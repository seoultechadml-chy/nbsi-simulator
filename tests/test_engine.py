from src.calphad_engine import calc_equilibrium


def test_two_phase_region(almg_tdb):
    # Al-30at%Mg, 700 K: FCC + beta 2상 영역 (pycalphad 공식 예제 상태도와 같은 결과)
    r = calc_equilibrium({"Mg": 30}, 700 - 273.15, almg_tdb, base_element="Al")
    assert r["status"] == "ok"
    assert set(r["phases"]) == {"FCC_A1", "ALMG_BETA"}
    assert abs(sum(p["fraction"] for p in r["phases"].values()) - 1) < 1e-6
    assert r["composition"] == {"Al": 70.0, "Mg": 30.0}
    # 상별 조성 합은 100 at.%
    for p in r["phases"].values():
        assert abs(sum(p["composition"].values()) - 100) < 1e-6


def test_pure_element_and_bad_input(almg_tdb):
    r = calc_equilibrium({"Mg": 0}, 300, almg_tdb, base_element="Al")
    assert list(r["phases"]) == ["FCC_A1"]
    import pytest
    with pytest.raises(ValueError):
        calc_equilibrium({"Mg": 120}, 300, almg_tdb, base_element="Al")
    with pytest.raises(ValueError):
        calc_equilibrium({"Si": 10}, 300, almg_tdb, base_element="Al")
