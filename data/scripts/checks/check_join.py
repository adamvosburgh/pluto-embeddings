"""Check: block group join from BCTCB2020 (after 01_lots.py)."""
from _check import *
from common import GEOINFO
import pandas as pd

lots = pd.read_parquet(p("lots.parquet"), columns=["bbl", "geoid", "BCTCB2020"])
geo = pd.read_csv(GEOINFO, dtype=str, skiprows=[1])
geo_ids = set(geo["GEO_ID"].str[-12:])
has = lots["geoid"] != ""
report("lots", len(lots), len(lots) == 856_687)
report("lots_with_block_group", int(has.sum()), int(has.sum()) == 856_664)
report("lots_without_block_group", int((~has).sum()), int((~has).sum()) == 23)
report("bctcb2020_lengths_without", lots.loc[~has, "BCTCB2020"].fillna("").astype(str).str.len().value_counts().to_dict())
report("distinct_block_groups_used", int(lots.loc[has, "geoid"].nunique()), int(lots.loc[has, "geoid"].nunique()) == 6625)
missing = ~lots.loc[has, "geoid"].isin(geo_ids)
report("lot_geoids_not_in_geoinfo", int(missing.sum()), int(missing.sum()) == 0)
finish("join")
