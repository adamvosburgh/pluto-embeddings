"""Shared paths, constants and helpers for the numbered pipeline scripts.

Every script imports this module. The lot order used everywhere downstream is the
lots sorted by bbl, and the position in that order is the lot_index.
"""
import json, os, random, time
import numpy as np

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPTS, "..", ".."))
ORIG = os.path.join(REPO, "data", "original")
PROC = os.path.join(REPO, "data", "processed")
WEB_DATA = os.path.join(REPO, "web", "public", "data")
os.makedirs(PROC, exist_ok=True)

PLUTO_GDB = os.path.join(ORIG, "nyc_mappluto_26v2_fgdb", "MapPLUTO26v2.gdb")
PLUTO_LAYER = "MapPLUTO_26v2_clipped"
FOOTPRINTS = os.path.join(ORIG, "footprints", "BUILDING_20260830.geojson")
TREES = os.path.join(ORIG, "trees", "street_trees_2015.csv")
ACS_BG = os.path.join(ORIG, "acs-bg")
GEOINFO = os.path.join(ORIG, "acs-dp04", "GEOINFO2024.GEOINFO-Data.csv")

# Placeholders (build doc §7). Change them here, in one place.
SEED = 0
TREE_MAX_FT = 60.0
COVERAGE_CAP = 1.5
GLYPH_SIMPLIFY_FT = 1.0
GLYPH_QUANT_FT = 0.5
ACS_VARIANCE_WEIGHT = 0.5
LATENT_DIM = 16
HIDDEN = (256, 128, 64)
EPOCHS = 30
BATCH = 4096
LR = 1e-3
HOLDOUT = 0.05
UMAP_NEIGHBORS = 30
UMAP_MIN_DIST = 0.1
UMAP_FIT_SAMPLE = 200_000
K_CLUSTERS = 12
SCALED_CLIP = 10.0      # robust-scaled values are clipped to +/- this, so a few huge lots don't dominate MSE
CURRENT_YEAR = 2026     # "years since" for YearBuilt / YearAlter1

VARIANTS = ["pluto", "housing", "demo", "both"]
VARIANT_LABELS = {"pluto": "PLUTO only", "housing": "+ ACS housing",
                  "demo": "+ ACS demographic", "both": "+ both"}
VARIANT_ACS = {"pluto": [], "housing": ["housing", "cost"],
               "demo": ["demographic"], "both": ["housing", "cost", "demographic"]}

BORO_FIPS = {"1": "36061", "2": "36005", "3": "36047", "4": "36081", "5": "36085"}


def p(*parts):
    return os.path.join(PROC, *parts)


def seed_everything(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def torch_device():
    import torch
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def to_bbl(values):
    """BBL arrives as float (PLUTO) or string (footprints, trees). Return int64, 0 where unusable."""
    a = np.asarray(values, dtype=object)
    out = np.zeros(len(a), dtype=np.int64)
    for i, v in enumerate(a):
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and f > 0:
            out[i] = int(round(f))
    return out


def transformer(src, dst):
    from pyproj import Transformer
    return Transformer.from_crs(src, dst, always_xy=True)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=_json_default)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if o != o else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


class Timer:
    """Prints elapsed time for a script and appends it to data/processed/timings.json."""
    def __init__(self, name):
        self.name, self.t0 = name, time.time()

    def done(self):
        dt = time.time() - self.t0
        path = p("timings.json")
        t = json.load(open(path)) if os.path.exists(path) else {}
        import platform
        t[self.name] = {"seconds": round(dt, 1), "machine": platform.platform(),
                        "when": time.strftime("%Y-%m-%d %H:%M")}
        write_json(path, t)
        print(f"[{self.name}] done in {dt:,.1f} s", flush=True)
