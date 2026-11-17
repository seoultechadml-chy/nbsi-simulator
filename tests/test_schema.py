import pandas as pd

from src.literature_schema import LITERATURE_COLUMNS, check_rows


def test_flags():
    df = pd.DataFrame(
        [
            {"alloy_id": "A", "Nb": 84, "Si": 16, "composition_basis": "at.% 공칭",
             "fracture_toughness_MPam05": 10, "toughness_method": "SENB", "source": "doi"},
            {"alloy_id": "B", "Nb": 80, "Si": 16, "fracture_toughness_MPam05": 999, "source": ""},
        ],
        columns=LITERATURE_COLUMNS,
    )
    fl = check_rows(df)
    assert fl[0] == ""
    assert "조성 합" in fl[1] and "범위 밖" in fl[1] and "출처 없음" in fl[1]
    assert "시험법 미기재" in fl[1] and "조성 단위" in fl[1]
