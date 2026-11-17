"""사용자가 정리한 엑셀 DB 두 개를 literature.csv 양식으로 옮기고 중복을 제거한다.

원자료(data/raw_user/*.xlsx)는 바꾸지 않는다. 값도 고치지 않는다.
(예외: '52,46'처럼 소수점이 쉼표로 적힌 숫자는 52.46으로 읽고, flags에 그 사실을 남긴다)

중복 판단 (측정값 하나 단위):
    조성(모든 원소, 0.1 at.% 단위로 반올림)이 같고
    + 물성 종류가 같고
    + 값이 같고 (파괴인성 0.01, 강도·경도 1 단위로 반올림)
    + 시험 온도가 같으면  ->  같은 측정값이 여러 번 실린 것으로 보고 하나만 남긴다.
남기는 순서: A 파일(공정·연도 정보가 더 많음) > 메타정보가 많은 행 > 위쪽 행.

실행:
    python -m src.import_user_db            # 미리보기 파일과 보고서만 만든다 (literature.csv 안 바꿈)
    python -m src.import_user_db --commit --by "승인자 이름" [--basis "at.% 공칭"]
                                             # 사용자가 확인한 뒤 literature.csv에 추가
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.literature_schema import ADDITIVES, ELEMENTS, LITERATURE_COLUMNS, check_rows  # noqa: E402

RAW = ROOT / "data" / "raw_user"
FILE_A = RAW / "A_NbSilicide_DB.xlsx"
FILE_B = RAW / "B_Nballoy_1117.xlsx"
OUT_STAGING = ROOT / "data" / "import_staging.csv"
OUT_DUPS = ROOT / "data" / "import_duplicates.csv"
OUT_EXCLUDED = ROOT / "data" / "import_excluded.csv"
OUT_REPORT = ROOT / "data" / "import_report.md"
LIT = ROOT / "data" / "literature.csv"

COMP_COLS = ELEMENTS + ADDITIVES
PROPS = ["fracture_toughness_MPam05", "compressive_strength_MPa", "compressive_yield_MPa", "hardness_HV"]
ROUND = {"fracture_toughness_MPam05": 2, "compressive_strength_MPa": 0, "compressive_yield_MPa": 0, "hardness_HV": 0}


# ---------------------------------------------------------------------------
def to_num(x):
    """숫자로 읽는다. '52,46' 같은 소수점 쉼표는 읽되 표시한다. 읽을 수 없으면 NaN."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan, False
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x), False
    s = str(x).strip()
    if s in ("", "-", "nan"):
        return np.nan, False
    try:
        return float(s), False
    except ValueError:
        if re.fullmatch(r"-?\d+,\d+", s):
            return float(s.replace(",", ".")), True
        return np.nan, False


def process_group(text) -> str:
    if text is None or (isinstance(text, float) and np.isnan(text)) or str(text).strip() == "":
        return ""
    t = str(text).lower()
    if re.search(r"\bds\b|ds_|ds\+|directional|unidirection|czochralski|floating zone", t):
        return "방향성응고"
    if re.search(r"slm|lpbf|laser powder|^am$|as built|as-built", t):
        return "적층제조"
    if re.search(r"sps|spark plasma|sinter|hot press|p/m|ball mill|powder", t):
        return "분말야금·소결"
    if re.search(r"arc|ingot|vim|melt|cast", t):
        return "용해·주조"
    return "기타"


def _num_cols(row, cols, flags):
    out = {}
    for c_out, c_in in cols.items():
        v, comma = to_num(row.get(c_in))
        if comma:
            flags.append(f"{c_out}: 원자료 소수점 쉼표 변환")
        out[c_out] = v
    return out


# ---------------------------------------------------------------------------
def load_a() -> pd.DataFrame:
    df = pd.read_excel(FILE_A)
    phase_cols = list(df.columns[df.columns.get_loc("Nbss"): df.columns.get_loc("Fracture_toughness_temp")])
    recs = []
    for i, r in df.iterrows():
        flags = []
        comp = _num_cols(r, {e: e for e in COMP_COLS if e in df.columns}, flags)
        ph = [p for p in phase_cols if to_num(r.get(p))[0] == 1]
        notes = []
        for lab, col in [("HT1 압력(MPa)", "HT1_Pressure(Mpa)"), ("HT2 압력(MPa)", "HT2_Pressure(Mpa)"),
                         ("인출속도(mm/min)", "Withdrawl_Rate(mm/min^-1)")]:
            v, _ = to_num(r.get(col))
            if not np.isnan(v):
                notes.append(f"{lab}={v:g}")
        base = {
            "origin_file": "A", "origin_row": i + 2, "ref": str(r["Ref_No."]).strip(),
            "year": to_num(r.get("Year"))[0], "alloy_id": r.get("Alloy_composition"),
            "process": r.get("Process") if pd.notna(r.get("Process")) else "",
            **comp,
            **_num_cols(r, {"heat_treatment_temp_C": "HT1_Temp_(℃)", "heat_treatment_time_h": "HT1_DT_(hours)",
                            "heat_treatment2_temp_C": "HT2_Temp_(℃)", "heat_treatment2_time_h": "HT2_DT_(hours)"}, flags),
            "phases_observed": "; ".join(ph), "notes": "; ".join(notes), "_flags": flags,
        }
        meas = []
        v = _num_cols(r, {"t": "Fracture_toughness_temp", "v": "Fracture_toughness"}, flags)
        meas.append(("fracture_toughness_MPam05", v["v"], v["t"]))
        v = _num_cols(r, {"t": "Compresisve_test_temp_(℃)", "v": "Compressive_strength_σ_max_(Mpa)",
                          "y": "Compressive_strength_σ_0.2_(Mpa)"}, flags)
        meas.append(("compressive_strength_MPa", v["v"], v["t"]))
        if not np.isnan(v["y"]):
            meas.append(("compressive_yield_MPa", v["y"], v["t"]))
        else:
            w = _num_cols(r, {"t": "CYS_Temp_(℃)", "v": "Compressive_Yield_Strength_(MPa)"}, flags)
            meas.append(("compressive_yield_MPa", w["v"], w["t"]))
        v = _num_cols(r, {"v": "Vickers_hardness_(Hv)"}, flags)
        meas.append(("hardness_HV", v["v"], np.nan))
        base["_meas"] = [m for m in meas if not np.isnan(m[1])]
        recs.append(base)
    return pd.DataFrame(recs)


def load_b() -> pd.DataFrame:
    df = pd.read_excel(FILE_B)
    label_map = {0: "arc-melted", 1: "DS", 3: "DS + HT", 4: "ball milling", 5: "LPBF"}
    recs = []
    for i, r in df.iterrows():
        flags = []
        comp = _num_cols(r, {e: e for e in COMP_COLS if e in df.columns}, flags)
        proc = r.get("[텍스트] Processing method")
        proc = "" if pd.isna(proc) else str(proc).strip()
        lab, _ = to_num(r.get("Processing method label"))
        if not proc and not np.isnan(lab):
            proc = label_map.get(int(lab), "")
        notes = []
        for lab_, col in [("DS 성장속도(mm/h)", "[DS] growth rate (mm/h)"), ("DS 인출속도(mm/min)", "[DS] withdrawal rate (mm/min)")]:
            v, _ = to_num(r.get(col))
            if not np.isnan(v):
                notes.append(f"{lab_}={v:g}")
        ref = r.get("[텍스트] Ref No.")
        base = {
            "origin_file": "B", "origin_row": i + 2, "ref": "" if pd.isna(ref) else str(ref).strip(),
            "year": to_num(r.get("Year"))[0], "alloy_id": r.get("[텍스트] Alloy name"),
            "process": proc, **comp,
            **_num_cols(r, {"heat_treatment_temp_C": "HT1_Temp (℃)", "heat_treatment_time_h": "HT1_DT (hours)",
                            "heat_treatment2_temp_C": "HT2_Temp (℃)", "heat_treatment2_time_h": "HT2_DT (hours)"}, flags),
            "phases_observed": "", "notes": "; ".join(notes), "_flags": flags,
        }
        meas = []
        for prop, tcol, vcol in [
            ("fracture_toughness_MPam05", "FT_Temp (℃)", "Fracture Toughness (Mpa m1/2)"),
            ("compressive_strength_MPa", "CS_Temp (℃)", "Compressive Strength (Mpa)"),
            ("compressive_yield_MPa", "CYS_Temp (℃)", "Compressive Yield Strength (Mpa)"),
        ]:
            v = _num_cols(r, {"t": tcol, "v": vcol}, flags)
            meas.append((prop, v["v"], v["t"]))
        v = _num_cols(r, {"v": "Vickers hardness (Hv)"}, flags)
        meas.append(("hardness_HV", v["v"], np.nan))
        base["_meas"] = [m for m in meas if not np.isnan(m[1])]
        recs.append(base)
    return pd.DataFrame(recs)


# ---------------------------------------------------------------------------
def comp_key(row) -> str:
    vals = [row.get(c, np.nan) for c in COMP_COLS]
    if all(pd.isna(v) for v in vals):  # 조성 열이 비어 있으면 합금 이름으로 대신 비교
        return "name:" + re.sub(r"\s+", "", str(row.get("alloy_id", ""))).lower()
    return "|".join(f"{0 if pd.isna(v) else round(float(v), 1):g}" for v in vals)


def meta_score(row) -> int:
    keys = ["process", "year", "heat_treatment_temp_C", "phases_observed"]
    return sum(1 for k in keys if pd.notna(row.get(k)) and str(row.get(k)) not in ("", "nan"))


def run():
    src = pd.concat([load_a(), load_b()], ignore_index=True)
    src["comp_key"] = src.apply(comp_key, axis=1)
    src["meta"] = src.apply(meta_score, axis=1)

    # --- 제외: 출처 없음 / 대상 물성 없음 ---
    excluded = []
    no_ref = src["ref"].isin(["", "nan"])
    no_meas = src["_meas"].map(len) == 0
    for _, r in src[no_ref & ~no_meas].iterrows():
        excluded.append({"origin_file": r.origin_file, "origin_row": r.origin_row, "alloy_id": r.alloy_id, "reason": "출처(Ref No.) 없음"})
    use = src[~no_ref & ~no_meas].copy()

    # --- 측정값 단위로 펼치기 ---
    m = use[["origin_file", "origin_row", "ref", "alloy_id", "comp_key", "meta", "_meas"]].explode("_meas")
    m[["prop", "value", "test_T"]] = pd.DataFrame(m["_meas"].tolist(), index=m.index)
    m = m.drop(columns="_meas")
    m["v_round"] = [round(v, ROUND[p]) for v, p in zip(m["value"], m["prop"])]
    m["T_key"] = m["test_T"].map(lambda t: "na" if pd.isna(t) else f"{float(t):g}")
    m["dup_key"] = m["comp_key"] + "#" + m["prop"] + "#" + m["v_round"].astype(str) + "#" + m["T_key"]
    m = m.sort_values(["dup_key", "origin_file", "meta", "origin_row"], ascending=[True, True, False, True])
    m["keep"] = ~m.duplicated("dup_key", keep="first")

    # 중복 목록 (지운 것과 남긴 것을 짝지어 기록)
    kept = m[m.keep].set_index("dup_key")
    dups = m[~m.keep].copy()
    dups["kept_file"] = dups["dup_key"].map(kept["origin_file"])
    dups["kept_row"] = dups["dup_key"].map(kept["origin_row"])
    dups["kept_ref"] = dups["dup_key"].map(kept["ref"])
    dups["kind"] = np.where(dups["origin_file"] != dups["kept_file"], "A-B 파일 간",
                            np.where(dups["ref"] == dups["kept_ref"], "같은 파일·같은 Ref", "같은 파일·다른 Ref"))

    # --- 남은 측정값으로 literature 행 다시 만들기 (원 행 x 시험 온도마다 한 행) ---
    meta_cols = [c for c in use.columns if c not in ("_meas", "comp_key", "meta")]
    rows = []
    for (f, rr, Tk), g in m[m.keep].groupby(["origin_file", "origin_row", "T_key"], sort=False):
        base = use[(use.origin_file == f) & (use.origin_row == rr)].iloc[0]
        row = {c: base[c] for c in meta_cols}
        row["test_temperature_C"] = np.nan if Tk == "na" else float(Tk)
        for _, x in g.iterrows():
            row[x["prop"]] = x["value"]
        rows.append(row)
    st = pd.DataFrame(rows)
    st["source"] = st["origin_file"] + ":" + st["ref"]
    st["source_location"] = "엑셀 " + st["origin_file"] + " " + st["origin_row"].astype(str) + "행"
    st["entry_method"] = "파일 가져오기"
    if "hardness_HV" in st:
        st.loc[st["hardness_HV"].notna() & st["test_temperature_C"].isna(), "notes"] = (
            st["notes"].fillna("").str.cat(["경도 시험 온도 원자료에 없음"] * len(st), sep="; ").str.strip("; "))
    st["process_group"] = st["process"].map(process_group)
    for c in LITERATURE_COLUMNS:
        if c not in st:
            st[c] = np.nan
    auto = check_rows(st)
    extra = st["_flags"].map(lambda l: "; ".join(l))
    comp_empty = st[COMP_COLS].isna().all(axis=1)
    st["flags"] = [
        "; ".join(x for x in (a, b, "조성 열 비어 있음(합금 이름에만 있음)" if ce else "") if x)
        for a, b, ce in zip(auto, extra, comp_empty)
    ]
    st = st[LITERATURE_COLUMNS + ["flags", "origin_file", "origin_row", "ref"]]
    st = st.sort_values(["origin_file", "origin_row", "test_temperature_C"])

    OUT_STAGING.parent.mkdir(parents=True, exist_ok=True)
    st.to_csv(OUT_STAGING, index=False, encoding="utf-8-sig")
    dcols = ["kind", "prop", "value", "test_T", "alloy_id", "origin_file", "origin_row", "ref", "kept_file", "kept_row", "kept_ref"]
    dups[dcols].sort_values(["kind", "prop", "origin_file", "origin_row"]).to_csv(OUT_DUPS, index=False, encoding="utf-8-sig")
    pd.DataFrame(excluded).to_csv(OUT_EXCLUDED, index=False, encoding="utf-8-sig")
    write_report(src, use, m, dups, st, excluded, no_meas)
    return st, dups


def write_report(src, use, m, dups, st, excluded, no_meas):
    L = ["# 사용자 DB 가져오기 보고서", "", f"작성일: {date.today().isoformat()}", ""]
    L += ["## 원자료", "", "| 파일 | 행 수 | 대상 물성이 있는 행 | Ref 개수 |", "|---|---|---|---|"]
    for f, path in [("A", FILE_A.name), ("B", FILE_B.name)]:
        s = src[src.origin_file == f]
        L.append(f"| {f} (`{path}`) | {len(s)} | {(s['_meas'].map(len) > 0).sum()} | {s['ref'].nunique()} |")
    L += ["", f"대상 물성: 파괴인성, 압축강도(최대·항복), 비커스 경도. 인장·산화·크리프 값은 이번 양식에 없어 가져오지 않았습니다 (원자료에는 그대로 있음).", ""]
    L += ["## 측정값 수와 중복 제거", "", "| 물성 | 전체 측정값 | 중복으로 제외 | 남은 값 | 그중 A | 그중 B |", "|---|---|---|---|---|---|"]
    for p in PROPS:
        x = m[m.prop == p]
        k = x[x.keep]
        L.append(f"| {p} | {len(x)} | {(~x.keep).sum()} | {len(k)} | {(k.origin_file == 'A').sum()} | {(k.origin_file == 'B').sum()} |")
    L += ["", "### 중복 종류", "", "| 종류 | 제외한 측정값 |", "|---|---|"]
    for k, n in dups["kind"].value_counts().items():
        L.append(f"| {k} | {n} |")
    L += ["", "- 같은 파일·같은 Ref: 공정·열처리 조건까지 같은 행에 같은 값이 반복 입력된 경우 (주로 경도가 시험 온도별 행마다 복사됨).",
          "- 같은 파일·다른 Ref: 리뷰 논문 등에서 같은 값을 다시 실은 경우로 보임.", "", "중복 판단 기준: 조성(0.1 at.% 단위) + 물성 종류 + 값 + 시험 온도가 모두 같음. 자세한 짝은 `import_duplicates.csv`.", ""]
    ab = dups[dups.kind == "A-B 파일 간"]
    if len(ab):
        L += ["### A와 B에서 같은 데이터를 가진 Ref 짝 (측정값 3개 이상)", "", "| B Ref (제외) | A Ref (남김) | 겹친 값 수 |", "|---|---|---|"]
        pair = ab.groupby(["ref", "kept_ref"]).size().sort_values(ascending=False)
        for (b, a), n in pair[pair >= 3].items():
            L.append(f"| {b} | {a} | {n} |")
        L.append("")
    L += ["## 제외한 행", "", f"- 출처(Ref No.) 없음: {len(excluded)}행 (`import_excluded.csv`)",
          f"- 대상 물성이 없는 행: {int(no_meas.sum())}행 (인장·산화 등만 있는 행)", ""]
    L += ["## 가져올 행 (`import_staging.csv`)", "", f"- 총 {len(st)}행 (원 행 하나에 시험 온도가 여럿이면 온도마다 한 행)",
          f"- 파괴인성 값이 있는 행: {st['fracture_toughness_MPam05'].notna().sum()}행", ""]
    fl = st["flags"].str.split("; ").explode()
    fl = fl[fl.fillna("") != ""].str.replace(r"=.*범위 밖", " 범위 밖", regex=True).str.replace(r"조성 합 [\d.]+ \(100 아님\)", "조성 합이 100이 아님", regex=True)
    L += ["### 확인 필요 표시 (행 수)", "", "| 내용 | 행 수 |", "|---|---|"]
    for k, n in fl.value_counts().items():
        L.append(f"| {k} | {n} |")
    L += ["", "> 위 표시는 값을 고치지 않고 알려 주기만 합니다.", ""]
    OUT_REPORT.write_text("\n".join(L), encoding="utf-8")


def commit(by: str, basis: str | None, exclude_bad_sum: bool = True):
    """확인받은 미리보기를 literature.csv에 추가한다.

    exclude_bad_sum: 조성 합이 100이 아닌 행은 넣지 않고 import_excluded.csv에 사유와 함께 남긴다.
    """
    st = pd.read_csv(OUT_STAGING)
    lit = pd.read_csv(LIT) if LIT.exists() else pd.DataFrame(columns=LITERATURE_COLUMNS)
    if (lit.get("entry_method") == "파일 가져오기").any():
        raise SystemExit("[중단] literature.csv에 이미 가져온 행이 있습니다. 두 번 넣지 않도록 멈춥니다.")
    if basis:
        st["composition_basis"] = basis
    bad = st["flags"].fillna("").str.contains("조성 합") if exclude_bad_sum else pd.Series(False, index=st.index)
    if bad.any():
        ex = st.loc[bad, ["origin_file", "origin_row", "alloy_id"]].assign(reason="조성 합이 100이 아님 (사용자 결정으로 제외)")
        old = pd.read_csv(OUT_EXCLUDED) if OUT_EXCLUDED.exists() and OUT_EXCLUDED.stat().st_size > 5 else pd.DataFrame()
        pd.concat([old, ex], ignore_index=True).drop_duplicates(["origin_file", "origin_row"]).to_csv(OUT_EXCLUDED, index=False, encoding="utf-8-sig")
    st = st[~bad].copy()
    st["approved_by"] = by
    st["approved_date"] = date.today().isoformat()
    # 승인 시점 기준으로 점검 표시를 다시 계산해 notes에 남긴다 (값은 바꾸지 않음)
    re_flags = check_rows(st[LITERATURE_COLUMNS])
    extra = st["flags"].fillna("").str.split("; ").map(lambda l: [x for x in l if "쉼표" in x])
    st["notes"] = st["notes"].fillna("").astype(str)
    for i in st.index:
        f = [x for x in re_flags[i].split("; ") if x] + extra[i]
        if f:
            st.at[i, "notes"] = "; ".join(x for x in [st.at[i, "notes"], "확인 필요: " + ", ".join(f)] if x)
    out = pd.concat([lit, st[LITERATURE_COLUMNS]], ignore_index=True)
    out.to_csv(LIT, index=False, encoding="utf-8-sig")
    print(f"literature.csv에 {len(st)}행 추가 (총 {len(out)}행), 조성 합 문제로 제외 {int(bad.sum())}행")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="확인한 뒤 literature.csv에 추가")
    ap.add_argument("--by", help="승인자 이름 (--commit과 함께)")
    ap.add_argument("--basis", help="모든 행의 조성 기준. 예: 'at.% 공칭' (사용자가 확인한 경우에만)")
    a = ap.parse_args()
    if a.commit:
        if not a.by:
            raise SystemExit("--by 승인자 이름이 필요합니다")
        commit(a.by, a.basis)
    else:
        st, dups = run()
        print(f"미리보기: {OUT_STAGING} ({len(st)}행), 중복 {len(dups)}건, 보고서: {OUT_REPORT}")


if __name__ == "__main__":
    main()
