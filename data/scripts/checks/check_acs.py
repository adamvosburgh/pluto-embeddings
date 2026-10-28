"""Check: ACS block group tables and features (after 05_acs.py)."""
from _check import *

s = json.load(open(p("acs_features.json")))
bad = {t: n for t, n in s["rows_per_table"].items() if n != 6807}
report("rows_per_table_all_6807", not bad, not bad, str(bad) if bad else "")
report("block_groups", s["block_groups"], s["block_groups"] == 6807)
report("acs_empty_block_groups", s["acs_empty_block_groups"], True, "doc: 411 with zero population")
report("not_in_geoinfo", s["not_in_geoinfo"], s["not_in_geoinfo"] == 0)
med = {k: m["n_empty"] for k, m in s["features"].items() if m["group"] == "median"}
report("median_value_empty", med["med_value"], True, "doc: B25077 missing for 2,669")
report("median_rent_empty", med["med_rent"], True, "doc: B25064 missing for 1,228")
report("empty_per_feature", {k: m["n_empty"] for k, m in s["features"].items()})
finish("acs")
