"""Check: each variant's held-out loss beats predicting the mean, per field (after 07_train.py)."""
from _check import *
from common import VARIANTS

for v in VARIANTS:
    path = p(f"train_{v}.json")
    if not os.path.exists(path):
        report(f"{v}_trained", False, False)
        continue
    t = json.load(open(path))
    worse = [f["field"] for f in t["per_field"] if f["held_out"] >= f["mean_baseline"]]
    report(f"{v}_held_out_total", round(t["held_out_total"], 4), t["held_out_total"] < t["baseline_total"],
           f"mean baseline {t['baseline_total']:.4f}")
    report(f"{v}_fields_not_beating_mean", worse, not worse)
    report(f"{v}_per_field", {f["field"]: [round(f["held_out"], 4), round(f["mean_baseline"], 4)]
                              for f in t["per_field"]})
finish("training")
