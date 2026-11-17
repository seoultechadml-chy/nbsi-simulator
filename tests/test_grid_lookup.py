import json
import shutil

import pandas as pd
import pytest

from src.build_grid import build, meta_path
from src.lookup import PhaseGrid


def test_build_resume_and_lookup(almg_cfg):
    build(almg_cfg, limit=3)                      # 일부만 계산 (중간에 끊긴 상황)
    n1 = len(pd.read_csv(almg_cfg["output_csv"]))
    res = build(almg_cfg)                         # 이어서 계산
    df = pd.read_csv(almg_cfg["output_csv"])
    assert res["ok"] == (9 - 3) * 3               # 남은 6개 조성 x 3개 온도만 새로 계산
    assert len(df) > n1
    assert not df.duplicated(["Mg", "T_C", "phase"]).any()
    assert build(almg_cfg)["ok"] == 0              # 다시 돌려도 중복 계산 없음

    g = PhaseGrid(almg_cfg["output_csv"])
    # 격자 점 위에서는 원자료와 같아야 한다
    raw = df[(df.Mg == 30) & (df.T_C == 300)].set_index("phase")["fraction"]
    f = g.fractions({"Mg": 30}, 300)
    for ph, v in raw.items():
        assert f[ph] == pytest.approx(v, abs=1e-5)
    assert sum(g.fractions({"Mg": 27.3}, 350).values()) == pytest.approx(1)
    assert g.fractions({"Mg": 50}, 300) == {}     # 범위 밖이면 빈 값
    c = g.curve("Mg", {"Mg": 0}, 300, n=11)
    assert len(c) == 11 and (c.drop(columns="Mg").sum(axis=1).round(6) == 1).all()


def test_refuses_mixing_tdbs(almg_cfg, tmp_path):
    build(almg_cfg, limit=1)
    m = json.loads(meta_path(almg_cfg).read_text(encoding="utf-8"))
    other = tmp_path / "other.tdb"
    shutil.copy(almg_cfg["tdb_file"], other)
    other.write_text(other.read_text() + "\n$ changed\n")
    with pytest.raises(SystemExit):
        build({**almg_cfg, "tdb_file": str(other)})
    assert m["tdb_sha256_16"]
