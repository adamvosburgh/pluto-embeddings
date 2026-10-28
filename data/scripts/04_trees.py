"""04: living street trees per lot, by nearest lot polygon within TREE_MAX_FT.

The census bbl field is not used for the assignment (it is the address the volunteer
recorded); it is kept only to report agreement in checks/check_trees.py.

Reads  data/original/trees/street_trees_2015.csv, data/processed/lot_geom.parquet, frontage.parquet
Writes data/processed/trees.parquet          per lot: trees_n, trees_per_100ft, tree_dbh_mean,
                                             tree_species_n, tree_species (common names, by count)
       data/processed/tree_assign.parquet    per living tree: tree_id, borocode, census_bbl, bbl, dist_ft
"""
import numpy as np, pandas as pd, shapely
from common import *

T = Timer("04_trees")
t = pd.read_csv(TREES, usecols=["tree_id", "status", "tree_dbh", "spc_latin", "spc_common",
                                "borocode", "x_sp", "y_sp", "bbl"], dtype={"bbl": str})
print(f"tree records {len(t):,}: {t['status'].value_counts(dropna=False).to_dict()}", flush=True)
t = t[t["status"] == "Alive"].reset_index(drop=True)

geom = pd.read_parquet(p("lot_geom.parquet"))
lot_bbl = geom["bbl"].to_numpy()
tree_idx = shapely.STRtree(shapely.from_wkb(geom["wkb"].to_numpy()))
pts = shapely.points(t["x_sp"].to_numpy(dtype=float), t["y_sp"].to_numpy(dtype=float))
(ti, li), dist = tree_idx.query_nearest(pts, max_distance=TREE_MAX_FT, return_distance=True, all_matches=False)
assign = np.full(len(t), -1, np.int64)
dd = np.full(len(t), np.nan)
assign[ti], dd[ti] = li, dist

a = pd.DataFrame({"tree_id": t["tree_id"], "borocode": t["borocode"],
                  "census_bbl": to_bbl(t["bbl"].to_numpy()),
                  "bbl": np.where(assign >= 0, lot_bbl[np.maximum(assign, 0)], 0), "dist_ft": dd})
a.to_parquet(p("tree_assign.parquet"), index=False)
print(f"living {len(t):,}; assigned within {TREE_MAX_FT:g} ft {int((assign >= 0).sum()):,}; "
      f"unassigned {int((assign < 0).sum()):,}", flush=True)

ta = t.assign(bbl=a["bbl"])[a["bbl"] > 0]
ta["dbh"] = pd.to_numeric(ta["tree_dbh"], errors="coerce").where(lambda s: s > 0)
ta["species"] = ta["spc_common"].fillna(ta["spc_latin"])
g = ta.groupby("bbl").agg(trees_n=("tree_id", "size"), tree_dbh_mean=("dbh", "mean"),
                          tree_species_n=("spc_latin", "nunique"))
sp = ta.dropna(subset=["species"]).groupby(["bbl", "species"]).size().reset_index(name="n") \
    .sort_values(["bbl", "n"], ascending=[True, False]).groupby("bbl")["species"].agg(list)

fr = pd.read_parquet(p("frontage.parquet"), columns=["bbl", "frontage_ft"])
out = fr.merge(g.reset_index(), on="bbl", how="left")
out["trees_n"] = out["trees_n"].fillna(0).astype(np.int32)
out["tree_species_n"] = out["tree_species_n"].fillna(0).astype(np.int32)
out["trees_per_100ft"] = np.where(out["frontage_ft"] > 0, out["trees_n"] / out["frontage_ft"].where(out["frontage_ft"] > 0) * 100, np.nan)
out["tree_species"] = out["bbl"].map(sp)
out.drop(columns=["frontage_ft"]).to_parquet(p("trees.parquet"), index=False)
T.done()
