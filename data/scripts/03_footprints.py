"""03: building footprints per lot, and the 3D glyph geometry.

Streams the 1 GB GeoJSON line by line (one feature per line), reprojects to EPSG:2263 and
joins to lots on mappluto_bbl. Features use feature_code 2100 (building) and 5110 (garage);
every code is kept for the glyphs. height_roof null or 0 is missing, not 0.

Reads  data/original/footprints/BUILDING_20260830.geojson, data/processed/lots.parquet
Writes data/processed/footprints.parquet       per-lot features
       data/processed/footprint_geom.parquet   per footprint: bbl, feature_code, height, wkb (2263, simplified)
       data/processed/footprints_summary.json  counts for checks/check_footprints.py
"""
import json
import numpy as np, pandas as pd, shapely
from common import *

T = Timer("03_footprints")
PROPS = ["bin", "mappluto_bbl", "base_bbl", "feature_code", "height_roof", "ground_elevation",
         "construction_year", "last_status_type"]
CHUNK = 100_000

lots = pd.read_parquet(p("lots.parquet"), columns=["bbl", "LotArea"])
lot_bbls = lots["bbl"].to_numpy()
to_ft = transformer("EPSG:4326", "EPSG:2263")


def project(g):
    xy = shapely.get_coordinates(g)
    x, y = to_ft.transform(xy[:, 0], xy[:, 1])
    return shapely.set_coordinates(g, np.column_stack([x, y]))


rows, geo_strings, chunks, n_read, n_bad = [], [], [], 0, 0


def flush():
    global rows, geo_strings
    if not rows:
        return
    g = shapely.from_geojson(np.array(geo_strings, dtype=object), on_invalid="ignore")
    g = project(g)
    d = pd.DataFrame(rows, columns=PROPS)
    d["area"] = shapely.area(g)
    d["wkb"] = shapely.to_wkb(shapely.simplify(g, GLYPH_SIMPLIFY_FT, preserve_topology=True))
    chunks.append(d)
    rows, geo_strings = [], []
    print(f"  footprints {n_read:,}", flush=True)


with open(FOOTPRINTS, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s.startswith('{"type":"Feature"'):
            continue
        if s.endswith(","):
            s = s[:-1]
        n_read += 1
        i, j = s.find('"geometry":'), s.rfind(',"properties":')
        if i < 0 or j < 0:
            feat = json.loads(s)
            gs, props = json.dumps(feat["geometry"]), feat["properties"]
        else:
            gs, props = s[i + 11:j], json.loads(s[j + 14:-1])
        if gs.strip() == "null":
            n_bad += 1
            continue
        rows.append([props.get(k) for k in PROPS])
        geo_strings.append(gs)
        if len(rows) >= CHUNK:
            flush()
flush()

fp = pd.concat(chunks, ignore_index=True)
fp["bbl"] = to_bbl(fp["mappluto_bbl"].to_numpy())
fp["feature_code"] = pd.to_numeric(fp["feature_code"], errors="coerce").fillna(-1).astype(np.int32)
for c in ["height_roof", "ground_elevation"]:
    fp[c] = pd.to_numeric(fp[c], errors="coerce")
fp.loc[~(fp["height_roof"] > 0), "height_roof"] = np.nan
matched = np.isin(fp["bbl"].to_numpy(), lot_bbls)
print(f"read {n_read:,} features ({n_bad} without geometry); "
      f"{matched.mean():.2%} have a mappluto_bbl that is a 26v2 lot", flush=True)

fp_m = fp[matched].reset_index(drop=True)
fp_m[["bbl", "feature_code", "height_roof", "wkb"]].rename(columns={"height_roof": "height"}) \
    .to_parquet(p("footprint_geom.parquet"), index=False)

# Per-lot features from buildings (2100) and garages (5110).
b = fp_m[fp_m["feature_code"].isin([2100, 5110])].copy()
b["has_h"] = b["height_roof"].notna()
b["a_h"] = np.where(b["has_h"], b["area"], 0.0)
b["ah"] = np.where(b["has_h"], b["area"] * b["height_roof"], 0.0)
b["has_e"] = b["ground_elevation"].notna()
b["a_e"] = np.where(b["has_e"], b["area"], 0.0)
b["ae"] = np.where(b["has_e"], b["area"] * b["ground_elevation"], 0.0)
g = b.groupby("bbl").agg(n_footprints=("area", "size"), footprint_area=("area", "sum"),
                         height_max=("height_roof", "max"), a_h=("a_h", "sum"), ah=("ah", "sum"),
                         a_e=("a_e", "sum"), ae=("ae", "sum"))
g["height_mean"] = np.where(g["a_h"] > 0, g["ah"] / g["a_h"].clip(lower=1e-9), np.nan)
g["volume"] = np.where(g["a_h"] > 0, g["ah"], np.nan)
g["ground_elev"] = np.where(g["a_e"] > 0, g["ae"] / g["a_e"].clip(lower=1e-9), np.nan)

out = lots.merge(g.reset_index(), on="bbl", how="left")
out["n_footprints"] = out["n_footprints"].fillna(0).astype(np.int32)
out["footprint_area"] = out["footprint_area"].fillna(0.0)
la = pd.to_numeric(out["LotArea"], errors="coerce")
out["coverage"] = np.where(la > 0, (out["footprint_area"] / la.where(la > 0)).clip(upper=COVERAGE_CAP), np.nan)
cols = ["bbl", "n_footprints", "footprint_area", "coverage", "height_max", "height_mean", "volume", "ground_elev"]
out[cols].to_parquet(p("footprints.parquet"), index=False)

summary = {
    "features_read": n_read,
    "without_geometry": n_bad,
    "joined_to_lot": int(matched.sum()),
    "joined_share": float(matched.mean()),
    "lots_with_footprint_any_code": int(fp_m["bbl"].nunique()),
    "lots_with_building_or_garage": int((out["n_footprints"] > 0).sum()),
    "feature_codes": {str(k): int(v) for k, v in fp["feature_code"].value_counts().items()},
    "height_missing_or_zero": int(fp["height_roof"].isna().sum()),
}
write_json(p("footprints_summary.json"), summary)
print(json.dumps(summary, indent=1), flush=True)
T.done()
