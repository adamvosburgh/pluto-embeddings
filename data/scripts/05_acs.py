"""05: block group ACS features, selected by label text (never by variable number).

Counts become shares of the table's universe. Negative sentinels (-666666666 and the like)
become missing. Medians are kept for the tooltip only.

Reads  data/original/acs-bg/<TABLE>.csv + .labels.json, acs-dp04/GEOINFO2024.GEOINFO-Data.csv
Writes data/processed/acs_bg.parquet   one row per block group (geoid, 12 chars)
       data/processed/acs_features.json  feature -> group, label, table, numerator and
                                         denominator variables with their label text, empties
"""
import json, os
import numpy as np, pandas as pd
from common import *

T = Timer("05_acs")
TABLES, LABELS = {}, {}


def table(t):
    if t not in TABLES:
        d = pd.read_csv(os.path.join(ACS_BG, f"{t}.csv"), dtype=str)
        d = d.loc[:, ~d.columns.str.match(r"^NAME\.\d+$")]   # NAME comes back twice
        d["geoid"] = d["GEO_ID"].str[-12:]
        TABLES[t] = d.set_index("geoid")
        lab = json.load(open(os.path.join(ACS_BG, f"{t}.labels.json"), encoding="utf-8"))
        LABELS[t] = {v: l for v, l in lab.items() if v.endswith("E") and l and l.startswith("Estimate!!")}
    return TABLES[t]


def var(t, label):
    """The estimate variable whose label, after 'Estimate!!', is exactly `label`."""
    table(t)
    hits = [v for v, l in LABELS[t].items() if l[len("Estimate!!"):] == label]
    if len(hits) != 1:
        raise SystemExit(f"{t}: label {label!r} matched {hits}")
    return hits[0]


def col(t, label):
    v = var(t, label)
    x = pd.to_numeric(table(t)[v], errors="coerce")
    return x.where(x >= 0), {"var": v, "label": label}


FEATURES, META = {}, {}


def share(name, group, label, t, num_labels, den_label, den_minus=()):
    num, used = 0, []
    for l in num_labels:
        x, m = col(t, l)
        num = num + x
        used.append(m)
    den, dm = col(t, den_label)
    minus = []
    for l in den_minus:
        x, m = col(t, l)
        den = den - x
        minus.append(m)
    FEATURES[name] = (num / den.where(den > 0)).clip(0, 1)
    META[name] = {"group": group, "label": label, "kind": "share", "table": t,
                  "numerator": used, "denominator": dm, "denominator_minus": minus}


def value(name, group, label, t, lab, kind="value", unit=""):
    x, m = col(t, lab)
    FEATURES[name] = x
    META[name] = {"group": group, "label": label, "kind": kind, "unit": unit, "table": t, "variable": m}


# --- housing -----------------------------------------------------------------------------
share("vacancy", "housing", "Vacant share", "B25002", ["Total:!!Vacant"], "Total:")
share("renter", "housing", "Renter-occupied share", "B25003", ["Total:!!Renter occupied"], "Total:")
U = "Total:!!"
share("units_1", "housing", "Units in structure: 1", "B25024", [U + "1, detached", U + "1, attached"], "Total:")
share("units_2_4", "housing", "Units in structure: 2–4", "B25024", [U + "2", U + "3 or 4"], "Total:")
share("units_5_19", "housing", "Units in structure: 5–19", "B25024", [U + "5 to 9", U + "10 to 19"], "Total:")
share("units_20_49", "housing", "Units in structure: 20–49", "B25024", [U + "20 to 49"], "Total:")
share("units_50p", "housing", "Units in structure: 50+", "B25024", [U + "50 or more"], "Total:")
share("built_pre1940", "housing", "Built before 1940", "B25034", [U + "Built 1939 or earlier"], "Total:")
share("built_1940_1969", "housing", "Built 1940–1969", "B25034",
      [U + "Built 1940 to 1949", U + "Built 1950 to 1959", U + "Built 1960 to 1969"], "Total:")
share("built_1970_1999", "housing", "Built 1970–1999", "B25034",
      [U + "Built 1970 to 1979", U + "Built 1980 to 1989", U + "Built 1990 to 1999"], "Total:")
share("built_2000_2009", "housing", "Built 2000–2009", "B25034", [U + "Built 2000 to 2009"], "Total:")
share("built_2010p", "housing", "Built 2010 or later", "B25034",
      [U + "Built 2010 to 2019", U + "Built 2020 or later"], "Total:")
share("bed_0", "housing", "Bedrooms: none", "B25041", [U + "No bedroom"], "Total:")
share("bed_1", "housing", "Bedrooms: 1", "B25041", [U + "1 bedroom"], "Total:")
share("bed_2", "housing", "Bedrooms: 2", "B25041", [U + "2 bedrooms"], "Total:")
share("bed_3p", "housing", "Bedrooms: 3 or more", "B25041",
      [U + "3 bedrooms", U + "4 bedrooms", U + "5 or more bedrooms"], "Total:")
crowd = [f"Total:!!{t}:!!{b}" for t in ("Owner occupied", "Renter occupied")
         for b in ("1.01 to 1.50 occupants per room", "1.51 to 2.00 occupants per room", "2.01 or more occupants per room")]
share("crowded", "housing", "More than 1 occupant per room", "B25014", crowd, "Total:")
moved = [f"Total:!!{t}:!!{b}" for t in ("Owner occupied", "Renter occupied")
         for b in ("Moved in 2023 or later", "Moved in 2020 to 2022", "Moved in 2010 to 2019")]
share("moved_2010p", "housing", "Moved in 2010 or later", "B25038", moved, "Total:")
share("no_vehicle", "housing", "No vehicle available", "B25044",
      ["Total:!!Owner occupied:!!No vehicle available", "Total:!!Renter occupied:!!No vehicle available"], "Total:")
share("heat_gas", "housing", "Heating fuel: utility gas", "B25040", [U + "Utility gas"], "Total:")
share("heat_electric", "housing", "Heating fuel: electricity", "B25040", [U + "Electricity"], "Total:")
share("heat_oil", "housing", "Heating fuel: fuel oil", "B25040", [U + "Fuel oil, kerosene, etc."], "Total:")
share("heat_other", "housing", "Heating fuel: other or none", "B25040",
      [U + "Bottled or tank gas (propane, butane, etc.)", U + "Coal or coke", U + "Wood",
       U + "Solar energy", U + "Other fuel", U + "No fuel used"], "Total:")
share("lack_plumbing", "housing", "Lacking complete plumbing", "B25047", [U + "Lacking complete plumbing facilities"], "Total:")
share("lack_kitchen", "housing", "Lacking complete kitchen", "B25051", [U + "Lacking complete kitchen facilities"], "Total:")
value("avg_hh_size", "housing", "Average household size", "B25010", "Average household size --!!Total:", unit="persons")

# --- housing cost (tagged "cost") ---------------------------------------------------------
burden = ["30.0 to 34.9 percent", "35.0 to 39.9 percent", "40.0 to 49.9 percent", "50.0 percent or more"]
share("rent_burden30", "cost", "Rent ≥ 30% of income", "B25070", [U + b for b in burden], "Total:",
      den_minus=[U + "Not computed"])
M, N = "Total:!!Housing units with a mortgage:", "Total:!!Housing units without a mortgage:"
share("owner_burden30", "cost", "Owner costs ≥ 30% of income", "B25091",
      [f"{M}!!{b}" for b in burden] + [f"{N}!!{b}" for b in burden], "Total:",
      den_minus=[f"{M}!!Not computed", f"{N}!!Not computed"])
share("with_mortgage", "cost", "With a mortgage", "B25081",
      ["Total:!!Housing units with a mortgage, contract to purchase, or similar debt:"], "Total:")

# Gross rent bands, edges chosen from the B25063 label text (of renters paying cash rent).
R = "Total:!!With cash rent:!!"
rent_bins = {
    "rent_lt1000": ("Gross rent: under $1,000", ["Less than $100", "$100 to $149", "$150 to $199", "$200 to $249",
                    "$250 to $299", "$300 to $349", "$350 to $399", "$400 to $449", "$450 to $499", "$500 to $549",
                    "$550 to $599", "$600 to $649", "$650 to $699", "$700 to $749", "$750 to $799", "$800 to $899",
                    "$900 to $999"]),
    "rent_1000_1499": ("Gross rent: $1,000–$1,499", ["$1,000 to $1,249", "$1,250 to $1,499"]),
    "rent_1500_1999": ("Gross rent: $1,500–$1,999", ["$1,500 to $1,999"]),
    "rent_2000_2999": ("Gross rent: $2,000–$2,999", ["$2,000 to $2,499", "$2,500 to $2,999"]),
    "rent_3000p": ("Gross rent: $3,000 or more", ["$3,000 to $3,499", "$3,500 or more"]),
}
for k, (lab, bands) in rent_bins.items():
    share(k, "cost", lab, "B25063", [R + b for b in bands], "Total:!!With cash rent:")

# Home value bands, edges chosen from the B25075 label text (of owner-occupied units).
value_bins = {
    "value_lt300k": ("Value: under $300,000", ["Less than $10,000", "$10,000 to $14,999", "$15,000 to $19,999",
                     "$20,000 to $24,999", "$25,000 to $29,999", "$30,000 to $34,999", "$35,000 to $39,999",
                     "$40,000 to $49,999", "$50,000 to $59,999", "$60,000 to $69,999", "$70,000 to $79,999",
                     "$80,000 to $89,999", "$90,000 to $99,999", "$100,000 to $124,999", "$125,000 to $149,999",
                     "$150,000 to $174,999", "$175,000 to $199,999", "$200,000 to $249,999", "$250,000 to $299,999"]),
    "value_300_499k": ("Value: $300,000–$499,999", ["$300,000 to $399,999", "$400,000 to $499,999"]),
    "value_500_749k": ("Value: $500,000–$749,999", ["$500,000 to $749,999"]),
    "value_750_999k": ("Value: $750,000–$999,999", ["$750,000 to $999,999"]),
    "value_1mp": ("Value: $1,000,000 or more", ["$1,000,000 to $1,499,999", "$1,500,000 to $1,999,999", "$2,000,000 or more"]),
}
for k, (lab, bands) in value_bins.items():
    share(k, "cost", lab, "B25075", [U + b for b in bands], "Total:")

# --- demographic ---------------------------------------------------------------------------
def ages(*bands):
    return [f"Total:!!{s}:!!{b}" for s in ("Male", "Female") for b in bands]


share("age_u18", "demographic", "Age under 18", "B01001",
      ages("Under 5 years", "5 to 9 years", "10 to 14 years", "15 to 17 years"), "Total:")
share("age_18_34", "demographic", "Age 18–34", "B01001",
      ages("18 and 19 years", "20 years", "21 years", "22 to 24 years", "25 to 29 years", "30 to 34 years"), "Total:")
share("age_35_64", "demographic", "Age 35–64", "B01001",
      ages("35 to 39 years", "40 to 44 years", "45 to 49 years", "50 to 54 years", "55 to 59 years",
           "60 and 61 years", "62 to 64 years"), "Total:")
share("age_65p", "demographic", "Age 65 and over", "B01001",
      ages("65 and 66 years", "67 to 69 years", "70 to 74 years", "75 to 79 years", "80 to 84 years",
           "85 years and over"), "Total:")
NH = "Total:!!Not Hispanic or Latino:"
share("hispanic", "demographic", "Hispanic or Latino", "B03002", ["Total:!!Hispanic or Latino:"], "Total:")
share("nh_white", "demographic", "Non-Hispanic White", "B03002", [NH + "!!White alone"], "Total:")
share("nh_black", "demographic", "Non-Hispanic Black", "B03002", [NH + "!!Black or African American alone"], "Total:")
share("nh_asian", "demographic", "Non-Hispanic Asian", "B03002", [NH + "!!Asian alone"], "Total:")
share("nh_other", "demographic", "Non-Hispanic other or two or more", "B03002",
      [NH + "!!American Indian and Alaska Native alone", NH + "!!Native Hawaiian and Other Pacific Islander alone",
       NH + "!!Some other race alone", NH + "!!Two or more races:"], "Total:")

pop, popm = col("B01003", "Total")
geo = pd.read_csv(GEOINFO, dtype=str, skiprows=[1])
geo = geo.loc[:, ~geo.columns.str.startswith("Unnamed")]
geo["geoid"] = geo["GEO_ID"].str[-12:]
geo = geo.set_index("geoid")
aland = pd.to_numeric(geo["AREALAND"], errors="coerce").reindex(pop.index)
FEATURES["pop_density"] = pop / (aland.where(aland > 0) / 2_589_988.110336)
META["pop_density"] = {"group": "demographic", "label": "Population density", "kind": "density",
                       "unit": "people per sq mi", "table": "B01003", "variable": popm,
                       "denominator": {"source": "GEOINFO2024 AREALAND (square meters)", "per": "square mile"}}

# --- tooltip medians -----------------------------------------------------------------------
MED = {}
for k, t, lab, unit, label in [("med_rooms", "B25018", "Median number of rooms", "rooms", "Median rooms"),
                               ("med_year_built", "B25035", "Median year structure built", "year", "Median year built"),
                               ("med_rent", "B25064", "Median gross rent", "$", "Median gross rent"),
                               ("med_value", "B25077", "Median value (dollars)", "$", "Median home value"),
                               ("med_age", "B01002", "Median age --!!Total:", "years", "Median age")]:
    x, m = col(t, lab)
    MED[k] = x
    META[k] = {"group": "median", "label": label, "kind": "median", "unit": unit, "table": t, "variable": m}

idx = pop.index
out = pd.DataFrame({"geoid": idx, "name": table("B01003").loc[idx, "NAME"].to_numpy(), "population": pop.to_numpy()})
for k, v in {**FEATURES, **MED}.items():
    out[k] = v.reindex(idx).to_numpy(dtype=np.float64)
out["acs_empty"] = ~(out["population"] > 0)
feat_cols = list(FEATURES)
out.loc[out["acs_empty"], feat_cols] = np.nan
out["in_geoinfo"] = out["geoid"].isin(geo.index)

for k in META:
    META[k]["n_empty"] = int(out[k].isna().sum())
summary = {
    "block_groups": len(out),
    "rows_per_table": {t: len(d) for t, d in TABLES.items()},
    "acs_empty_block_groups": int(out["acs_empty"].sum()),
    "not_in_geoinfo": int((~out["in_geoinfo"]).sum()),
    "features": META,
}
out.to_parquet(p("acs_bg.parquet"), index=False)
write_json(p("acs_features.json"), summary)
for k, m in META.items():
    print(f"  {k:18s} {m['group']:12s} empty {m['n_empty']:5d}", flush=True)
print(f"block groups {len(out):,}; acs_empty {summary['acs_empty_block_groups']}", flush=True)
T.done()
