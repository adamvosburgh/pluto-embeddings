"""Check: building footprints read and joined (after 03_footprints.py)."""
from _check import *

s = json.load(open(p("footprints_summary.json")))
report("features_read", s["features_read"], s["features_read"] == 1_083_026)
report("joined_share", f"{s['joined_share']:.2%}", s["joined_share"] >= 0.995, "doc: 99.9%")
report("lots_with_footprint_any_code", s["lots_with_footprint_any_code"],
       abs(s["lots_with_footprint_any_code"] - 816_746) <= 2_000, "doc: 816,746")
report("lots_with_building_or_garage", s["lots_with_building_or_garage"])
report("height_missing_or_zero", s["height_missing_or_zero"], True, "doc: 3 null + 733 zero = 736")
report("feature_codes", s["feature_codes"])
finish("footprints")
