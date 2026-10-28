"""Check: frontage_core.py reproduces the Queens sample in smt-fa2026's frontage_unshared_edge.py.

Run after 01_lots.py and BEFORE 02_frontage.py. Same selection as the original: Queens
blocks with 8+ one-to-two-family lots (BldgClass A or B) and at most 400 lots, 500 sampled
with seed 20260904; blocks with fewer than 4 lot geometries skipped; A/B lots measured.
The sample cannot be the identical 500 blocks (the original sampled in shapefile row order),
so agreement is "within sampling noise". Docstring numbers (2026-09-04, 13,670 lots):

    exactly one unshared edge 85.0%, two 10.7%, three or more 4.4%, none 0.5%
    median unshared share of perimeter 11.8%, frontage normal points out of block 97.4%
"""
from _check import *
import random
import numpy as np, pandas as pd, shapely
from frontage_core import compute_frontage

lots = pd.read_parquet(p("lots.parquet"), columns=["bbl", "block_key", "BldgClass"])
geom = pd.read_parquet(p("lot_geom.parquet"))
q = (lots["bbl"] // 1_000_000_000 == 4).to_numpy()
lots, geom = lots[q].reset_index(drop=True), geom[q].reset_index(drop=True)
isab = lots["BldgClass"].fillna("").astype(str).str[:1].isin(["A", "B"]).to_numpy()
byblock = {}
for i, b in enumerate(lots["block_key"].to_numpy()):
    byblock.setdefault(int(b), []).append(i)
elig = [b for b, v in byblock.items() if sum(1 for i in v if isab[i]) >= 8 and len(v) <= 400]
random.seed(20260904)
sample = random.sample(elig, min(500, len(elig)))
idx = np.array(sorted(i for b in sample for i in byblock[b]))
g = shapely.from_wkb(geom["wkb"].to_numpy()[idx])
ok = ~shapely.is_empty(g)
sizes = pd.Series(lots["block_key"].to_numpy()[idx][ok]).value_counts()
used_blocks = set(sizes[sizes >= 4].index)
f = compute_frontage(lots["block_key"].to_numpy()[idx], g, verbose=False)
m = isab[idx] & ok & lots["block_key"].iloc[idx].isin(used_blocks).to_numpy()
f = f[m]
nofree = (f["frontage_edges"] == 0) | (np.hypot(f["fx"], f["fy"]) < 1e-9)
r = f[~nofree]
n = len(r)
one = (r["frontage_edges"] == 1).mean()
two = (r["frontage_edges"] == 2).mean()
three = (r["frontage_edges"] >= 3).mean()
share = float(np.median(r["frontage_ft"] / r["edge_len_total"]))
out = float(r["front_out_of_block"].mean())

report("queens_lots", len(lots))
report("eligible_blocks", len(elig))
report("blocks_used", len(used_blocks))
report("one_two_family_lots_measured", n, 10_000 <= n <= 17_000, "docstring 13,670")
report("lots_with_no_free_edge", int(nofree.sum()), True, f"{nofree.mean():.1%}; docstring 65, 0.5%")
report("free_edges_1", f"{one:.1%}", abs(one - 0.850) <= 0.03, "docstring 85.0%, tolerance 3 pts")
report("free_edges_2", f"{two:.1%}", abs(two - 0.107) <= 0.03, "docstring 10.7%")
report("free_edges_3plus", f"{three:.1%}", abs(three - 0.044) <= 0.02, "docstring 4.4%")
report("median_free_perimeter_share", f"{share:.1%}", abs(share - 0.118) <= 0.02, "docstring 11.8%")
report("frontage_points_out_of_block", f"{out:.1%}", abs(out - 0.974) <= 0.02, "docstring 97.4%")
report("frontage_runs_1", f"{(r['frontage_runs'] == 1).mean():.1%}", True, "runs, not edges: for information")
finish("frontage_queens")
