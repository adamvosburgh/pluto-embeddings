---
title: Build Doc — PLUTO Embeddings
date: 2026-10-28
type: build-doc
---

# Build Doc — PLUTO Embeddings

For Claude Code. Repo `pluto-embeddings`. Written 2026-10-28 in Cowork, after a feasibility pass with Adam the same day.

This is an experimental prototype. Every tax lot in New York City is described by its PLUTO record, its buildings, its street frontage and street trees, and, in some versions, the ACS figures for its block group. A small PyTorch autoencoder turns each lot into a short vector (an embedding). A 3D browser view shows the lots as points that can be arranged by embedding, by any two or three fields, or on a map. Later it will be folded into a sandbox on the course site (`smt-fa2026`). For now it lives only in this repo.

Counts and field names below were read from the files on disk on 2026-10-28. Where a number is a choice rather than a fact, it is marked as a placeholder.

## 0. Read first, and working rules

- `data/scripts/fetch_sources.py` (what was downloaded and from where) and `data/original/fetch_log.txt`.
- `data/original/nyc_mappluto_26v2_fgdb/pluto_datadictionary.pdf` for field meanings and codes.
- In the course repo, `smt-fa2026/data/scripts/checks/frontage_unshared_edge.py`. Its docstring describes the frontage method used in §3.2 and the numbers a reimplementation should reproduce.
- In the course repo, `smt-fa2026/package.json`, for the library versions to match (§5.1).

Working rules:

- Please do not `git commit` or `git push`. Leave your changes in the working tree and list what changed.
- Please do not invent data: no made-up figure, field name, URL or dataset. If something here turns out to be wrong on disk, stop and say so in the summary.
- American English in every string, comment and identifier.
- Kill any dev server you start.
- Every prose file you write is a draft. First line: `<!-- PROSE DRAFT: written for accuracy, not voice. Rewrite against the style guide. -->`
- Nothing is fetched at build time. Everything needed is already in `data/original/`.

## 1. Decisions already made with Adam

| topic | decision |
|---|---|
| unit | One point per tax lot, all 856,687 lots kept, including vacant lots, parks and lots with no building. |
| ACS geography | Block group detailed tables (B25 housing, B01/B02/B03 demographic), ACS 2020–2024 5-year. Tract DP04/DP05 are on disk for comparison only. |
| join | No spatial join. Block group comes from PLUTO's `BCTCB2020` (§3.1). |
| embedding variants | Four, each trained separately: PLUTO only, PLUTO + ACS housing, PLUTO + ACS demographic, PLUTO + both. "PLUTO" here includes the footprint, frontage and tree features. |
| location | No location fields go into any embedding (no lat/lon, borough, district or tract fields). Location is only used to place points on the map. |
| model | Plain PyTorch autoencoder. No text-embedding model. |
| ACS uncertainty | Use estimates as they are. Show one short note when an ACS variant is on (§6). |
| trees | 2015 Street Tree Census. Trees per lot frontage. No separate tree embedding. |
| map | MapLibre basemap under deck.gl. No Cesium, no Google 3D tiles. |
| views | Embedding view, custom-axes view, map view, a year-built preset, "lots like this one" with distance coloring, switching between the four variants. |

## 2. Data on disk (verified 2026-10-28)

All under `data/original/` (gitignored).

| path | what | facts |
|---|---|---|
| `nyc_mappluto_26v2_fgdb/MapPLUTO26v2.gdb` | MapPLUTO 26v2, one layer `MapPLUTO_26v2_clipped` | 856,687 lots, MultiPolygon, EPSG:2263 (feet). `BBL` is a float field, so read it as int64. 28,784 tax blocks. |
| `acs-bg/<TABLE>.csv` + `.labels.json` | 28 block group tables, Census API `group()` output | 6,807 rows each, all five counties. Columns `<var>E`, `<var>EA`, `<var>M`, `<var>MA`, plus `GEO_ID`, `state`, `county`, `tract`, `block group`. `NAME` appears twice (asked for once and returned again by the group), so drop the duplicate. |
| `acs-tract/DP04.csv`, `DP05.csv` | tract data profiles | 2,327 tracts. Not used in the pipeline. |
| `acs-dp04/GEOINFO2024.GEOINFO-Data.csv` | block group land area and internal point | 6,807 block groups. The second row is a label row, so skip it. The folder name is misleading: these are GEOINFO tables, not DP04. The block group IDs are identical across 2020–2025. |
| `footprints/BUILDING_20260830.geojson` | NYC Building Footprints (Open Data `5zhs-2jue`), WGS 84 | 1,083,026 features, one per line. Fields include `bin`, `mappluto_bbl`, `base_bbl`, `height_roof` (ft), `ground_elevation` (ft), `construction_year`, `feature_code`, `last_status_type`. 1 GB: please stream it line by line rather than loading it whole. |
| `trees/street_trees_2015.csv` | 2015 Street Tree Census (`uvpi-gqnh`) | 683,788 rows: 652,173 `Alive`, 17,654 `Stump`, 13,961 `Dead`. `x_sp`/`y_sp` are in EPSG:2263 feet. Has `tree_dbh`, `spc_latin`, `health`, `curb_loc`, `bbl`. |

ACS missing values come back as negative sentinels, mainly `-666666666` for the estimate and `-222222222` for the margin. Medians are often missing at the block group level. For example, `B25077` (median value) is missing for 2,669 of 6,807 block groups, and `B25064` (median rent) for 1,228. There are 411 block groups with zero population.

## 3. Pipeline

Python scripts in `data/scripts/`, numbered so they run in order, and writing to `data/processed/` (please add that to `.gitignore`). Add a `requirements.txt` listing pandas, pyarrow, numpy, pyogrio, shapely, scikit-learn, umap-learn and torch. The scripts need to run on Adam's Mac (Apple silicon) and his Windows PC (RTX 5060 Ti 16GB, through WSL2). Choose the torch device in the order cuda, then mps, then cpu. Use a fixed seed everywhere (placeholder: 0).

Intermediate tables are parquet, keyed by `bbl` (int64). The lot order used everywhere downstream is the lots sorted by `bbl`, and the position in that order is the `lot_index`.

### 3.1 `01_lots.py`: PLUTO attributes, block group, lot geometry

- Read all attribute fields plus geometry.
- Block group: `BCTCB2020` is 11 characters: borough code (1), 2020 tract (6), 2020 block (4). The block group is the first digit of the block. Convert the borough code to county FIPS (1→36061, 2→36005, 3→36047, 4→36081, 5→36085), then GEOID = county + tract + that digit (12 characters). Verified 2026-10-28: 856,664 lots get a GEOID, and every one of them is in GEOINFO. 23 lots have a 4-character `BCTCB2020` and get no block group. Keep them, with empty ACS features.
- Point position: `Latitude`/`Longitude`. Lots missing them (about 460, the same rows that are null across most fields) take the centroid of their polygon, reprojected.
- Lot shape: polygon area, perimeter, compactness (4πA/P²), and vertex count. All are measured in EPSG:2263.

### 3.2 `02_frontage.py`: street frontage

Reimplement the unshared-edge method from `frontage_unshared_edge.py`, citywide, block by block. A tax block is bounded by streets, so an edge a lot shares with no other lot in its block is street frontage. Use the same constants: sample every 3 ft, snap to a 3 ft grid, and call an edge shared when at least half its samples hit a key touched by two or more lots.

Outputs per lot:

- `frontage_ft`: total length of unshared edges.
- `frontage_runs`: number of separate unshared runs. 1 is an interior lot; 2 or more is a corner or through lot.
- `frontage_share`: frontage_ft divided by perimeter.
- `front_dir_sin`, `front_dir_cos`: the direction of the length-weighted mean outward normal.

Before running citywide, please run the Queens sample check and confirm it reproduces the docstring numbers within sampling noise (§4).

### 3.3 `03_footprints.py`: buildings per lot

- Stream the GeoJSON. Reproject to EPSG:2263. Join to lots on `mappluto_bbl`. Verified: 99.9% of footprints match a 26v2 BBL, and 816,746 lots have at least one footprint.
- `feature_code` 2100 is a building and 5110 a garage. Keep both, and also keep the others (a few hundred bridge/tower-type codes) only for the 3D view. Features use 2100 and 5110.
- Features per lot:
  - `n_footprints`
  - `footprint_area` (sum)
  - `coverage` (footprint_area / LotArea, capped at 1.5, placeholder)
  - `height_max` and `height_mean` (area-weighted, from `height_roof`)
  - `volume` (sum of area × height)
  - `ground_elev` (area-weighted `ground_elevation`)
- 3 footprints have no height, and 733 have height 0. Treat both as missing, not 0.
- 3D geometry for the browser: each lot's outline and its footprints, in feet relative to the lot's point, simplified to 1 ft (placeholder), with `height_roof` per footprint (§3.8).

### 3.4 `04_trees.py`: street trees per frontage

- Keep `status == "Alive"`.
- Assign each tree to the nearest lot polygon within 60 ft (placeholder). Trees farther than that are left unassigned and counted in the summary.
- Please don't use the census `bbl` field for this. Checked on the Bronx (78,540 living trees) on 2026-10-28:
  - The census `bbl` matches the nearest lot for only 66% of trees, and it is on the same tax block for 84%. The field is the address the volunteer recorded, which is often a corner building or a lot farther along the block.
  - The nearest lot is a median of 10.5 ft away, and 99% are within 58 ft, which fits a tree on the curb in front of the lot.
- Features per lot:
  - `trees_n`
  - `trees_per_100ft` (trees_n / frontage_ft × 100; empty where frontage_ft is 0)
  - `tree_dbh_mean`
  - `tree_species_n`

### 3.5 `05_acs.py`: block group features

Work from the `*.labels.json` files. Select variables by their label text, not by variable number, and write the label → feature mapping into the output so it can be checked. Turn counts into shares of the table's universe. Medians go in the tooltip only, not the embedding, because so many are missing.

Housing group:

- Vacancy share (B25002)
- Renter share (B25003)
- Units in structure, five shares: 1 unit (detached + attached), 2–4, 5–19, 20–49, 50+ (B25024)
- Year built, five shares: before 1940, 1940–1969, 1970–1999, 2000–2009, 2010 and later (B25034)
- Bedrooms, four shares: none, 1, 2, 3 or more (B25041)
- More than 1 occupant per room (B25014)
- Moved in 2010 or later (B25038)
- No vehicle (B25044)
- Heating fuel, four shares: utility gas, electricity, fuel oil, other (B25040)
- Lacking complete plumbing (B25047) and kitchen (B25051)
- Average household size (B25010)

Housing cost subgroup (still part of housing, but tagged `cost` in the manifest so Adam can drop it):

- Rent ≥ 30% of income (B25070)
- Owner costs ≥ 30% of income (B25091)
- With mortgage (B25081)
- Gross rent, five shares (B25063)
- Value, five shares (B25075)

Please choose the band edges for rent and value from the label text and record them.

Demographic group:

- Age, four shares: under 18, 18–34, 35–64, 65+ (B01001)
- Population density: B01003 divided by `AREALAND` from GEOINFO2024, per square mile
- Race and Hispanic origin shares from B03002: Hispanic or Latino, and non-Hispanic White, Black, Asian, and other or two or more

Medians for the tooltip: B25018, B25035, B25064, B25077, B01002.

Block groups with zero population or with the universe at 0 get empty shares and a flag `acs_empty`.

### 3.6 `06_features.py`: the model input

PLUTO block, used in every variant:

- Numeric, each `log1p` where the field is an area, count or volume, then robust-scaled (median and interquartile range):
  - LotArea, BldgArea, ResArea, ComArea, OfficeArea, RetailArea, GarageArea, StrgeArea, FactryArea, OtherArea
  - NumBldgs, NumFloors, UnitsRes, UnitsTotal
  - LotFront, LotDepth, BldgFront, BldgDepth
  - YearBuilt, YearAlter1 (as "years since", or empty when 0)
  - BuiltFAR, ResidFAR, CommFAR, FacilFAR
  - The lot shape, frontage, footprint and tree features above
- Categorical, each as an embedding table in the model:
  - LandUse
  - BldgClass first letter, plus full BldgClass
  - ZoneDist1, reduced to its family (`R6`, `C4`, `M1`, and so on, with suffixes stripped; keep the full value in the tooltip)
  - LotType, ProxCode, IrrLotCode, BsmtCode, Ext, OwnerType (empty → "private/unknown")
  - SplitZone
  - In-historic-district flag (`HistDist` not empty)
  - Landmark flag
  - `PFIRM15_FLAG`

Left out on purpose:

- All location fields (lat/lon, XCoord/YCoord, Borough, CD, Council, ZipCode, all district fields, tract and block fields, ZoneMap, Sanborn, TaxMap)
- Assessed values and exemptions (AssessLand, AssessTot, ExemptTot)
- OwnerName
- The record-keeping fields (Version, DCPEdited, Notes, APPBBL, APPDate, PLUTOMapID, AreaSource)

Missing values: many PLUTO fields use 0 to mean unknown. Please treat 0 as missing for YearBuilt, NumFloors, LotFront, LotDepth, BldgFront and BldgDepth. Every numeric feature gets a paired missing flag, the value is set to 0 after scaling, and the loss skips it (§3.7). About 45,000 lots have the area-breakdown fields null, and about 41,000 have no NumFloors. These are mostly lots without buildings, so they stay in.

ACS blocks are added only for their variants. Each ACS numeric feature is robust-scaled across lots, not across block groups, so each block group is weighted by how many lots it has. Every lot in a block group shares the same ACS values, which means there are only about 6,600 distinct ACS vectors. To keep them from dominating the result, multiply the ACS block by a weight so its total variance is 0.5 (placeholder) times the PLUTO block's total variance. Record the weight in the manifest.

### 3.7 `07_train.py`: the autoencoder

One model per variant, the same architecture for all four:

- Encoder: categorical embeddings (size min(8, levels/2), placeholder) are concatenated with the numeric values and their missing flags. Then an MLP of 256 → 128 → 64 (placeholder) with GELU activations and LayerNorm, ending in a latent of 16 dimensions (placeholder).
- Decoder: the reverse. It outputs numeric values and one softmax head per categorical field.
- Loss: masked MSE on numeric values (ignoring missing), plus cross-entropy per categorical field, divided by the number of fields in each block so neither block dominates the total.
- Training: batch 4,096, Adam with learning rate 1e-3, 30 epochs (placeholder), and 5% of lots held out to report reconstruction.

Outputs: `latent_<variant>.npy` (float32, N × 16) and `train_<variant>.json` (loss curve, held-out loss per field, settings).

### 3.8 `08_layout.py`: 3D layouts, clusters, diagnostics

- **UMAP to 3D** on the latent: n_neighbors 30, min_dist 0.1, both placeholders. Fit on a 200,000-lot random sample, then transform the rest, which saves time on 857k rows.
- **Alignment:** align each ACS variant's layout to the PLUTO-only layout with orthogonal Procrustes (rotation, reflection and uniform scale), so that switching variants moves points as little as needed. Then scale all four to fit a cube with side 100.
- **Clusters:** k-means on the latent, k = 12 (placeholder), per variant, with labels renumbered by cluster size.
- **Diagnostics:** these go in `diagnostics.json` and are shown in the info panel (§5.4). For each variant:
  - Block group overlap: across a 20,000-lot sample, the share of each lot's 20 nearest latent neighbors that are in the same block group. This shows how much the ACS block pulls lots together by place.
  - Borough check: the accuracy of a 20-nearest-neighbor classifier predicting borough from the latent, against the share of the largest borough. This shows how much location the embedding picks up without being given it.

### 3.9 `09_export.py`: files for the browser

Write to `web/public/data/`. All arrays are little-endian binary and follow lot_index order. `manifest.json` describes every file, field, unit, scale and source.

| file | contents |
|---|---|
| `lots.bin` | `bbl` float64, `lon`/`lat` float32, `bg_index` uint16 (65535 = none) |
| `fields.bin` | every field offered on the axis and color dropdowns, quantized to uint16 with min/max per field in the manifest (65535 = missing). Includes the PLUTO numeric fields, the derived features, the lot's ACS shares, lon, lat, and the cluster IDs. |
| `layout_<variant>.bin` | float32 × 3 |
| `latent_<variant>.bin` | int8 × 16, with a scale per dimension in the manifest. Loaded only when its variant is chosen. |
| `acs_bg.json` | per block group: GEOID, name, the tooltip medians and the ACS shares |
| `details/<shard>.json` | 1,000 lots per shard by lot_index: address, BldgClass, LandUse, ZoneDist1–2, OwnerType, YearBuilt, NumFloors, UnitsRes, frontage, tree count and species list |
| `glyphs/<shard>.bin` | 1,000 lots per shard: lot outline and footprints in feet relative to the lot point, quantized to int16 at 0.5 ft (placeholder), with height per footprint |

The manifest also carries the label, unit and group (PLUTO, footprints, frontage, trees, ACS housing, ACS cost, ACS demographic, embedding) for each field, which the dropdowns use.

## 4. Checks

Put these in `data/scripts/checks/`. Each prints its numbers and exits non-zero on failure. Please report the numbers in the summary.

- Join: 856,664 lots with a block group and 23 without. 6,625 distinct block groups used.
- Frontage, Queens sample: reproduces the numbers in the `frontage_unshared_edge.py` docstring within sampling noise (one unshared edge about 85%, normal out of block about 97%).
- Footprints: 1,083,026 read. Report the share joined to a lot and the number of lots with at least one footprint (expect about 816,700).
- Trees: 652,173 alive. Report how many were assigned within 60 ft, the distance percentiles, and the agreement with the census `bbl`. For the Bronx it should be near 66%.
- ACS: 6,807 block groups per table. For each feature, the number of block groups left empty.
- Training: the held-out loss for each variant is below the loss of predicting the mean for every field (report per field).
- Export: every `.bin` has length N × record size. Spot-check five BBLs against PLUTO for position, YearBuilt and NumFloors.

## 5. The interactive

### 5.1 Stack

- Vite + Svelte 5 + deck.gl + MapLibre, in `web/`. Match the versions in `smt-fa2026/package.json` (svelte ^5.20, vite ^6.2, deck.gl ^9.3.11, maplibre-gl ^6.6.0) so it can be moved over later.
- Basemap: Carto Positron, `https://basemaps.cartocdn.com/gl/positron-gl-style/style.json`, the one the course site already uses.
- No other map or 3D library.

### 5.2 Views

There is one point layer for all views. Switching view animates each point from its old position to its new one (1.5 s, placeholder, using deck.gl attribute transitions).

1. **Embedding.** OrbitView. Points at `layout_<variant>`, colored by cluster.
2. **Custom axes.** OrbitView. Three searchable dropdowns for X, Y and Z, each listing every field in the manifest grouped by its group. Defaults: X longitude, Y latitude, Z BldgArea. Each axis is rescaled to 0–100. Each axis has a log toggle and a percentile clip (1–99%, placeholder) so a few extreme lots don't flatten the rest. Show axis lines with the field name and three tick labels in the field's own units.
3. **Map.** MapView over the MapLibre basemap (interleaved). Points at lon/lat.
4. **Year built** (a preset of custom axes): X longitude, Y latitude, Z YearBuilt, with missing years left on the floor plane.

### 5.3 Zooming in: lot outlines and buildings

When the camera is close enough (placeholder: fewer than about 5,000 points in view), the points nearest the camera target are drawn as glyphs: the lot outline as a thin line and the footprints extruded to `height_roof`. Cap it at 3,000 glyphs (placeholder). Glyph shards load on demand and are cached.

- In the map view, glyphs sit at true position and true scale (meter offsets from the lot point).
- In the embedding and custom views, each glyph is centered on its point and scaled uniformly. A "glyph size" slider sets the scale. All glyphs share one scale, so relative lot sizes stay true.
- Points that become glyphs fade out. The rest stay points.

### 5.4 Controls

A left panel, collapsible:

- **View:** Embedding / Custom axes / Map / Year built
- **Embedding:** PLUTO only / + ACS housing / + ACS demographic / + both. Switching animates points to the new layout and reloads latent and clusters.
- **Color by:** Cluster / a field (the same searchable dropdown) / Similarity (enabled after a lot is chosen, §5.5)
- **Axes:** the three dropdowns, shown only in Custom axes
- **Find a lot by BBL:** an input that flies to and selects that lot
- **About this embedding:** the diagnostics for the current variant (§3.8) as two short lines, and the training settings

Color: use the cluster palette and the sequential ramp the dataviz guidance recommends. Keep missing values a neutral gray in every mode.

### 5.5 Clicking a lot

- Clicking selects the lot and opens a card:
  - Address and BBL
  - Land use and building class, written out in words using the data dictionary codes
  - Zoning
  - Year built, floors, residential units
  - Roof height (max)
  - Frontage, and trees on the frontage
  - Cluster
  - For ACS variants, a short block group section with three or four of the medians
- **Lots like this one** (a button on the card):
  - Compute the distance from the chosen lot to every lot in the current variant's latent, in the browser. That's N × 16 int8, a brute-force pass of well under a second.
  - Color all lots by that distance (Color by switches to Similarity).
  - Highlight the 50 nearest (placeholder) and list them in the panel with their address and distance. Clicking one in the list flies to it in the current view.
- Changing variant keeps the selection and recomputes the distances.

### 5.6 Performance

- The first load is `lots.bin`, `fields.bin`, the PLUTO-only layout and latent, and the manifest. Report the total size in the summary.
- If `fields.bin` is over 60 MB, split it into one file per group and load each group the first time a field from it is used.

## 6. Strings

Use these as written. If you need a string that isn't here, add it to this list in your summary.

- ACS note, shown under the Embedding selector whenever an ACS variant is on, and in the card's ACS section: "Note: high margin of error for block-group level data."
- Similarity legend: "Distance in embedding space (nearer = more alike)."
- Missing value in a card: "—"

Write a `web/README.md` (prose draft) covering how to run the pipeline, what each script reads and writes, and how to run the web view.

## 7. Placeholders and open items

All placeholders are listed here so Adam can change them in one pass:

- Seed 0
- Tree distance cap 60 ft
- Coverage cap 1.5
- Glyph simplification 1 ft and quantization 0.5 ft
- ACS block variance weight 0.5
- Latent 16, MLP 256/128/64, 30 epochs
- UMAP n_neighbors 30, min_dist 0.1, fit sample 200,000
- k = 12
- Transition 1.5 s
- Glyph trigger about 5,000 in view, cap 3,000
- 50 nearest
- Percentile clip 1–99%

Open items for Adam. None of them blocks the build:

- OwnerName is left out of the card. It's public data, but showing owner names wasn't discussed.
- The ACS housing cost subgroup (rent, value, cost burden) is in the housing variant, tagged `cost`. Removing it means deleting the tag from the housing group and retraining.
- `.gitignore` lists `utilties/` (misspelled), so `utilities/` is currently not ignored.

## 8. Summary to hand back

In the summary, please include:

- The files changed and added.
- The output of every check in §4.
- Run times for each script and the machine it ran on.
- Held-out reconstruction per variant.
- The diagnostics from §3.8.
- First-load size of the web view.
- Anything in this document that did not match what was on disk.
