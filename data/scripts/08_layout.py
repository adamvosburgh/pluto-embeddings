"""08: 3D layouts (UMAP), Procrustes alignment, k-means clusters and diagnostics.

Reads  data/processed/latent_<variant>.npy, lot_table.parquet
Writes data/processed/layout_<variant>.npy   float32 N x 3, aligned to PLUTO-only, in a 100-unit cube
       data/processed/clusters_<variant>.npy int16, renumbered by size (0 = largest)
       data/processed/diagnostics.json
"""
import json, os, sys
import numpy as np, pandas as pd
from scipy.linalg import orthogonal_procrustes
from sklearn.cluster import KMeans
from sklearn.neighbors import NearestNeighbors
from common import *

T = Timer("08_layout")
seed_everything()
import umap

lt = pd.read_parquet(p("lot_table.parquet"), columns=["bbl", "geoid", "borough_code"])
N = len(lt)
variants = [v for v in VARIANTS if os.path.exists(p(f"latent_{v}.npy"))]
if variants[0] != "pluto":
    raise SystemExit("latent_pluto.npy is needed: the other layouts are aligned to it")
rng = np.random.default_rng(SEED)
fit_idx = np.sort(rng.choice(N, min(UMAP_FIT_SAMPLE, N), replace=False))
diag_idx = np.sort(rng.choice(N, 20_000, replace=False))
bg = lt["geoid"].fillna("").to_numpy()
boro = lt["borough_code"].to_numpy()

raw, diags = {}, {}
for v in variants:
    lat = np.load(p(f"latent_{v}.npy"))
    print(f"[{v}] UMAP fit on {len(fit_idx):,}", flush=True)
    red = umap.UMAP(n_components=3, n_neighbors=UMAP_NEIGHBORS, min_dist=UMAP_MIN_DIST,
                    random_state=SEED, low_memory=True)
    red.fit(lat[fit_idx])
    emb = np.empty((N, 3), np.float32)
    rest = np.setdiff1d(np.arange(N), fit_idx)
    emb[fit_idx] = red.embedding_
    for i in range(0, len(rest), 100_000):
        emb[rest[i:i + 100_000]] = red.transform(lat[rest[i:i + 100_000]])
        print(f"  [{v}] transformed {min(i + 100_000, len(rest)):,}/{len(rest):,}", flush=True)
    raw[v] = emb.astype(np.float64)

    km = KMeans(n_clusters=K_CLUSTERS, n_init=4, random_state=SEED).fit(lat)
    sizes = np.bincount(km.labels_, minlength=K_CLUSTERS)
    rank = np.empty(K_CLUSTERS, np.int16)
    rank[np.argsort(-sizes, kind="stable")] = np.arange(K_CLUSTERS)
    cl = rank[km.labels_]
    np.save(p(f"clusters_{v}.npy"), cl.astype(np.int16))

    nn = NearestNeighbors(n_neighbors=21).fit(lat)
    _, nb = nn.kneighbors(lat[diag_idx])
    nb = nb[:, 1:]
    has_bg = bg[diag_idx] != ""
    same_bg = (bg[nb] == bg[diag_idx][:, None])[has_bg].mean()
    votes = np.apply_along_axis(lambda r: np.bincount(r, minlength=6).argmax(), 1, boro[nb])
    acc = float((votes == boro[diag_idx]).mean())
    largest = float(np.bincount(boro[diag_idx]).max() / len(diag_idx))
    diags[v] = {"bg_overlap_20nn": float(same_bg), "borough_knn_accuracy": acc,
                "borough_largest_share": largest,
                "cluster_sizes": np.sort(sizes)[::-1].tolist()}
    print(f"[{v}] {json.dumps(diags[v])}", flush=True)

# Align each ACS variant to PLUTO-only (rotation/reflection + uniform scale), then fit all in one cube.
ref = raw["pluto"] - raw["pluto"].mean(0)
aligned = {"pluto": ref}
for v in variants[1:]:
    b = raw[v] - raw[v].mean(0)
    R, s = orthogonal_procrustes(b, ref)
    scale = s / (b ** 2).sum()
    aligned[v] = b @ R * scale
    diags[v]["procrustes_scale"] = float(scale)
lo = np.min([np.percentile(a, 0.5, axis=0) for a in aligned.values()], axis=0)
hi = np.max([np.percentile(a, 99.5, axis=0) for a in aligned.values()], axis=0)
center, span = (lo + hi) / 2, float((hi - lo).max())
for v, a in aligned.items():
    np.save(p(f"layout_{v}.npy"), ((a - center) / span * 100).astype(np.float32))

write_json(p("diagnostics.json"), {
    "variants": diags, "diag_sample": len(diag_idx), "k": K_CLUSTERS,
    "umap": {"n_neighbors": UMAP_NEIGHBORS, "min_dist": UMAP_MIN_DIST, "fit_sample": len(fit_idx)},
    "cube": {"side": 100, "fit_percentiles": [0.5, 99.5]},
})
T.done()
