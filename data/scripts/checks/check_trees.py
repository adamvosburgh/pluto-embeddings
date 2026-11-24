"""Check: living street trees assigned to the nearest lot (after 04_trees.py)."""
from _check import *
import numpy as np, pandas as pd

a = pd.read_parquet(p("tree_assign.parquet"))
assigned = a["bbl"] > 0
report("alive", len(a), len(a) == 652_173)
report("assigned_within_60ft", int(assigned.sum()), True, f"{assigned.mean():.2%}")
report("unassigned", int((~assigned).sum()))
d = a.loc[assigned, "dist_ft"]
report("distance_percentiles_ft", {q: round(float(np.percentile(d, q)), 1) for q in (25, 50, 75, 90, 99)})
agree = (a["census_bbl"] == a["bbl"])[assigned]
report("census_bbl_agreement_citywide", f"{agree.mean():.1%}")
bx = assigned & (a["borocode"] == 2)
bx_agree = float((a["census_bbl"] == a["bbl"])[bx].mean())
report("census_bbl_agreement_bronx", f"{bx_agree:.1%}", abs(bx_agree - 0.66) <= 0.05, "doc: near 66%")
report("bronx_living_trees", int((a["borocode"] == 2).sum()), int((a["borocode"] == 2).sum()) == 80_585)
finish("trees")
