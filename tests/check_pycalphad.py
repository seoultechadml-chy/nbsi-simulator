"""단계 0: pycalphad 동작 확인 (공식 예제와 같은 Al-Mg 이원 상태도).
pycalphad 패키지에 시험용으로 들어 있는 Al-Mg_Zhong.tdb를 사용한다. (Nb-Si와 무관)"""
import os, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pycalphad
from pycalphad import Database, binplot, equilibrium, variables as v

tdb = os.path.join(os.path.dirname(pycalphad.__file__), "tests", "databases", "Al-Mg_Zhong.tdb")
db = Database(tdb)
comps = ["AL", "MG", "VA"]
phases = list(db.phases.keys())
print("pycalphad", pycalphad.__version__, "| 상 목록:", phases)

eq = equilibrium(db, comps, phases, {v.X("MG"): 0.3, v.T: 700, v.P: 101325, v.N: 1})
ph = [p for p in eq.Phase.values.squeeze() if p]
fr = eq.NP.values.squeeze()[: len(ph)]
print("Al-30at%Mg, 700K 평형:", dict(zip(ph, fr.round(3))))

fig = plt.figure(figsize=(7, 5))
binplot(db, comps, phases, {v.X("MG"): (0, 1, 0.02), v.T: (300, 1000, 10), v.P: 101325, v.N: 1}, plot_kwargs={"ax": fig.gca()})
os.makedirs("tests/output", exist_ok=True)
fig.savefig("tests/output/AlMg_check.png", dpi=100)
print("상태도 저장: tests/output/AlMg_check.png")
