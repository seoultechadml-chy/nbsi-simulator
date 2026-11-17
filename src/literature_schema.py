"""literature.csv / extracted_pending.csv의 열 정의와 기본 점검.

열을 추가하거나 바꾸려면 이 파일만 고친다. 빈 양식은 아래로 다시 만든다.
    python -m src.literature_schema init      # 빈 양식 만들기 (이미 있으면 건드리지 않음)
    python -m src.literature_schema check data/literature.csv   # 점검만 (파일은 안 바꿈)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# 조성 열 (at.% 기준으로 쓰는 것을 원칙으로 한다). 원소를 추가하려면 여기에 넣는다.
ELEMENTS = [
    "Nb", "Si", "Ti", "Cr", "Al", "Hf", "Mo", "W", "Ta", "Zr", "V", "B", "C", "Y", "Ge", "Sn", "Fe",
    "Ga", "Re", "Ru", "Co", "Ni", "Sc", "Mn", "Mg", "Au", "P", "Sr", "Gd", "Dy", "Ho", "Er", "Ce", "In",
]
# 화합물 형태로 첨가한 경우 (복합재). 원소 조성과 따로 적는다.
ADDITIVES = ["ZrB2", "TaB2", "ZrC", "B4C", "TiC"]

LITERATURE_COLUMNS = (
    ["alloy_id"]
    + ELEMENTS
    + ADDITIVES
    + [
        "composition_basis",          # at.% 공칭 / at.% 실측 / wt.% 공칭 / wt.% 실측
        "process",                    # 원문 표기 그대로 (arc melting, SPS, DS ...)
        "process_group",              # 묶음: 용해·주조 / 방향성응고 / 분말야금·소결 / 적층제조 / 기타
        "heat_treatment_temp_C",      # 열처리 온도. 주조 상태(as-cast)면 빈칸
        "heat_treatment_time_h",      # 열처리 시간
        "heat_treatment2_temp_C",     # 2차 열처리 (있으면)
        "heat_treatment2_time_h",
        "phases_observed",            # 관찰된 상 이름 목록 (분율 없이). 예: "Nbss; Nb5Si3"
        "phase_fraction_measured",    # 예: "Nbss:45; Nb5Si3:55"
        "phase_fraction_basis",       # vol.% / area.% / wt.% 등
        "hardness_HV",
        "hardness_load_kgf",
        "compressive_strength_MPa",   # 최대 압축강도
        "compressive_yield_MPa",      # 압축 항복강도 (0.2% 등)
        "fracture_toughness_MPam05",
        "fracture_toughness_std",     # 표준편차 또는 ± 값 (있으면)
        "toughness_method",           # SENB / chevron notch / 압입(indentation) / ...
        "test_temperature_C",
        "source",                     # DOI 또는 "자체 측정" (참고문헌 번호만 있으면 "파일:번호")
        "year",
        "source_location",            # 예: "p.5, Table 2"
        "entry_method",               # 자동 추출 / 직접 입력 / 파일 가져오기
        "approved_by",
        "approved_date",
        "notes",
    ]
)

# 승인 대기 파일에만 있는 열
PENDING_EXTRA = [
    "pending_id",       # 승인 화면에서 행을 구분하는 번호
    "paper_title",
    "source_quote",     # 값이 나온 원문 구절 (승인할 때 나란히 보여 줌)
    "flags",            # 확인 필요 사유, 중복 후보 등 (; 로 구분)
    "review_status",    # 대기 / 승인 / 수정 후 승인 / 반려
    "reviewer_note",
    "extracted_date",
]
PENDING_COLUMNS = PENDING_EXTRA[:1] + LITERATURE_COLUMNS + PENDING_EXTRA[1:]

GRAPH_TODO_COLUMNS = ["source", "paper_title", "figure", "quantity", "note"]

# 값이 이 범위를 크게 벗어나면 "확인 필요"로 표시한다 (오타·단위 실수 찾기용 거친 기준, 물성 데이터 아님)
SANITY_RANGES = {
    "hardness_HV": (50, 2500),
    "compressive_strength_MPa": (20, 6000),
    "compressive_yield_MPa": (20, 6000),
    "fracture_toughness_MPam05": (0.5, 60),
    "test_temperature_C": (-273, 2000),
    "heat_treatment_temp_C": (200, 2200),
    "heat_treatment_time_h": (0, 2000),
}

COMPOSITION_BASIS_VALUES = ["at.% 공칭", "at.% 실측", "wt.% 공칭", "wt.% 실측", "at.%", "wt.%"]  # 뒤 둘: 공칭/실측 구분 미기재


def empty(columns) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def init_templates(overwrite: bool = False) -> list[Path]:
    made = []
    for name, cols in [
        ("literature.csv", LITERATURE_COLUMNS),
        ("extracted_pending.csv", PENDING_COLUMNS),
        ("papers/graph_extraction_needed.csv", GRAPH_TODO_COLUMNS),
    ]:
        p = DATA / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not overwrite:
            print(f"이미 있음(건드리지 않음): {p}")
            continue
        empty(cols).to_csv(p, index=False, encoding="utf-8-sig")  # utf-8-sig: 엑셀에서 한글이 안 깨지게
        made.append(p)
        print(f"빈 양식 생성: {p}")
    return made


def check_rows(df: pd.DataFrame) -> pd.Series:
    """행마다 문제점을 문자열로 돌려준다 (문제가 없으면 빈 문자열). 값은 바꾸지 않는다."""
    flags = []
    for _, r in df.iterrows():
        f = []
        comp = pd.to_numeric(pd.Series({e: r.get(e) for e in ELEMENTS + ADDITIVES if e in df.columns}), errors="coerce")
        if comp.notna().any():
            s = comp.fillna(0).sum()
            if abs(s - 100) > 0.5:
                f.append(f"조성 합 {s:.1f} (100 아님)")
        else:
            f.append("조성 없음")
        basis = str(r.get("composition_basis", "") or "").strip()
        if basis in ("", "nan"):
            f.append("조성 단위(at/wt)·공칭/실측 미기재")
        elif basis not in COMPOSITION_BASIS_VALUES:
            f.append(f"조성 기준 값 확인: '{basis}'")
        for col, (lo, hi) in SANITY_RANGES.items():
            if col in df.columns:
                v = pd.to_numeric(r.get(col), errors="coerce")
                if pd.notna(v) and not (lo <= v <= hi):
                    f.append(f"{col}={v} 범위 밖")
        if "fracture_toughness_MPam05" in df.columns and pd.notna(pd.to_numeric(r.get("fracture_toughness_MPam05"), errors="coerce")):
            if str(r.get("toughness_method", "") or "").strip() in ("", "nan"):
                f.append("파괴인성 시험법 미기재")
        if str(r.get("source", "") or "").strip() in ("", "nan"):
            f.append("출처 없음")
        flags.append("; ".join(f))
    return pd.Series(flags, index=df.index, name="flags")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="빈 양식 만들기")
    c = sub.add_parser("check", help="CSV 점검 (파일은 바꾸지 않음)")
    c.add_argument("csv")
    a = ap.parse_args()
    if a.cmd == "init":
        init_templates()
    else:
        df = pd.read_csv(a.csv)
        missing = [c for c in LITERATURE_COLUMNS if c not in df.columns]
        if missing:
            print("없는 열:", missing)
        fl = check_rows(df)
        bad = fl[fl != ""]
        print(f"{len(df)}행 중 확인 필요 {len(bad)}행")
        for i, msg in bad.items():
            print(f"  {i + 2}번째 줄 ({df.loc[i].get('alloy_id', '')}): {msg}")


if __name__ == "__main__":
    sys.exit(main())
