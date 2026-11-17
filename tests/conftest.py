"""시험용 공통 설정.

Nb-Si TDB가 아직 없으므로 pycalphad에 시험용으로 들어 있는 Al-Mg DB로 코드 동작만 확인한다.
(재료 데이터를 확인하는 시험이 아니다)"""
import json
import os
import sys
from pathlib import Path

import pycalphad
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ALMG = os.path.join(os.path.dirname(pycalphad.__file__), "tests", "databases", "Al-Mg_Zhong.tdb")


@pytest.fixture
def almg_tdb():
    return ALMG


@pytest.fixture
def almg_cfg(tmp_path):
    return {
        "name": "Al-Mg test",
        "tdb_file": ALMG,
        "base_element": "Al",
        "elements": {"Mg": {"min": 0, "max": 40, "step": 5}},
        "temperature_C": {"min": 200, "max": 400, "step": 100},
        "output_csv": str(tmp_path / "grid.csv"),
        "failed_csv": str(tmp_path / "grid_failed.csv"),
    }
