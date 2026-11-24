"""01: PLUTO attributes, block group, point position and lot shape.

Reads  data/original/nyc_mappluto_26v2_fgdb/MapPLUTO26v2.gdb (layer MapPLUTO_26v2_clipped)
Writes data/processed/lots.parquet      one row per lot, sorted by bbl (row = lot_index)
       data/processed/lot_geom.parquet  bbl + polygon WKB in EPSG:2263 feet
"""
import numpy as np, pandas as pd, pyogrio, shapely
from common import *

T = Timer("01_lots")
res = pyogrio.raw.read(PLUTO_GDB, layer=PLUTO_LAYER)
meta, geom_wkb, field_data = res[0], res[-2], res[-1]
names = list(meta["fields"])
print(f"read {len(geom_wkb):,} lots, {len(names)} fields, crs {meta.get('crs')}", flush=True)

need = ["BBL", "BCTCB2020", "Latitude", "Longitude", "LotArea", "BldgClass", "ZoneDist1"]
missing = [n for n in need if n not in names]
if missing:
    raise SystemExit(f"fields not found in the GDB: {missing}")

df = pd.DataFrame({n: v for n, v in zip(names, field_data)})
df.insert(0, "bbl", to_bbl(df["BBL"].to_numpy()))
geoms = shapely.from_wkb(geom_wkb)

if (df["bbl"] == 0).any():
    raise SystemExit(f"{int((df['bbl'] == 0).sum())} lots have no usable BBL")
if df["bbl"].duplicated().any():
    raise SystemExit(f"{int(df['bbl'].duplicated().sum())} duplicate BBLs")

order = np.argsort(df["bbl"].to_numpy(), kind="stable")
df = df.iloc[order].reset_index(drop=True)
geoms = geoms[order]

# Block group from BCTCB2020: boro(1) + tract(6) + block(4); block group = first digit of block.
code = df["BCTCB2020"].fillna("").astype(str).str.strip()
ok = (code.str.len() == 11) & code.str[0].isin(list(BORO_FIPS))
df["geoid"] = np.where(ok, code.str[0].map(BORO_FIPS).fillna("") + code.str[1:7] + code.str[7], "")
print(f"block group from BCTCB2020: {int(ok.sum()):,} lots, {int((~ok).sum()):,} without; "
      f"BCTCB2020 lengths among the rest: {code[~ok].str.len().value_counts().to_dict()}", flush=True)

# Point position: Latitude/Longitude, else the polygon centroid reprojected.
lat = pd.to_numeric(df["Latitude"], errors="coerce").to_numpy(dtype=np.float64, copy=True)
lon = pd.to_numeric(df["Longitude"], errors="coerce").to_numpy(dtype=np.float64, copy=True)
bad = ~np.isfinite(lat) | ~np.isfinite(lon) | (lat == 0) | (lon == 0)
cen = shapely.centroid(geoms[bad])
to_wgs = transformer("EPSG:2263", "EPSG:4326")
clon, clat = to_wgs.transform(shapely.get_x(cen), shapely.get_y(cen))
lon[bad], lat[bad] = clon, clat
df["lon"], df["lat"] = lon, lat
df["point_from_centroid"] = bad
x_ft, y_ft = transformer("EPSG:4326", "EPSG:2263").transform(lon, lat)
df["x_ft"], df["y_ft"] = x_ft, y_ft
print(f"point from polygon centroid: {int(bad.sum()):,} lots", flush=True)

# Lot shape in EPSG:2263 feet.
area = shapely.area(geoms)
perim = shapely.length(geoms)
df["poly_area"] = area
df["perimeter"] = perim
df["compactness"] = np.where(perim > 0, 4 * np.pi * area / np.maximum(perim, 1e-9) ** 2, np.nan)
df["n_vertices"] = shapely.get_num_coordinates(geoms)
df["block_key"] = df["bbl"] // 10000
df["borough_code"] = df["bbl"] // 1_000_000_000

df.to_parquet(p("lots.parquet"), index=False)
pd.DataFrame({"bbl": df["bbl"], "wkb": shapely.to_wkb(geoms)}).to_parquet(p("lot_geom.parquet"), index=False)
print(f"lots {len(df):,}; tax blocks {df['block_key'].nunique():,}; "
      f"distinct block groups {df.loc[df['geoid'] != '', 'geoid'].nunique():,}", flush=True)
T.done()
