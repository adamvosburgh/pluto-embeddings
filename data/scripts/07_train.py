"""07: one autoencoder per variant, same architecture for all four.

Encoder: categorical embeddings + numeric values + missing flags -> MLP (GELU, LayerNorm) ->
latent. Decoder mirrors it, with a numeric head and one softmax head per categorical field.
Loss: masked MSE averaged over numeric fields + cross-entropy averaged over categorical fields.

    python 07_train.py              # all four variants
    python 07_train.py pluto both   # just these

Reads  data/processed/features.npz, features.json
Writes data/processed/latent_<variant>.npy   float32, N x LATENT_DIM, lot_index order
       data/processed/train_<variant>.json   loss curve, held-out loss per field vs predicting the mean
"""
import json, math, sys, time
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
from common import *

T = Timer("07_train")
dev = torch_device()
print(f"device {dev}", flush=True)
Z = np.load(p("features.npz"))
spec = json.load(open(p("features.json")))
cat_specs = spec["categorical"]
N = spec["n_lots"]


def variant_arrays(v):
    xs, ms, names = [Z["num_pluto"]], [Z["miss_pluto"]], [s["field"] for s in spec["pluto_numeric"]]
    for g in VARIANT_ACS[v]:
        w = spec["acs_weight"][v]
        xs.append(Z[f"num_{g}"] * w)
        ms.append(Z[f"miss_{g}"])
        names += [s["field"] for s in spec["acs_numeric"][g]]
    return np.concatenate(xs, 1).astype(np.float32), np.concatenate(ms, 1).astype(np.float32), names


def mlp(sizes):
    layers = []
    for a, b in zip(sizes[:-1], sizes[1:]):
        layers += [nn.Linear(a, b), nn.GELU(), nn.LayerNorm(b)]
    return nn.Sequential(*layers)


class AE(nn.Module):
    def __init__(self, n_num, levels):
        super().__init__()
        self.emb = nn.ModuleList([nn.Embedding(n, min(8, max(1, math.ceil(n / 2)))) for n in levels])
        d_in = sum(e.embedding_dim for e in self.emb) + 2 * n_num
        self.enc = nn.Sequential(mlp((d_in,) + HIDDEN), nn.Linear(HIDDEN[-1], LATENT_DIM))
        self.dec = mlp((LATENT_DIM,) + HIDDEN[::-1])
        self.num_head = nn.Linear(HIDDEN[0], n_num)
        self.cat_heads = nn.ModuleList([nn.Linear(HIDDEN[0], n) for n in levels])

    def encode(self, x, m, c):
        e = [emb(c[:, i]) for i, emb in enumerate(self.emb)]
        return self.enc(torch.cat(e + [x, m], 1))

    def forward(self, x, m, c):
        z = self.encode(x, m, c)
        h = self.dec(z)
        return self.num_head(h), [hd(h) for hd in self.cat_heads]


def per_field_losses(model, x, m, c, idx):
    """Mean held-out loss per numeric field (masked MSE) and per categorical field (CE)."""
    se = torch.zeros(x.shape[1], device=dev)
    cnt = torch.zeros(x.shape[1], device=dev)
    ce = torch.zeros(c.shape[1], device=dev)
    model.eval()
    with torch.no_grad():
        for i in range(0, len(idx), BATCH * 4):
            b = idx[i:i + BATCH * 4]
            pn, pc = model(x[b], m[b], c[b])
            keep = 1 - m[b]
            se += ((pn - x[b]) ** 2 * keep).sum(0)
            cnt += keep.sum(0)
            for j, logits in enumerate(pc):
                ce[j] += F.cross_entropy(logits, c[b, j], reduction="sum")
    return (se / cnt.clamp(min=1)).cpu().numpy(), (ce / len(idx)).cpu().numpy()


def baseline(x, m, c, train, held, levels):
    """Loss of predicting the training mean (numeric) / training class frequencies (categorical)."""
    keep_t = 1 - m[train]
    mean = (x[train] * keep_t).sum(0) / keep_t.sum(0).clamp(min=1)
    keep_h = 1 - m[held]
    mse = (((x[held] - mean) ** 2) * keep_h).sum(0) / keep_h.sum(0).clamp(min=1)
    ce = []
    for j, n in enumerate(levels):
        freq = torch.bincount(c[train, j], minlength=n).float() + 1e-3
        logp = torch.log(freq / freq.sum())
        ce.append(float(-logp[c[held, j]].mean()))
    return mse.cpu().numpy(), np.array(ce)


def train(v):
    seed_everything()
    xn, mn, names = variant_arrays(v)
    x, m = torch.from_numpy(xn).to(dev), torch.from_numpy(mn).to(dev)
    c = torch.from_numpy(Z["cat"]).to(dev)
    levels = [s["n_levels"] for s in cat_specs]
    perm = np.random.default_rng(SEED).permutation(N)
    n_held = int(round(N * HOLDOUT))
    held = torch.from_numpy(np.sort(perm[:n_held])).to(dev)
    tr = torch.from_numpy(perm[n_held:]).to(dev)
    model = AE(x.shape[1], levels).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    g = torch.Generator(device="cpu").manual_seed(SEED)
    curve = []
    t0 = time.time()
    for ep in range(EPOCHS):
        model.train()
        order = tr[torch.randperm(len(tr), generator=g).to(dev)]
        tot, nb = 0.0, 0
        for i in range(0, len(order), BATCH):
            b = order[i:i + BATCH]
            pn, pc = model(x[b], m[b], c[b])
            keep = 1 - m[b]
            mse_f = ((pn - x[b]) ** 2 * keep).sum(0) / keep.sum(0).clamp(min=1)
            num_loss = mse_f.mean()
            cat_loss = torch.stack([F.cross_entropy(l, c[b, j]) for j, l in enumerate(pc)]).mean()
            loss = num_loss + cat_loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss)
            nb += 1
        hm, hc = per_field_losses(model, x, m, c, held)
        held_loss = float(hm.mean() + hc.mean())
        curve.append({"epoch": ep + 1, "train": tot / nb, "held_out": held_loss})
        print(f"  [{v}] epoch {ep + 1:2d}  train {tot / nb:.4f}  held-out {held_loss:.4f}  "
              f"({time.time() - t0:,.0f} s)", flush=True)

    hm, hc = per_field_losses(model, x, m, c, held)
    bm, bc = baseline(x, m, c, tr, held, levels)
    model.eval()
    lat = []
    with torch.no_grad():
        for i in range(0, N, BATCH * 4):
            sl = slice(i, i + BATCH * 4)
            lat.append(model.encode(x[sl], m[sl], c[sl]).float().cpu().numpy())
    lat = np.concatenate(lat).astype(np.float32)
    np.save(p(f"latent_{v}.npy"), lat)
    per_field = ([{"field": n, "kind": "numeric", "held_out": float(a), "mean_baseline": float(b)}
                  for n, a, b in zip(names, hm, bm)]
                 + [{"field": s["field"], "kind": "categorical", "held_out": float(a), "mean_baseline": float(b)}
                    for s, a, b in zip(cat_specs, hc, bc)])
    write_json(p(f"train_{v}.json"), {
        "variant": v, "device": str(dev), "seconds": round(time.time() - t0, 1), "curve": curve,
        "held_out_total": float(hm.mean() + hc.mean()), "baseline_total": float(bm.mean() + bc.mean()),
        "held_out_numeric": float(hm.mean()), "held_out_categorical": float(hc.mean()),
        "per_field": per_field,
        "settings": {"latent": LATENT_DIM, "hidden": list(HIDDEN), "epochs": EPOCHS, "batch": BATCH, "lr": LR,
                     "holdout": HOLDOUT, "seed": SEED, "n_numeric": int(x.shape[1]), "n_categorical": len(levels),
                     "acs_weight": spec["acs_weight"].get(v)},
    })
    print(f"[{v}] held-out {hm.mean() + hc.mean():.4f} vs mean baseline {bm.mean() + bc.mean():.4f}", flush=True)


for v in (sys.argv[1:] or VARIANTS):
    train(v)
T.done()
