"""Check: browser files have the right lengths; five BBLs match PLUTO (after 09_export.py)."""
from _check import *
from common import WEB_DATA, PLUTO_GDB, PLUTO_LAYER, to_bbl
import numpy as np, pandas as pd, pyogrio

m = json.load(open(os.path.join(WEB_DATA, "manifest.json")))
N = m["n_lots"]


def size(f):
    return os.path.getsize(os.path.join(WEB_DATA, f))


report("lots.bin", size("lots.bin"), size("lots.bin") == N * 18, "N x 18")
for f in sorted({x["file"] for x in m["fields"]}):
    n = sum(1 for x in m["fields"] if x["file"] == f)
    report(f, size(f), size(f) == N * 2 * n, f"N x 2 x {n} fields")
for v in m["variants"]:
    report(v["layout"], size(v["layout"]), size(v["layout"]) == N * 12, "N x 12")
    report(v["latent"], size(v["latent"]), size(v["latent"]) == N * m["latent_dim"], "N x 16")
n_shards = (N + 999) // 1000
for d in ("details", "glyphs"):
    k = len(os.listdir(os.path.join(WEB_DATA, d)))
    report(f"{d}_shards", k, k == n_shards)

raw = open(os.path.join(WEB_DATA, "lots.bin"), "rb").read()
bbl = np.frombuffer(raw, "<f8", N, 0).astype(np.int64)
lon = np.frombuffer(raw, "<f4", N, N * 8)
lat = np.frombuffer(raw, "<f4", N, N * 12)
fields = {x["key"]: x for x in m["fields"]}


def field(key, i):
    x = fields[key]
    q = np.frombuffer(open(os.path.join(WEB_DATA, x["file"]), "rb").read(), "<u2", N, x["offset"])[i]
    return None if q == 65535 else x["min"] + q * x["scale"]


rng = np.random.default_rng(0)
pick = np.sort(rng.choice(N, 5, replace=False))
want = set(bbl[pick].tolist())
res = pyogrio.raw.read(PLUTO_GDB, layer=PLUTO_LAYER, read_geometry=False,
                       columns=["BBL", "Latitude", "Longitude", "YearBuilt", "NumFloors"])
names, data = list(res[0]["fields"]), res[-1]
d = pd.DataFrame({n: v for n, v in zip(names, data)})
d["bbl"] = to_bbl(d["BBL"].to_numpy())
d = d[d["bbl"].isin(want)].set_index("bbl")
for i in pick:
    b = int(bbl[i])
    r = d.loc[b]
    ok_pos = (not np.isfinite(r["Latitude"])) or (abs(r["Latitude"] - lat[i]) < 1e-5 and abs(r["Longitude"] - lon[i]) < 1e-5)
    yb = field("YearBuilt", i)
    nf = field("NumFloors", i)
    ok_yb = (yb is None and not (r["YearBuilt"] > 0)) or (yb is not None and abs(yb - r["YearBuilt"]) < 0.5)
    ok_nf = (nf is None and not (r["NumFloors"] > 0)) or (nf is not None and abs(nf - r["NumFloors"]) < 0.01)
    report(f"bbl_{b}", {"lat": float(lat[i]), "lon": float(lon[i]), "YearBuilt": yb, "NumFloors": nf,
                        "pluto": [r["Latitude"], r["Longitude"], r["YearBuilt"], r["NumFloors"]]},
           ok_pos and ok_yb and ok_nf)
s = json.load(open(p("export_summary.json")))
report("first_load_MB", round(s["first_load_bytes"] / 1e6, 1), True, ", ".join(s["first_load"]))
finish("export")
