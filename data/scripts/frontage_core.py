"""The unshared-edge frontage method, vectorized per chunk of tax blocks.

Reimplements smt-fa2026/data/scripts/checks/frontage_unshared_edge.py. A NYC tax block is
bounded by streets, so every shared lot line lies inside a block: an edge a lot shares with
no other lot in its block is street frontage. Each edge is sampled every STEP ft, the
samples snapped to a SNAP ft grid, and the edge called shared when at least SHARED_FRAC of
its samples land on a grid key touched by two or more lots of the same block.

Differences from the original, which read the shapefile: edges come from the exterior ring
of every polygon part (the original used only the first ring), and the work is done with
numpy over thousands of blocks at once rather than a Python loop per edge. The block is
folded into the key, so lots in different blocks never share.
"""
import numpy as np, pandas as pd, shapely

SNAP, STEP, SHARED_FRAC = 3.0, 3.0, 0.5
MIN_EDGE = 0.5
KEY_X = 4_000_000          # same key packing as the original: kx * 4e6 + ky
KEY_BLOCK = 2_000_000_000_000
CHUNK_LOTS = 40_000


def _chunk(geoms, block_idx, n_lots):
    parts, part_lot = shapely.get_parts(geoms, return_index=True)
    rings = shapely.get_exterior_ring(parts)
    xy, ring_of = shapely.get_coordinates(rings, return_index=True)
    ring_lot = part_lot[np.arange(len(rings))]

    # lot center = mean of ring vertices, closing point excluded (as in the original)
    last = np.r_[ring_of[1:] != ring_of[:-1], True]
    keep_v = ~last
    vl = ring_lot[ring_of[keep_v]]
    cnt = np.bincount(vl, minlength=n_lots)
    cx = np.bincount(vl, xy[keep_v, 0], n_lots) / np.maximum(cnt, 1)
    cy = np.bincount(vl, xy[keep_v, 1], n_lots) / np.maximum(cnt, 1)

    same = ring_of[1:] == ring_of[:-1]
    P, Q, er = xy[:-1][same], xy[1:][same], ring_of[:-1][same]
    d = Q - P
    L = np.hypot(d[:, 0], d[:, 1])
    k = L >= MIN_EDGE
    P, d, L, er = P[k], d[k], L[k], er[k]
    el = ring_lot[er]
    nx, ny = d[:, 1] / L, -d[:, 0] / L
    mx, my = P[:, 0] + d[:, 0] / 2, P[:, 1] + d[:, 1] / 2
    flip = (mx - cx[el]) * nx + (my - cy[el]) * ny < 0
    nx[flip], ny[flip] = -nx[flip], -ny[flip]

    # samples along each edge
    ns = np.maximum(2, (L / STEP).astype(np.int64) + 1)
    E = len(L)
    se = np.repeat(np.arange(E), ns)
    start = np.r_[0, np.cumsum(ns)[:-1]]
    t = (np.arange(len(se)) - start[se]) / (ns[se] - 1)
    sx = P[se, 0] + d[se, 0] * t
    sy = P[se, 1] + d[se, 1] * t
    key = (block_idx[el[se]].astype(np.int64) * KEY_BLOCK
           + np.rint(sx / SNAP).astype(np.int64) * KEY_X + np.rint(sy / SNAP).astype(np.int64))
    sl = el[se]

    o = np.lexsort((sl, key))
    K, O = key[o], sl[o]
    u = np.ones(len(K), bool)
    u[1:] = (K[1:] != K[:-1]) | (O[1:] != O[:-1])
    ku, cn = np.unique(K[u], return_counts=True)
    multi = ku[cn >= 2]
    shared_s = np.isin(key, multi)
    frac = np.bincount(se, shared_s.astype(np.float64), E) / ns
    free = frac < SHARED_FRAC

    # separate unshared runs, walking each ring in order with wraparound
    first = np.r_[True, er[1:] != er[:-1]]
    first_idx = np.flatnonzero(first)
    ring_start = np.repeat(first_idx, np.diff(np.r_[first_idx, E]))
    ring_end = np.repeat(np.r_[first_idx[1:], E] - 1, np.diff(np.r_[first_idx, E]))
    prev = np.where(first, ring_end, np.arange(E) - 1)
    run_start = free & ~free[prev]
    n_ring_edges = np.bincount(er, minlength=len(rings))
    n_ring_free = np.bincount(er, free.astype(np.int64), len(rings))
    ring_runs = np.bincount(er, run_start.astype(np.int64), len(rings))
    ring_runs = np.where((n_ring_free == n_ring_edges) & (n_ring_edges > 0), 1, ring_runs)

    out = pd.DataFrame({
        "frontage_ft": np.bincount(el, L * free, n_lots),
        "frontage_edges": np.bincount(el, free.astype(np.int64), n_lots).astype(np.int32),
        "frontage_runs": np.bincount(ring_lot, ring_runs, n_lots).astype(np.int32),
        "edge_len_total": np.bincount(el, L, n_lots),
        "fx": np.bincount(el, nx * L * free, n_lots),
        "fy": np.bincount(el, ny * L * free, n_lots),
        "cx": cx, "cy": cy,
    })
    # block center = mean of lot centers in the block (as in the original)
    has = cnt > 0
    nb = block_idx.max() + 1
    bn = np.bincount(block_idx[has], minlength=nb)
    bcx = np.bincount(block_idx[has], cx[has], nb) / np.maximum(bn, 1)
    bcy = np.bincount(block_idx[has], cy[has], nb) / np.maximum(bn, 1)
    mag = np.hypot(out["fx"], out["fy"])
    out["front_out_of_block"] = ((cx - bcx[block_idx]) * out["fx"] + (cy - bcy[block_idx]) * out["fy"] > 0) & (mag > 1e-9)
    return out


def compute_frontage(block_key, geoms, verbose=True):
    """Frontage for lots grouped by tax block. Inputs in any order; output in input order."""
    block_key = np.asarray(block_key)
    order = np.argsort(block_key, kind="stable")
    bk = block_key[order]
    cuts = [0]
    breaks = np.flatnonzero(np.r_[True, bk[1:] != bk[:-1]])
    nxt = CHUNK_LOTS
    for b in breaks[1:]:
        if b >= nxt:
            cuts.append(b)
            nxt = b + CHUNK_LOTS
    cuts.append(len(bk))
    pieces = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        idx = order[a:b]
        _, binv = np.unique(bk[a:b], return_inverse=True)
        g = geoms[idx]
        ok = ~shapely.is_missing(g) & ~shapely.is_empty(g)
        res = _chunk(np.where(ok, g, shapely.from_wkt("POLYGON EMPTY")), binv, len(idx))
        res.index = idx
        pieces.append(res)
        if verbose:
            print(f"  frontage {b:,}/{len(bk):,} lots", flush=True)
    out = pd.concat(pieces).sort_index()
    mag = np.hypot(out["fx"], out["fy"])
    has = (out["frontage_ft"] > 0) & (mag > 1e-9)
    ang = np.arctan2(out["fy"], out["fx"])
    out["front_dir_sin"] = np.where(has, np.sin(ang), np.nan)
    out["front_dir_cos"] = np.where(has, np.cos(ang), np.nan)
    return out
