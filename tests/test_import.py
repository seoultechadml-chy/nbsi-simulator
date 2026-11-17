import numpy as np

from src.import_user_db import process_group, to_num


def test_to_num():
    assert to_num("52,46") == (52.46, True)      # 소수점 쉼표는 읽되 표시
    assert to_num(" 13.7 ") == (13.7, False)
    assert np.isnan(to_num("-")[0]) and np.isnan(to_num("abc")[0])


def test_process_group():
    assert process_group("vacuum non-consumable arc melting") == "용해·주조"
    assert process_group("DS + HT") == "방향성응고"
    assert process_group("Spark Plasma Sintering") == "분말야금·소결"
    assert process_group("laser powder bed fusion (LPBF)") == "적층제조"
    assert process_group(None) == ""
