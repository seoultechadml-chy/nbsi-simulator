"""공개 TDB 후보 검증과 승인 기록.

TDB 내용은 절대 고치지 않는다. 읽어 보고, 상태도를 그려 보고, 사용자가 승인하면 복사만 한다.

1) 후보 검증 (data/tdb_candidates/에 넣은 파일):
    python -m src.tdb_finder check data/tdb_candidates/NbSi.tdb --pair Nb Si
   -> 오류 없이 읽히는지, 원소·상 목록, Nb-Si 상태도 그림, 보고서(.md)를 만든다.

2) 사용자가 그림을 원 논문 상태도와 비교한 뒤 승인:
    python -m src.tdb_finder approve data/tdb_candidates/NbSi.tdb --by "이름" \
        --source "저자, 학술지, 연도, DOI" --terms "이용 조건/인용 방법"
   -> data/tdb/로 복사하고 data/tdb/README.md에 출처와 승인 기록을 남긴다.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import warnings
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CAND = ROOT / "data" / "tdb_candidates"
APPROVED = ROOT / "data" / "tdb"
KELVIN = 273.15


def inspect(tdb_path) -> dict:
    """TDB를 읽고 원소·상·참고문헌 정보를 정리한다."""
    from pycalphad import Database

    info = {"file": str(tdb_path), "ok": False, "warnings": [], "error": ""}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            db = Database(str(tdb_path))
        except Exception as e:
            info["error"] = f"{type(e).__name__}: {e}"
            return info
        info["warnings"] = sorted({str(x.message) for x in w})
    info["ok"] = True
    info["elements"] = sorted(e for e in db.elements if e not in ("VA", "/-", "*"))
    phases = {}
    for name, ph in sorted(db.phases.items()):
        subl = [sorted(str(s.name) for s in c) for c in ph.constituents]
        phases[name] = {"sublattices": list(ph.sublattices), "constituents": subl, "model_hints": dict(ph.model_hints)}
    info["phases"] = phases
    info["n_parameters"] = len(db._parameters)
    info["references"] = {str(k): str(v) for k, v in getattr(db, "refstore", {}).items()} if hasattr(db, "refstore") else {}
    info["sha256_16"] = hashlib.sha256(Path(tdb_path).read_bytes()).hexdigest()[:16]
    return info


def plot_binary(tdb_path, a: str, b: str, out_png, T_C=(900, 2600), x_max=1.0, dx=0.01, dT=10) -> Path:
    """a-b 이원 상태도를 그려 저장한다. 가로축은 b의 몰분율."""
    from pycalphad import Database, binplot, variables as v

    db = Database(str(tdb_path))
    A, B = a.upper(), b.upper()
    comps = [A, B] + (["VA"] if "VA" in db.elements else [])
    phases = sorted(db.phases.keys())
    fig, ax = plt.subplots(figsize=(8, 6))
    binplot(
        db, comps, phases,
        {v.X(B): (0, x_max, dx), v.T: (T_C[0] + KELVIN, T_C[1] + KELVIN, dT), v.P: 101325, v.N: 1},
        plot_kwargs={"ax": ax},
    )
    leg = ax.get_legend()
    if leg is not None:  # 범례를 그림 아래로 옮겨 오른쪽 °C 축과 겹치지 않게 한다
        handles, labels = leg.legend_handles, [t.get_text() for t in leg.texts]
        leg.remove()
        ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4, fontsize=8, frameon=False)
    ax.set_xlabel(f"X({b}) (mole fraction)")
    ax.set_ylabel("Temperature (K)")
    sec = ax.secondary_yaxis("right", functions=(lambda k: k - KELVIN, lambda c: c + KELVIN))
    sec.set_ylabel("Temperature (°C)")
    ax.set_title(f"{a}-{b} calculated  ({Path(tdb_path).name})")
    fig.tight_layout()
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png


def write_report(info: dict, pngs: list[Path], out_md: Path) -> Path:
    lines = [f"# TDB 후보 검증 보고서: `{Path(info['file']).name}`", ""]
    lines += ["## 출처 (사용자가 채움)", "", "- 출처 논문: ", "- 내려받은 곳: ", "- 이용 조건·인용 방법: ", ""]
    lines += ["## 읽기 결과", ""]
    if not info["ok"]:
        lines += [f"**읽기 실패**: `{info['error']}`", ""]
    else:
        lines += [f"- 읽기: 성공 (파라미터 {info['n_parameters']}개)", f"- 파일 지문(sha256 앞 16자리): `{info['sha256_16']}`",
                  f"- 원소: {', '.join(info['elements'])}", f"- 상 개수: {len(info['phases'])}", ""]
        if info["warnings"]:
            lines += ["### 경고", ""] + [f"- {w}" for w in info["warnings"]] + [""]
        lines += ["### 상 목록", "", "| 상 | 부격자 비율 | 구성 성분 |", "|---|---|---|"]
        for name, p in info["phases"].items():
            subl = " : ".join(str(s) for s in p["sublattices"])
            cons = " : ".join(",".join(c) for c in p["constituents"])
            lines.append(f"| {name} | {subl} | {cons} |")
        lines.append("")
        if info["references"]:
            lines += ["### TDB 안의 참고문헌 기록", ""] + [f"- {k}: {v}" for k, v in info["references"].items()] + [""]
    if pngs:
        lines += ["## 계산 상태도", ""] + [f"![{p.name}]({p.name})" for p in pngs] + [""]
        lines += ["> 원 논문의 상태도와 비교해 주세요: 상 종류, 공정·포정 온도, 고용 한계, 녹는점.", ""]
    lines += ["## 승인", "", "- [ ] 원 논문 상태도와 비교 완료", "- 승인자: ", "- 날짜: ", ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    return out_md


def check(tdb_path, pair=None, T_C=(900, 2600)) -> dict:
    tdb_path = Path(tdb_path)
    info = inspect(tdb_path)
    pngs = []
    if info["ok"]:
        print(f"[읽기 성공] 원소: {info['elements']}, 상 {len(info['phases'])}개")
        for w in info["warnings"]:
            print("  경고:", w)
        if pair:
            a, b = pair
            stem = tdb_path.stem
            print(f"  {a}-{b} 상태도 계산 중 (수 분 걸릴 수 있음)...")
            pngs.append(plot_binary(tdb_path, a, b, tdb_path.with_name(f"{stem}_{a}{b}_full.png"), T_C=T_C))
            pngs.append(plot_binary(tdb_path, a, b, tdb_path.with_name(f"{stem}_{a}{b}_0-40.png"), T_C=T_C, x_max=0.4, dx=0.005))
            for p in pngs:
                print("  그림 저장:", p)
    else:
        print("[읽기 실패]", info["error"])
    md = write_report(info, pngs, tdb_path.with_name(tdb_path.stem + "_report.md"))
    print("보고서:", md)
    return info


def approve(tdb_path, by: str, source: str, terms: str) -> Path:
    """사용자가 승인한 후보를 data/tdb/로 복사하고 README에 기록한다. (내용은 바꾸지 않음)"""
    src = Path(tdb_path)
    info = inspect(src)
    if not info["ok"]:
        raise SystemExit(f"[중단] 읽히지 않는 파일은 승인할 수 없습니다: {info['error']}")
    APPROVED.mkdir(parents=True, exist_ok=True)
    dst = APPROVED / src.name
    if dst.exists():
        raise SystemExit(f"[중단] 같은 이름의 승인 파일이 이미 있습니다: {dst}")
    shutil.copy2(src, dst)
    readme = APPROVED / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = text.replace("| (아직 없음) | | | | | |\n", "")
    row = f"| {dst.name} | {source} | {', '.join(info['elements'])} | {terms} | {by} | {date.today().isoformat()} |\n"
    readme.write_text(text.rstrip("\n") + "\n" + row, encoding="utf-8")
    print(f"승인 완료: {dst}\nREADME 기록: {readme}")
    return dst


def main():
    ap = argparse.ArgumentParser(description="TDB 후보 검증·승인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="후보 TDB 읽기 검사 + 상태도 그리기")
    c.add_argument("tdb")
    c.add_argument("--pair", nargs=2, metavar=("A", "B"), help="상태도를 그릴 두 원소, 예: Nb Si")
    c.add_argument("--tmin", type=float, default=900)
    c.add_argument("--tmax", type=float, default=2600)
    p = sub.add_parser("approve", help="사용자가 승인한 후보를 data/tdb/로 복사")
    p.add_argument("tdb")
    p.add_argument("--by", required=True, help="승인자 이름")
    p.add_argument("--source", required=True, help="출처 논문 (저자, 학술지, 연도, DOI)")
    p.add_argument("--terms", required=True, help="이용 조건·인용 방법")
    a = ap.parse_args()
    if a.cmd == "check":
        check(a.tdb, a.pair, (a.tmin, a.tmax))
    else:
        approve(a.tdb, a.by, a.source, a.terms)


if __name__ == "__main__":
    sys.exit(main())
