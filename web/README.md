<!-- PROSE DRAFT: written for accuracy, not voice. Rewrite against the style guide. -->

# PLUTO Embeddings

Every tax lot in New York City (856,687 in MapPLUTO 26v2) becomes a point. A small PyTorch autoencoder turns each lot's PLUTO record, buildings, street frontage and street trees (and, in three of the four variants, its block group's ACS figures) into a 16-number vector. The browser view arranges the points by that embedding, by any three fields, or on a map.

Nothing is fetched at build time. Every input is already in `data/original/`.

## Running the pipeline

The pipeline runs on macOS (Apple silicon) and on Windows through WSL2. From the repo root:

```bash
bash run_pipeline.sh setup      # once: creates ~/.venvs/pluto-embeddings and installs requirements.txt
bash run_pipeline.sh            # every step and its check, 01 through 09
bash run_pipeline.sh from 07    # start again at a step
bash run_pipeline.sh only 04    # one step and its check
```

On a machine with `nvidia-smi`, setup installs the CUDA 12.8 build of PyTorch, which the RTX 50 series needs. Training picks its device in the order cuda, mps, cpu. The script stops at the first step or check that fails. Everything it prints also goes to `data/processed/run_log.txt`. Run times go to `data/processed/timings.json`, and check results go to `data/processed/checks.json`.

To change a placeholder (the seed, the tree distance cap, the network sizes, k, and so on), edit the block at the top of `data/scripts/common.py`. The web placeholders are at the top of `web/src/lib/viewer.js` and `web/src/App.svelte`.

## What each script reads and writes

All outputs go to `data/processed/` unless noted. Tables are parquet keyed by `bbl` (int64). The lot order everywhere is the lots sorted by `bbl`, and a lot's position in that order is its `lot_index`.

| script | reads | writes |
|---|---|---|
| `01_lots.py` | MapPLUTO 26v2 GDB | `lots.parquet` (every attribute, block group GEOID from `BCTCB2020`, point position, lot shape), `lot_geom.parquet` (polygons in EPSG:2263) |
| `02_frontage.py` | `lots`, `lot_geom` | `frontage.parquet`: frontage length, runs, share of perimeter, direction |
| `03_footprints.py` | building footprints GeoJSON (streamed), `lots` | `footprints.parquet` (per-lot building features), `footprint_geom.parquet` (simplified footprints for the 3D glyphs), `footprints_summary.json` |
| `04_trees.py` | 2015 street tree census, `lot_geom`, `frontage` | `trees.parquet` (per-lot tree features), `tree_assign.parquet` (per living tree) |
| `05_acs.py` | ACS block group tables and labels, GEOINFO2024 | `acs_bg.parquet`, `acs_features.json` (each feature's variables and label text, and its count of empty block groups) |
| `06_features.py` | all of the above | `features.npz` and `features.json` (the model input), `lot_table.parquet` (every field in real units) |
| `07_train.py` | `features` | `latent_<variant>.npy`, `train_<variant>.json` |
| `08_layout.py` | latents, `lot_table` | `layout_<variant>.npy`, `clusters_<variant>.npy`, `diagnostics.json` |
| `09_export.py` | everything above | `web/public/data/` (see below), `export_summary.json` |

`frontage_core.py` holds the unshared-edge method that `02_frontage.py` and the Queens check share. `codes.py` holds the data dictionary's code tables, which the lot card uses.

The checks in `data/scripts/checks/` each print their numbers and exit non-zero on failure. `run_pipeline.sh` runs `check_frontage_queens.py` before the citywide frontage step.

The four variants are `pluto` (PLUTO, footprints, frontage and trees), `housing` (plus ACS housing and housing cost), `demo` (plus ACS demographic) and `both`.

## The browser files

`09_export.py` writes these to `web/public/data/`, all little-endian and in lot_index order. `manifest.json` describes each one.

- `lots.bin`: columnar `bbl` float64, `lon` float32, `lat` float32, `bg_index` uint16.
- `fields_<group>.bin`: one uint16 column per field, with 65535 for missing. The value is `min + q × scale`, with `min` and `scale` given in the manifest. The fields are split by group because together they come to more than 60 MB.
- `layout_<variant>.bin` (float32 × 3) and `latent_<variant>.bin` (int8 × 16, with a scale per dimension).
- `acs_bg.json`, `details/<shard>.json`, `glyphs/<shard>.bin`: 1,000 lots per shard.

The first load is the manifest, `lots.bin`, the PLUTO-only layout and latent, and `fields_embedding.bin` (the cluster IDs). The ACS table loads in the background. Other field groups load the first time one of their fields is chosen.

## Running the web view

```bash
cd web
npm install
npm run dev        # or: bash run_pipeline.sh web
```

Open the address Vite prints. `npm run build` writes a static site to `web/dist/`.

## Known limits

- Glyph shards follow lot_index, which is BBL order. In the map view, the lots near the camera are neighbors in BBL order, so they come from a few shards. In the embedding view they come from all over the city, so one update can need hundreds of shards. Each update fetches at most 150 shards (`GLYPH_MAX_SHARDS` in `viewer.js`). Lots in other shards stay as points.
- Point moves are animated between the embedding, custom-axes and year-built views. The map view uses a different camera, so switching into or out of it is a cut.
- The MapLibre overlay is not interleaved. `@deck.gl/mapbox` 9.4 throws with maplibre-gl 6.x in interleaved mode, because it reads `map.transform`, which maplibre-gl 6.x no longer has.
