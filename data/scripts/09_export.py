"""09: files for the browser, in web/public/data/. Little-endian, lot_index order.

lots.bin                   columnar: bbl float64[N] | lon float32[N] | lat float32[N] | bg_index uint16[N]
fields.bin or fields_<group>.bin
                           columnar uint16[N] per field, 65535 = missing; value = min + q * scale
layout_<variant>.bin       float32[N*3] interleaved x,y,z
latent_<variant>.bin       int8[N*16] interleaved; value = q * scale[dim]
acs_bg.json                {columns, rows}; row i is bg_index i
details/<shard>.json       1,000 lots per shard
glyphs/<shard>.bin         1,000 lots per shard, CSR layout described in manifest.glyphs
manifest.json              every file, field, unit, scale and source
"""
import glob, json, os, shutil
import numpy as np, pandas as pd, shapely
from common import *
from codes import all_codes

T = Timer("09_export")
OUT = WEB_DATA
for d in ("details", "glyphs"):
    shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
    os.makedirs(os.path.join(OUT, d), exist_ok=True)
for f in glob.glob(os.path.join(OUT, "*.bin")):
    os.remove(f)

lt = pd.read_parquet(p("lot_table.parquet"))
N = len(lt)
feat = json.load(open(p("features.json")))
acs_meta = json.load(open(p("acs_features.json")))["features"]
diag = json.load(open(p("diagnostics.json")))
variants = [v for v in VARIANTS if os.path.exists(p(f"layout_{v}.npy"))]
SHARD = 1000
files = {}


def write(name, arr):
    arr = np.ascontiguousarray(arr)
    with open(os.path.join(OUT, name), "wb") as f:
        f.write(arr.astype(arr.dtype.newbyteorder("<"), copy=False).tobytes())
    files[name] = os.path.getsize(os.path.join(OUT, name))


# ---- block groups ------------------------------------------------------------------------
acs = pd.read_parquet(p("acs_bg.parquet")).sort_values("geoid").reset_index(drop=True)
bg_pos = pd.Series(np.arange(len(acs)), index=acs["geoid"])
bg_index = lt["geoid"].map(bg_pos).fillna(65535).astype(np.uint16).to_numpy()
acs_cols = [k for k, m in acs_meta.items()]


def rnd(x, nd=4):
    return None if x is None or not np.isfinite(x) else float(f"{x:.{nd}g}")


with open(os.path.join(OUT, "acs_bg.json"), "w", encoding="utf-8") as f:
    json.dump({"columns": ["geoid", "name"] + acs_cols,
               "rows": [[r["geoid"], r["name"]] + [rnd(r[c]) for c in acs_cols] for _, r in acs.iterrows()]},
              f, separators=(",", ":"))
files["acs_bg.json"] = os.path.getsize(os.path.join(OUT, "acs_bg.json"))

# ---- lots.bin ----------------------------------------------------------------------------
lots_bin = np.concatenate([lt["bbl"].to_numpy(np.float64).view(np.uint8),
                           lt["lon"].to_numpy(np.float32).view(np.uint8),
                           lt["lat"].to_numpy(np.float32).view(np.uint8),
                           bg_index.view(np.uint8)])
write("lots.bin", lots_bin)

# ---- fields --------------------------------------------------------------------------------
FIELD_DEFS = [("lon", "Longitude", "°", "PLUTO"), ("lat", "Latitude", "°", "PLUTO"),
              ("YearBuilt", "Year built", "year", "PLUTO"), ("YearAlter1", "Year altered", "year", "PLUTO")]
for s in feat["pluto_numeric"]:
    if s["field"] not in ("years_since_built", "years_since_alter"):
        FIELD_DEFS.append((s["field"], s["label"], s["unit"], s["group"]))
for g, specs in feat["acs_numeric"].items():
    for s in specs:
        FIELD_DEFS.append((s["field"], s["label"], s["unit"], "ACS " + g))
clusters = {v: np.load(p(f"clusters_{v}.npy")) for v in variants}
for v in variants:
    FIELD_DEFS.append((f"cluster_{v}", f"Cluster ({VARIANT_LABELS[v]})", "", "embedding"))


def values(key):
    if key.startswith("cluster_"):
        return clusters[key[8:]].astype(np.float64)
    x = pd.to_numeric(lt[key], errors="coerce").to_numpy(np.float64)
    if key == "YearAlter1":
        x = np.where(x > 0, x, np.nan)
    return x


def quantize(x):
    ok = np.isfinite(x)
    if not ok.any():
        return np.full(len(x), 65535, np.uint16), 0.0, 0.0, 1.0
    lo, hi = float(x[ok].min()), float(x[ok].max())
    integer = np.all(x[ok] == np.round(x[ok])) and hi - lo <= 65534
    scale = 1.0 if integer else max((hi - lo) / 65534, 1e-12)
    q = np.full(len(x), 65535, np.uint16)
    q[ok] = np.clip(np.rint((x[ok] - lo) / scale), 0, 65534).astype(np.uint16)
    return q, lo, hi, scale


GROUP_ORDER = ["PLUTO", "footprints", "frontage", "trees", "ACS housing", "ACS cost", "ACS demographic", "embedding"]
total = len(FIELD_DEFS) * N * 2
split = total > 60 * 1024 * 1024
field_meta, by_file = [], {}
for key, label, unit, group in FIELD_DEFS:
    q, lo, hi, scale = quantize(values(key))
    fname = f"fields_{group.lower().replace(' ', '_')}.bin" if split else "fields.bin"
    by_file.setdefault(fname, []).append(q)
    field_meta.append({"key": key, "label": label, "unit": unit, "group": group, "file": fname,
                       "offset": (len(by_file[fname]) - 1) * N * 2, "min": lo, "max": hi, "scale": scale,
                       "missing": 65535})
for fname, cols in by_file.items():
    write(fname, np.concatenate(cols))
print(f"fields: {len(field_meta)}, {total / 1e6:,.1f} MB, split by group: {split}", flush=True)

# ---- layouts and latents ---------------------------------------------------------------------
latent_scale, train = {}, {}
for v in variants:
    write(f"layout_{v}.bin", np.load(p(f"layout_{v}.npy")).astype(np.float32).ravel())
    lat = np.load(p(f"latent_{v}.npy"))
    sc = np.abs(lat).max(0) / 127
    sc[sc == 0] = 1
    write(f"latent_{v}.bin", np.clip(np.rint(lat / sc), -127, 127).astype(np.int8).ravel())
    latent_scale[v] = sc.tolist()
    t = json.load(open(p(f"train_{v}.json")))
    train[v] = {"held_out_total": t["held_out_total"], "baseline_total": t["baseline_total"], "settings": t["settings"]}

# ---- details shards ----------------------------------------------------------------------
def clean(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if not np.isfinite(v) else round(float(v), 2)
    if isinstance(v, np.ndarray):
        return [str(s) for s in v]
    return v


det_cols = {"bbl": "bbl", "Address": "address", "BldgClass": "bldgclass", "LandUse": "landuse",
            "ZoneDist1": "zone1", "ZoneDist2": "zone2", "OwnerType": "ownertype", "YearBuilt": "yearbuilt",
            "NumFloors": "floors", "UnitsRes": "unitsres", "frontage_ft": "frontage_ft", "trees_n": "trees_n",
            "height_max": "height_max", "tree_species": "species"}
det = lt[list(det_cols)].rename(columns=det_cols)
recs = det.to_dict("records")
for s in range(0, N, SHARD):
    with open(os.path.join(OUT, "details", f"{s // SHARD}.json"), "w", encoding="utf-8") as f:
        json.dump([{k: clean(v) for k, v in r.items()} for r in recs[s:s + SHARD]], f, separators=(",", ":"))

# ---- glyph shards ------------------------------------------------------------------------
Q = GLYPH_QUANT_FT
px, py = lt["x_ft"].to_numpy(), lt["y_ft"].to_numpy()
lg = pd.read_parquet(p("lot_geom.parquet"))
lot_g = shapely.simplify(shapely.from_wkb(lg["wkb"].to_numpy()), GLYPH_SIMPLIFY_FT, preserve_topology=True)
parts, part_lot = shapely.get_parts(lot_g, return_index=True)
rings, ring_part = shapely.get_rings(parts, return_index=True)
o_ring_lot = part_lot[ring_part]
o_xy, o_cr = shapely.get_coordinates(rings, return_index=True)

fpg = pd.read_parquet(p("footprint_geom.parquet"))
fp_lot = np.searchsorted(lt["bbl"].to_numpy(), fpg["bbl"].to_numpy())
order = np.argsort(fp_lot, kind="stable")
fpg, fp_lot = fpg.iloc[order].reset_index(drop=True), fp_lot[order]
fparts, fpart_fp = shapely.get_parts(shapely.from_wkb(fpg["wkb"].to_numpy()), return_index=True)
poly_lot = fp_lot[fpart_fp]
h = fpg["height"].to_numpy()[fpart_fp]
poly_h = np.where(np.isfinite(h), np.clip(np.rint(h * 10), 0, 65534), 65535).astype(np.uint16)
frings, fring_poly = shapely.get_rings(fparts, return_index=True)
f_xy, f_cr = shapely.get_coordinates(frings, return_index=True)


def rel(xy, lot_of_coord):
    return np.rint(np.column_stack([xy[:, 0] - px[lot_of_coord], xy[:, 1] - py[lot_of_coord]]) / Q)


o_q = rel(o_xy, o_ring_lot[o_cr])
f_q = rel(f_xy, poly_lot[fring_poly[f_cr]])
too_big = np.zeros(N, bool)
np.logical_or.at(too_big, o_ring_lot[o_cr], np.abs(o_q).max(1) > 32767)
np.logical_or.at(too_big, poly_lot[fring_poly[f_cr]], np.abs(f_q).max(1) > 32767)
print(f"glyphs: {int(too_big.sum())} lots dropped, extent beyond int16 at {Q} ft", flush=True)

keep_r = ~too_big[o_ring_lot]
keep_c = keep_r[o_cr]
o_ring_lot, o_q, o_cr = o_ring_lot[keep_r], o_q[keep_c].astype(np.int16), np.cumsum(keep_r)[o_cr[keep_c]] - 1
keep_p = ~too_big[poly_lot]
keep_fr = keep_p[fring_poly]
keep_fc = keep_fr[f_cr]
pnew = np.cumsum(keep_p) - 1
poly_lot, poly_h = poly_lot[keep_p], poly_h[keep_p]
fring_poly = pnew[fring_poly[keep_fr]]
f_q, f_cr = f_q[keep_fc].astype(np.int16), np.cumsum(keep_fr)[f_cr[keep_fc]] - 1

lot_ring_start = np.searchsorted(o_ring_lot, np.arange(N + 1))
ring_coord_start = np.searchsorted(o_cr, np.arange(len(o_ring_lot) + 1))
lot_poly_start = np.searchsorted(poly_lot, np.arange(N + 1))
poly_ring_start = np.searchsorted(fring_poly, np.arange(len(poly_lot) + 1))
fring_coord_start = np.searchsorted(f_cr, np.arange(len(fring_poly) + 1))

for s in range(0, N, SHARD):
    e = min(s + SHARD, N)
    r0, r1 = lot_ring_start[s], lot_ring_start[e]
    oc0, oc1 = ring_coord_start[r0], ring_coord_start[r1]
    p0, p1 = lot_poly_start[s], lot_poly_start[e]
    fr0, fr1 = poly_ring_start[p0], poly_ring_start[p1]
    fc0, fc1 = fring_coord_start[fr0], fring_coord_start[fr1]
    heights = poly_h[p0:p1]
    pad = np.zeros((len(heights) % 2), np.uint16)
    parts_out = [
        np.array([e - s, r1 - r0, oc1 - oc0, p1 - p0, fr1 - fr0, fc1 - fc0, 0, 0], np.int32),
        (lot_ring_start[s:e + 1] - r0).astype(np.int32),
        (ring_coord_start[r0:r1 + 1] - oc0).astype(np.int32),
        (lot_poly_start[s:e + 1] - p0).astype(np.int32),
        (poly_ring_start[p0:p1 + 1] - fr0).astype(np.int32),
        (fring_coord_start[fr0:fr1 + 1] - fc0).astype(np.int32),
        heights, pad, o_q[oc0:oc1].ravel(), f_q[fc0:fc1].ravel(),
    ]
    with open(os.path.join(OUT, "glyphs", f"{s // SHARD}.bin"), "wb") as f:
        for a in parts_out:
            f.write(np.ascontiguousarray(a).astype(a.dtype.newbyteorder("<")).tobytes())

# ---- manifest ------------------------------------------------------------------------------
med_cols = [k for k, m in acs_meta.items() if m["group"] == "median"]
manifest = {
    "version": 1,
    "n_lots": N,
    "lot_order": "sorted by bbl; position = lot_index",
    "lots": {"file": "lots.bin", "columns": [
        {"key": "bbl", "type": "float64", "offset": 0},
        {"key": "lon", "type": "float32", "offset": N * 8},
        {"key": "lat", "type": "float32", "offset": N * 12},
        {"key": "bg_index", "type": "uint16", "offset": N * 16, "missing": 65535}]},
    "fields": field_meta,
    "field_groups": [g for g in GROUP_ORDER if any(f["group"] == g for f in field_meta)],
    "variants": [{"key": v, "label": VARIANT_LABELS[v], "acs_groups": VARIANT_ACS[v],
                  "layout": f"layout_{v}.bin", "latent": f"latent_{v}.bin", "latent_scale": latent_scale[v],
                  "cluster_field": f"cluster_{v}", "diagnostics": diag["variants"][v], "training": train[v]}
                 for v in variants],
    "latent_dim": LATENT_DIM,
    "k_clusters": K_CLUSTERS,
    "acs_bg": {"file": "acs_bg.json", "medians": med_cols,
               "labels": {k: {"label": m["label"], "unit": m.get("unit") or ("share" if m["kind"] == "share" else ""),
                              "group": m["group"]} for k, m in acs_meta.items()}},
    "details": {"dir": "details", "shard_size": SHARD},
    "glyphs": {"dir": "glyphs", "shard_size": SHARD, "quant_ft": Q, "simplify_ft": GLYPH_SIMPLIFY_FT,
               "height_unit_ft": 0.1, "height_missing": 65535, "dropped_lots": int(too_big.sum()),
               "layout": "int32 header[8] = n_lots, n_outline_rings, n_outline_coords, n_polys, n_poly_rings, "
                         "n_poly_coords, 0, 0; int32 lot_ring_start[n_lots+1]; int32 ring_coord_start[n_outline_rings+1]; "
                         "int32 lot_poly_start[n_lots+1]; int32 poly_ring_start[n_polys+1]; "
                         "int32 poly_ring_coord_start[n_poly_rings+1]; uint16 poly_height[n_polys] (+1 pad if odd); "
                         "int16 outline_xy[2*n_outline_coords]; int16 poly_xy[2*n_poly_coords]. "
                         "Coordinates are EPSG:2263 feet relative to the lot point, divided by quant_ft."},
    "codes": all_codes(),
    "sources": {
        "pluto": "MapPLUTO 26v2 (NYC DCP), layer MapPLUTO_26v2_clipped",
        "footprints": "NYC Building Footprints, NYC Open Data 5zhs-2jue, downloaded 2026-08-30",
        "trees": "2015 Street Tree Census, NYC Open Data uvpi-gqnh",
        "acs": "ACS 2020–2024 5-year, block group detailed tables (Census API)",
        "acs_area": "GEOINFO2024 AREALAND",
    },
    "settings": {"seed": SEED, "tree_max_ft": TREE_MAX_FT, "coverage_cap": COVERAGE_CAP,
                 "acs_variance_weight": ACS_VARIANCE_WEIGHT, "umap": diag["umap"], "k": K_CLUSTERS},
}
write_json(os.path.join(OUT, "manifest.json"), manifest)
files["manifest.json"] = os.path.getsize(os.path.join(OUT, "manifest.json"))

emb_file = next(f["file"] for f in field_meta if f["key"] == "cluster_pluto")
first = ["manifest.json", "lots.bin", "layout_pluto.bin", "latent_pluto.bin", emb_file]
first_bytes = sum(files[f] for f in first)
write_json(p("export_summary.json"), {"files": files, "first_load": first, "first_load_bytes": first_bytes,
                                       "glyphs_dropped": int(too_big.sum())})
for k, v in sorted(files.items()):
    print(f"  {k:32s} {v / 1e6:9.2f} MB", flush=True)
print(f"first load: {first_bytes / 1e6:,.1f} MB ({', '.join(first)})", flush=True)
T.done()
