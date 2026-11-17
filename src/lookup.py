"""phase_grid.csv에서 슬라이더 값의 상분율을 보간(사이값 추정)해 꺼낸다.

화면에서 슬라이더를 움직일 때마다 열역학 계산을 다시 돌리지 않고,
미리 계산해 둔 격자 점들 사이를 직선으로 이어 값을 구한다.

주의: 상 경계 근처에서는 격자 간격(예: 0.5 at.%) 정도의 오차가 생길 수 있다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree


def base_phase(name: str) -> str:
    """'BCC_A2#2' -> 'BCC_A2' (같은 상이 두 개로 나뉜 경우 합쳐서 보여 준다)"""
    return name.split("#")[0]


class PhaseGrid:
    def __init__(self, csv_path):
        self.path = Path(csv_path)
        df = pd.read_csv(self.path)
        meta_file = self.path.with_name(self.path.stem + "_meta.json")
        self.meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}

        xcols = [c for c in df.columns if c.startswith("x_")]
        self.all_elements = [c[2:] for c in xcols]  # base 원소 포함
        idx = df.columns.get_loc("T_C")
        self.elements = list(df.columns[:idx])  # 슬라이더로 움직이는 원소
        self.base = self.meta.get("base_element") or [e for e in self.all_elements if e not in self.elements][0]
        self.raw = df
        self.axes_names = self.elements + ["T_C"]

        df = df.assign(phase=df["phase"].map(base_phase))
        wide = df.pivot_table(index=self.axes_names, columns="phase", values="fraction", aggfunc="sum").fillna(0.0)
        self.phases = list(wide.columns)
        self.wide = wide

        # 규칙 격자 배열 만들기 (빈 점은 NaN)
        self.axes = [np.array(sorted(wide.index.get_level_values(n).unique()), dtype=float) for n in self.axes_names]
        shape = [len(a) for a in self.axes]
        self.values = np.full(shape + [len(self.phases)], np.nan)
        pos = [np.searchsorted(a, wide.index.get_level_values(n).to_numpy(float)) for a, n in zip(self.axes, self.axes_names)]
        self.values[tuple(pos)] = wide.to_numpy()

        # 축이 1개 점뿐이면 보간기가 다룰 수 없으므로 그 축은 고정값으로 처리
        self._live = [i for i, a in enumerate(self.axes) if len(a) > 1]
        self._interp = RegularGridInterpolator(
            [self.axes[i] for i in self._live],
            self.values.reshape([shape[i] for i in self._live] + [len(self.phases)]),
            bounds_error=False,
            fill_value=np.nan,
        )
        # NaN(실패 점) 근처용 최근접 점 찾기
        valid = wide.index.to_frame().to_numpy(float)
        self._scale = np.array([max(np.ptp(a), 1e-9) for a in self.axes])
        self._tree = cKDTree(valid / self._scale)
        self._valid_vals = wide.to_numpy()

    # ---- 범위 -------------------------------------------------------------
    def bounds(self) -> dict:
        return {n: (float(a.min()), float(a.max())) for n, a in zip(self.axes_names, self.axes)}

    def _point(self, composition: dict, T_C: float) -> np.ndarray:
        return np.array([float(composition.get(e, 0.0)) for e in self.elements] + [float(T_C)])

    def in_range(self, composition: dict, T_C: float) -> bool:
        p = self._point(composition, T_C)
        return all(lo - 1e-9 <= x <= hi + 1e-9 for x, (lo, hi) in zip(p, self.bounds().values()))

    # ---- 상분율 -----------------------------------------------------------
    def fractions(self, composition: dict, T_C: float) -> dict:
        """보간한 상분율 {상이름: 0~1}. 범위 밖이면 빈 dict."""
        if not self.in_range(composition, T_C):
            return {}
        p = self._point(composition, T_C)
        v = self._interp(p[self._live][None, :])[0]
        if np.any(~np.isfinite(v)):  # 주변에 실패 점이 있으면 가장 가까운 정상 점을 쓴다
            _, j = self._tree.query(p / self._scale)
            v = self._valid_vals[j]
        v = np.clip(v, 0, None)
        s = v.sum()
        if s <= 0:
            return {}
        v = v / s
        return {ph: float(f) for ph, f in zip(self.phases, v) if f > 1e-4}

    def phase_compositions(self, composition: dict, T_C: float) -> dict:
        """가장 가까운 격자 점의 상별 조성 {상이름: {원소: at.%}} (보간하지 않음)."""
        p = self._point(composition, T_C)
        _, j = self._tree.query(p / self._scale)
        key = self.wide.index[j]
        sel = self.raw
        for n, val in zip(self.axes_names, key):
            sel = sel[np.isclose(sel[n], val)]
        out = {}
        for _, r in sel.iterrows():
            out[r["phase"]] = {e: float(r[f"x_{e}"]) for e in self.all_elements}
        return out

    def curve(self, element: str, composition: dict, T_C: float, n: int = 201) -> pd.DataFrame:
        """element 하나만 범위 전체로 바꿔 가며 상분율을 구한 표 (가로축 곡선용)."""
        lo, hi = self.bounds()[element]
        xs = np.linspace(lo, hi, n)
        rows = []
        for x in xs:
            c = dict(composition)
            c[element] = x
            f = self.fractions(c, T_C)
            rows.append({element: x, **{ph: f.get(ph, 0.0) for ph in self.phases}})
        return pd.DataFrame(rows)

    def section(self, element: str, composition: dict) -> pd.DataFrame:
        """상태도 그림용: element-온도 단면의 격자 점별 상 조합 (보간 없이 원자료)."""
        df = self.raw.copy()
        for e in self.elements:
            if e != element:
                df = df[np.isclose(df[e], composition.get(e, 0.0))]
        df = df.assign(phase=df["phase"].map(base_phase))
        return (
            df[df["fraction"] > 1e-4]
            .groupby([element, "T_C"])["phase"]
            .apply(lambda s: " + ".join(sorted(set(s))))
            .reset_index(name="phase_set")
        )
