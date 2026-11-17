"""열역학 계산 모듈.

화면(app.py)과 다른 모듈은 이 파일의 `calc_equilibrium()` 하나만 호출한다.
지금은 pycalphad(무료)만 구현되어 있다. 나중에 Thermo-Calc(TC-Python)나
Pandat을 쓰게 되면 `PycalphadBackend`와 같은 모양의 클래스를 하나 더 만들고
`get_backend()`에서 골라 주기만 하면 된다. 나머지 코드는 고칠 필요가 없다.

사용 예:
    from src.calphad_engine import calc_equilibrium
    r = calc_equilibrium({"Si": 16}, 1500, tdb_file="data/tdb/NbSi.tdb")
    r["phases"]  # {"BCC_A2": {"fraction": 0.42, "composition": {"Nb": 98.9, "Si": 1.1}}, ...}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

KELVIN = 273.15


def _norm(el: str) -> str:
    """원소 기호를 TDB 표기(대문자)로 바꾼다. 'Si' -> 'SI'"""
    return el.strip().upper()


def _pretty(el: str) -> str:
    """TDB 표기를 보통 표기로 바꾼다. 'SI' -> 'Si'"""
    return el.capitalize()


@dataclass
class PycalphadBackend:
    """pycalphad로 평형을 계산하는 엔진."""

    tdb_file: str
    base_element: str = "Nb"
    pressure_Pa: float = 101325.0
    phases: list[str] | None = None  # None이면 TDB의 모든 상 사용
    name: str = field(default="pycalphad", init=False)

    def __post_init__(self):
        from pycalphad import Database

        path = Path(self.tdb_file)
        if not path.exists():
            raise FileNotFoundError(f"TDB 파일이 없습니다: {path}")
        self.db = Database(str(path))
        self.base = _norm(self.base_element)
        if self.phases is None:
            self.phases = sorted(self.db.phases.keys())

    # ---- 정보 -------------------------------------------------------------
    def elements(self) -> list[str]:
        """TDB에 들어 있는 실제 원소 (VA, /- 같은 가상 성분 제외)"""
        return sorted(_pretty(e) for e in self.db.elements if e not in ("VA", "/-", "*"))

    # ---- 계산 -------------------------------------------------------------
    def _components(self, solutes: list[str]) -> list[str]:
        comps = [self.base] + solutes
        if "VA" in self.db.elements:
            comps.append("VA")
        return comps

    def equilibrium(self, composition: dict, temperatures_C) -> list[dict]:
        """한 조성에서 여러 온도를 한 번에 계산한다 (격자 계산 속도용).

        composition: {"Si": 16, "Ti": 22} (at.%, 나머지는 base_element)
        temperatures_C: 숫자 또는 숫자 목록
        반환: 온도마다 calc_equilibrium()과 같은 모양의 dict 목록
        """
        from pycalphad import equilibrium, variables as v

        temps = np.atleast_1d(np.asarray(temperatures_C, dtype=float))
        comp = {_norm(k): float(val) for k, val in composition.items() if _norm(k) != self.base}
        total = sum(comp.values())
        if total >= 100 or any(x < 0 for x in comp.values()):
            raise ValueError(f"조성이 잘못되었습니다 (합 {total} at.%): {composition}")
        missing = [e for e in comp if e not in self.db.elements]
        if missing:
            raise ValueError(f"TDB에 없는 원소: {missing}")

        solutes = sorted(comp)
        conds = {v.T: temps + KELVIN, v.P: self.pressure_Pa, v.N: 1}
        for el in solutes:
            # pycalphad는 조성이 정확히 0이면 불안정할 수 있어 아주 작은 값으로 바꾼다
            conds[v.X(el)] = max(comp[el] / 100.0, 1e-10)

        eq = equilibrium(self.db, self._components(solutes), self.phases, conds)

        # eq 배열 모양: (N, P, T, X1, X2, ..., vertex)  -> 온도 축만 남긴다
        phase_arr = eq.Phase.values.reshape(len(temps), -1)
        np_arr = eq.NP.values.reshape(len(temps), -1)
        comp_names = list(eq.component.values)
        x_arr = eq.X.values.reshape(len(temps), -1, len(comp_names))

        nominal = {_pretty(self.base): round(100 - total, 6)}
        nominal.update({_pretty(e): comp[e] for e in solutes})

        out = []
        for i, T in enumerate(temps):
            phases: dict[str, dict] = {}
            ok = True
            for j, ph in enumerate(phase_arr[i]):
                ph = str(ph)
                if not ph:
                    continue
                f = float(np_arr[i, j])
                if not np.isfinite(f):
                    ok = False
                    continue
                if f < 1e-6:
                    continue
                key = ph
                n = 2
                while key in phases:  # 같은 상이 두 번 나오면(혼화성 갭) 이름 뒤에 #2를 붙인다
                    key = f"{ph}#{n}"
                    n += 1
                phases[key] = {
                    "fraction": f,
                    "composition": {
                        _pretty(c): float(x_arr[i, j, k] * 100) for k, c in enumerate(comp_names)
                    },
                }
            fsum = sum(p["fraction"] for p in phases.values())
            if not phases or abs(fsum - 1) > 1e-3:
                ok = False
            out.append(
                {
                    "status": "ok" if ok else "failed",
                    "message": "" if ok else f"계산 미수렴 또는 상분율 합 이상 (합={fsum:.4f})",
                    "temperature_C": float(T),
                    "composition": nominal,
                    "phases": phases if ok else {},
                    "backend": self.name,
                    "tdb_file": str(self.tdb_file),
                }
            )
        return out


# ---- 엔진 선택 -------------------------------------------------------------
@lru_cache(maxsize=4)
def get_backend(tdb_file: str, base_element: str = "Nb", backend: str = "pycalphad"):
    """엔진을 만든다. 같은 TDB는 한 번만 읽도록 기억해 둔다."""
    if backend == "pycalphad":
        return PycalphadBackend(tdb_file=tdb_file, base_element=base_element)
    # 나중에: if backend == "thermocalc": return ThermoCalcBackend(...)
    raise NotImplementedError(f"아직 지원하지 않는 엔진: {backend}")


def calc_equilibrium(
    composition: dict,
    temperature_C: float,
    tdb_file: str,
    base_element: str = "Nb",
    backend: str = "pycalphad",
) -> dict:
    """조성(at.%)과 온도(°C)를 넣으면 평형 상과 상분율, 상별 조성을 돌려준다.

    반환 예:
    {
      "status": "ok",                     # 실패하면 "failed"
      "temperature_C": 1500.0,
      "composition": {"Nb": 84.0, "Si": 16.0},
      "phases": {"BCC_A2": {"fraction": 0.42, "composition": {"Nb": ..., "Si": ...}}, ...},
      "backend": "pycalphad", "tdb_file": "..."
    }
    fraction은 몰분율(0~1), composition은 at.%.
    """
    eng = get_backend(str(tdb_file), base_element, backend)
    return eng.equilibrium(composition, [temperature_C])[0]
