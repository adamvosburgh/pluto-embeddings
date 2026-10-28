"""02: street frontage per lot by the unshared-edge method (frontage_core.py), citywide.

Run checks/check_frontage_queens.py first: it runs the same code on the Queens sample.

Reads  data/processed/lots.parquet, lot_geom.parquet
Writes data/processed/frontage.parquet  bbl, frontage_ft, frontage_runs, frontage_edges,
       frontage_share, front_dir_sin, front_dir_cos, front_out_of_block
"""
import numpy as np, pandas as pd, shapely
from common import *
from frontage_core import compute_frontage

T = Timer("02_frontage")
lots = pd.read_parquet(p("lots.parquet"), columns=["bbl", "block_key", "perimeter"])
geom = pd.read_parquet(p("lot_geom.parquet"))
assert (geom["bbl"].to_numpy() == lots["bbl"].to_numpy()).all()
geoms = shapely.from_wkb(geom["wkb"].to_numpy())

f = compute_frontage(lots["block_key"].to_numpy(), geoms)
out = pd.DataFrame({
    "bbl": lots["bbl"],
    "frontage_ft": f["frontage_ft"].to_numpy(),
    "frontage_runs": f["frontage_runs"].to_numpy(),
    "frontage_edges": f["frontage_edges"].to_numpy(),
    "frontage_share": np.where(lots["perimeter"] > 0, f["frontage_ft"] / lots["perimeter"].clip(lower=1e-9), np.nan),
    "front_dir_sin": f["front_dir_sin"].to_numpy(),
    "front_dir_cos": f["front_dir_cos"].to_numpy(),
    "front_out_of_block": f["front_out_of_block"].to_numpy(),
})
out.to_parquet(p("frontage.parquet"), index=False)
r = out["frontage_runs"]
print(f"no frontage {int((r == 0).sum()):,}  one run {int((r == 1).sum()):,}  "
      f"two+ runs {int((r >= 2).sum()):,}  median frontage {out['frontage_ft'].median():.1f} ft", flush=True)
T.done()
