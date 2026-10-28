"""06: the model input, plus one merged lot table in real units for the export.

PLUTO block (every variant): numeric fields (log1p for areas, counts and volumes, then
robust-scaled by median and IQR), each with a missing flag; categorical fields as integer
codes for embedding tables. ACS blocks are scaled across lots and multiplied by a weight so
their total variance is ACS_VARIANCE_WEIGHT times the PLUTO block's.

No location field goes into any block.

Reads  data/processed/lots.parquet, frontage.parquet, footprints.parquet, trees.parquet, acs_bg.parquet,
       acs_features.json
Writes data/processed/features.npz        num_<block>, miss_<block> (float32), cat (int64)
       data/processed/features.json       field lists, scalers, category levels, ACS weights
       data/processed/lot_table.parquet   every field in real units, lot_index order
"""
import json, re
import numpy as np, pandas as pd
from common import *

T = Timer("06_features")
lots = pd.read_parquet(p("lots.parquet"))
for f in ["frontage", "footprints", "trees"]:
    lots = lots.merge(pd.read_parquet(p(f"{f}.parquet")), on="bbl", how="left", validate="1:1")
acs = pd.read_parquet(p("acs_bg.parquet"))
acs_meta = json.load(open(p("acs_features.json")))["features"]
N = len(lots)
assert lots["bbl"].is_monotonic_increasing

# ---- numeric PLUTO block --------------------------------------------------------------------
AREAS = ["LotArea", "BldgArea", "ResArea", "ComArea", "OfficeArea", "RetailArea", "GarageArea",
         "StrgeArea", "FactryArea", "OtherArea"]
COUNTS = ["NumBldgs", "NumFloors", "UnitsRes", "UnitsTotal"]
LENGTHS = ["LotFront", "LotDepth", "BldgFront", "BldgDepth"]
FARS = ["BuiltFAR", "ResidFAR", "CommFAR", "FacilFAR"]
ZERO_IS_MISSING = {"YearBuilt", "NumFloors", "LotFront", "LotDepth", "BldgFront", "BldgDepth"}

for c in AREAS + COUNTS + LENGTHS + FARS + ["YearBuilt", "YearAlter1"]:
    lots[c] = pd.to_numeric(lots[c], errors="coerce")
    if c in ZERO_IS_MISSING:
        lots.loc[lots[c] == 0, c] = np.nan
lots["years_since_built"] = (CURRENT_YEAR - lots["YearBuilt"]).where(lots["YearBuilt"] > 0)
ya = lots["YearAlter1"]
lots["years_since_alter"] = (CURRENT_YEAR - ya).where(ya > 0)

# (field, transform, label, unit, group)
PLUTO_NUM = (
    [(c, "log1p", c, "sq ft", "PLUTO") for c in AREAS]
    + [(c, "log1p", c, "count", "PLUTO") for c in COUNTS]
    + [(c, "none", c, "ft", "PLUTO") for c in LENGTHS]
    + [("years_since_built", "none", "Years since built", "years", "PLUTO"),
       ("years_since_alter", "none", "Years since altered", "years", "PLUTO")]
    + [(c, "none", c, "ratio", "PLUTO") for c in FARS]
    + [("poly_area", "log1p", "Lot polygon area", "sq ft", "PLUTO"),
       ("perimeter", "none", "Lot perimeter", "ft", "PLUTO"),
       ("compactness", "none", "Lot compactness (4πA/P²)", "ratio", "PLUTO"),
       ("n_vertices", "log1p", "Lot vertex count", "count", "PLUTO")]
    + [("frontage_ft", "none", "Street frontage", "ft", "frontage"),
       ("frontage_runs", "log1p", "Frontage runs", "count", "frontage"),
       ("frontage_share", "none", "Frontage share of perimeter", "ratio", "frontage"),
       ("front_dir_sin", "none", "Frontage direction (sin)", "", "frontage"),
       ("front_dir_cos", "none", "Frontage direction (cos)", "", "frontage")]
    + [("n_footprints", "log1p", "Footprints", "count", "footprints"),
       ("footprint_area", "log1p", "Footprint area", "sq ft", "footprints"),
       ("coverage", "none", "Coverage", "ratio", "footprints"),
       ("height_max", "none", "Roof height (max)", "ft", "footprints"),
       ("height_mean", "none", "Roof height (area-weighted mean)", "ft", "footprints"),
       ("volume", "log1p", "Building volume", "cu ft", "footprints"),
       ("ground_elev", "none", "Ground elevation", "ft", "footprints")]
    + [("trees_n", "log1p", "Street trees", "count", "trees"),
       ("trees_per_100ft", "none", "Trees per 100 ft of frontage", "per 100 ft", "trees"),
       ("tree_dbh_mean", "none", "Mean tree diameter", "in", "trees"),
       ("tree_species_n", "log1p", "Tree species", "count", "trees")]
)


def robust(x):
    """log/none already applied. Returns scaled (missing -> 0), missing flag, scaler."""
    x = np.asarray(x, dtype=np.float64)
    miss = ~np.isfinite(x)
    v = x[~miss]
    med = float(np.median(v)) if v.size else 0.0
    q1, q3 = (np.percentile(v, [25, 75]) if v.size else (0.0, 1.0))
    iqr = float(q3 - q1)
    if iqr <= 0:
        iqr = float(np.std(v)) if v.size and np.std(v) > 0 else 1.0
    s = np.clip((x - med) / iqr, -SCALED_CLIP, SCALED_CLIP)
    s[miss] = 0.0
    return s.astype(np.float32), miss.astype(np.float32), {"median": med, "iqr": iqr}


def block(fields, frame):
    cols, flags, specs = [], [], []
    for name, tf, label, unit, group in fields:
        x = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=np.float64)
        if tf == "log1p":
            x = np.log1p(np.where(x >= 0, x, np.nan))
        s, m, sc = robust(x)
        cols.append(s)
        flags.append(m)
        specs.append({"field": name, "transform": tf, "label": label, "unit": unit, "group": group,
                      "missing_share": float(m.mean()), **sc})
    return np.stack(cols, 1), np.stack(flags, 1), specs


num_p, miss_p, spec_p = block(PLUTO_NUM, lots)

# ---- ACS blocks (per lot, via block group) ---------------------------------------------------
lots = lots.merge(acs.drop(columns=["name"]), on="geoid", how="left")
assert len(lots) == N
ACS_GROUPS = {}
for k, m in acs_meta.items():
    if m["group"] in ("housing", "cost", "demographic"):
        tf = "log1p" if k == "pop_density" else "none"
        unit = m.get("unit") or ("share" if m["kind"] == "share" else "")
        ACS_GROUPS.setdefault(m["group"], []).append((k, tf, m["label"], unit, "ACS " + m["group"]))

pluto_var = float(num_p.var(0).sum())
acs_blocks, acs_specs = {}, {}
for g, fields in ACS_GROUPS.items():
    x, m, s = block(fields, lots)
    acs_blocks[g] = (x, m)
    acs_specs[g] = s
weights = {}
for v, groups in VARIANT_ACS.items():
    if not groups:
        continue
    total = sum(float(acs_blocks[g][0].var(0).sum()) for g in groups)
    weights[v] = float(np.sqrt(ACS_VARIANCE_WEIGHT * pluto_var / total)) if total > 0 else 1.0

# ---- categorical block -----------------------------------------------------------------------
def s(c):
    return lots[c].astype("string").str.strip().replace("", pd.NA)


def zone_family(z):
    if z is None or z is pd.NA:
        return "missing"
    m = re.match(r"^([RCM]\d+)", z)
    return m.group(1) if m else z


cat_frame = pd.DataFrame({
    "LandUse": s("LandUse").str.zfill(2).fillna("missing"),
    "BldgClassLetter": s("BldgClass").str[0].fillna("missing"),
    "BldgClass": s("BldgClass").fillna("missing"),
    "ZoneFamily": s("ZoneDist1").map(zone_family, na_action="ignore").fillna("missing"),
    "LotType": s("LotType").fillna("missing"),
    "ProxCode": s("ProxCode").fillna("missing"),
    "IrrLotCode": s("IrrLotCode").fillna("missing"),
    "BsmtCode": s("BsmtCode").fillna("missing"),
    "Ext": s("Ext").fillna("missing"),
    "OwnerType": s("OwnerType").fillna("private/unknown"),
    "SplitZone": s("SplitZone").fillna("missing"),
    "InHistDist": s("HistDist").notna().map({True: "yes", False: "no"}),
    "Landmark": s("Landmark").notna().map({True: "yes", False: "no"}),
    "PFIRM15_FLAG": s("PFIRM15_FLAG").fillna("none"),
})
cat_codes, cat_specs = [], []
for c in cat_frame.columns:
    codes, levels = pd.factorize(cat_frame[c].astype(str), sort=True)
    cat_codes.append(codes)
    cat_specs.append({"field": c, "levels": [str(l) for l in levels], "n_levels": len(levels)})
cat = np.stack(cat_codes, 1).astype(np.int64)

arrays = {"num_pluto": num_p, "miss_pluto": miss_p, "cat": cat}
for g, (x, m) in acs_blocks.items():
    arrays[f"num_{g}"], arrays[f"miss_{g}"] = x, m
np.savez(p("features.npz"), **arrays)
write_json(p("features.json"), {
    "n_lots": N, "pluto_numeric": spec_p, "acs_numeric": acs_specs, "categorical": cat_specs,
    "pluto_total_variance": pluto_var, "acs_variance_target": ACS_VARIANCE_WEIGHT,
    "acs_weight": weights, "variant_acs_groups": VARIANT_ACS, "scaled_clip": SCALED_CLIP,
})

# ---- one table in real units for the export ----------------------------------------------------
keep = (["bbl", "geoid", "lon", "lat", "x_ft", "y_ft", "borough_code", "Address", "BldgClass", "LandUse",
         "ZoneDist1", "ZoneDist2", "OwnerType", "YearBuilt", "YearAlter1", "NumFloors", "UnitsRes", "tree_species"]
        + [f for f, *_ in PLUTO_NUM] + [f for g in ACS_GROUPS.values() for f, *_ in g])
lots.loc[:, list(dict.fromkeys(keep))].to_parquet(p("lot_table.parquet"), index=False)
print(f"lots {N:,}; PLUTO numeric {num_p.shape[1]}; categorical {cat.shape[1]}; "
      + "; ".join(f"ACS {g} {acs_blocks[g][0].shape[1]}" for g in acs_blocks)
      + f"; ACS weights {weights}", flush=True)
T.done()
