"""조성 격자 일괄 계산 -> phase_grid.csv

설정 파일(config/*.json)에 적힌 원소 범위와 온도 범위의 모든 점에서
calc_equilibrium()을 돌려 결과를 CSV에 저장한다.

- 중간에 끊겨도 다시 실행하면 이미 계산한 점은 건너뛰고 이어서 계산한다.
- 계산이 실패한 점은 건너뛰고 *_failed.csv에 따로 남긴다.
- 어떤 TDB로 계산했는지 *_meta.json에 기록한다. TDB가 바뀌었으면 이어 계산하지 않는다.

실행:
    python -m src.build_grid config/grid_NbSi.json
    python -m src.build_grid config/grid_NbSi.json --retry-failed   # 실패한 점 다시 시도
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.calphad_engine import get_backend  # noqa: E402


def load_config(path) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("tdb_file", "output_csv", "failed_csv"):
        p = Path(cfg[key])
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
    return cfg


def frange(r: dict) -> list[float]:
    vals = np.arange(r["min"], r["max"] + r["step"] / 2, r["step"])
    return [round(float(x), 6) for x in vals]


def grid_points(cfg) -> tuple[list[str], list[tuple], list[float]]:
    """(용질 원소 목록, 조성 조합 목록, 온도 목록)"""
    els = list(cfg["elements"].keys())
    combos = [c for c in itertools.product(*(frange(cfg["elements"][e]) for e in els)) if sum(c) < 100]
    return els, combos, frange(cfg["temperature_C"])


def file_hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def meta_path(cfg) -> Path:
    return Path(cfg["output_csv"]).with_name(Path(cfg["output_csv"]).stem + "_meta.json")


def _key(comp: tuple, T: float) -> tuple:
    return tuple(round(float(x), 6) for x in comp) + (round(float(T), 6),)


def _read_done(path: Path, els: list[str]) -> set:
    done = set()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(_key([row[e] for e in els], row["T_C"]))
    return done


def build(cfg: dict, retry_failed: bool = False, limit: int | None = None) -> dict:
    eng = get_backend(cfg["tdb_file"], cfg["base_element"])
    base = cfg["base_element"]
    els, combos, temps = grid_points(cfg)
    all_els = [base] + els

    out = Path(cfg["output_csv"])
    fail = Path(cfg["failed_csv"])
    out.parent.mkdir(parents=True, exist_ok=True)

    # --- 어떤 TDB로 계산 중인지 확인 (다른 TDB 결과와 섞이지 않게) ---
    h = file_hash(cfg["tdb_file"])
    mp = meta_path(cfg)
    if out.exists() and mp.exists():
        old = json.loads(mp.read_text(encoding="utf-8"))
        if old.get("tdb_sha256_16") != h:
            raise SystemExit(
                f"[중단] 기존 {out.name}은(는) 다른 TDB({old.get('tdb_file')})로 계산한 것입니다.\n"
                f"      섞이지 않도록 기존 파일을 다른 이름으로 옮긴 뒤 다시 실행하세요."
            )
    mp.write_text(
        json.dumps(
            {
                "system": cfg.get("name"),
                "tdb_file": str(Path(cfg["tdb_file"]).relative_to(ROOT)) if Path(cfg["tdb_file"]).is_relative_to(ROOT) else cfg["tdb_file"],
                "tdb_sha256_16": h,
                "backend": eng.name,
                "base_element": base,
                "elements": cfg["elements"],
                "temperature_C": cfg["temperature_C"],
                "pressure_Pa": cfg.get("pressure_Pa", 101325),
                "updated": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    done = _read_done(out, els)
    failed_before = _read_done(fail, els)
    skip = done | (set() if retry_failed else failed_before)

    if retry_failed and fail.exists():
        # 다시 시도할 것이므로 실패 목록을 비우고 새로 쓴다
        fail.unlink()

    out_cols = els + ["T_C", "phase", "fraction"] + [f"x_{e}" for e in all_els]
    fail_cols = els + ["T_C", "message"]
    new_out = not out.exists()
    new_fail = not fail.exists()

    total = len(combos) * len(temps)
    todo = [(c, [T for T in temps if _key(c, T) not in skip]) for c in combos]
    todo = [(c, ts) for c, ts in todo if ts]
    if limit:
        todo = todo[:limit]
    n_todo = sum(len(ts) for _, ts in todo)
    print(f"[{cfg.get('name')}] 전체 {total}점 중 남은 {n_todo}점 계산 (조성 {len(todo)}개 x 온도)")

    n_ok = n_fail = 0
    t0 = time.time()
    with open(out, "a", newline="", encoding="utf-8") as fo, open(fail, "a", newline="", encoding="utf-8") as ff:
        wo, wf = csv.writer(fo), csv.writer(ff)
        if new_out:
            wo.writerow(out_cols)
        if new_fail:
            wf.writerow(fail_cols)
        for i, (comp, ts) in enumerate(todo, 1):
            cdict = dict(zip(els, comp))
            try:
                results = eng.equilibrium(cdict, ts)
            except Exception as e:  # 한 조성 전체가 실패하면 온도별로 다시 시도
                results = []
                for T in ts:
                    try:
                        results += eng.equilibrium(cdict, [T])
                    except Exception as e2:
                        results.append({"status": "failed", "message": f"{type(e2).__name__}: {e2}", "temperature_C": T})
            for r in results:
                T = r["temperature_C"]
                if r["status"] != "ok":
                    wf.writerow(list(comp) + [T, r["message"]])
                    n_fail += 1
                    continue
                for ph, d in r["phases"].items():
                    wo.writerow(
                        list(comp)
                        + [T, ph, f"{d['fraction']:.6f}"]
                        + [f"{d['composition'].get(e, 0.0):.4f}" for e in all_els]
                    )
                n_ok += 1
            fo.flush()
            ff.flush()
            if i % 5 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  {i}/{len(todo)} 조성 완료, 경과 {el:.0f}초, 남은 예상 {el / i * (len(todo) - i):.0f}초")

    print(f"끝: 성공 {n_ok}점, 실패 {n_fail}점 -> {out}")
    if n_fail:
        print(f"실패 목록: {fail}")
    return {"ok": n_ok, "failed": n_fail}


def main():
    ap = argparse.ArgumentParser(description="조성 격자 평형 계산")
    ap.add_argument("config", help="설정 파일 (예: config/grid_NbSi.json)")
    ap.add_argument("--tdb", help="설정 파일의 tdb_file 대신 쓸 TDB")
    ap.add_argument("--retry-failed", action="store_true", help="실패했던 점을 다시 계산")
    ap.add_argument("--limit", type=int, help="시험용: 조성 몇 개만 계산")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.tdb:
        cfg["tdb_file"] = str(Path(a.tdb).resolve())
    if not Path(cfg["tdb_file"]).exists():
        raise SystemExit(f"[중단] TDB 파일이 없습니다: {cfg['tdb_file']}\n      승인된 TDB를 data/tdb/에 넣고 설정 파일의 tdb_file을 고치세요.")
    build(cfg, retry_failed=a.retry_failed, limit=a.limit)


if __name__ == "__main__":
    main()
