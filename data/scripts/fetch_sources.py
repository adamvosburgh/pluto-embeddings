#!/usr/bin/env python3
"""Fetch the ACS tables and building footprints for the PLUTO embeddings sandbox.

Standard library only. Run from the repo root:

    python3 data/scripts/fetch_sources.py            # everything
    python3 data/scripts/fetch_sources.py acs        # ACS only
    python3 data/scripts/fetch_sources.py trees      # street trees only

Environment variables:
    CENSUS_API_KEY     required. The Census API now refuses requests without one.
                       Free: https://api.census.gov/data/key_signup.html
    SOCRATA_APP_TOKEN  optional, avoids NYC Open Data throttling

Writes to data/original/ (gitignored):
    acs-bg/<TABLE>.csv           block group detailed tables, all five counties, ACS 2020-2024 5-year
    acs-bg/<TABLE>.labels.json   variable labels for that table
    acs-tract/DP04.csv, DP05.csv tract data profiles, same release
    trees/street_trees_2015.csv  2015 Street Tree Census (uvpi-gqnh), citywide

Building footprints are not fetched. footprints/BUILDING_20260830.geojson was copied
from smt-fa2026/data/original/ (NYC Open Data 5zhs-2jue, downloaded 2026-08-30).
    fetch_log.txt                what succeeded, what failed, row counts

A file that already exists and passes validation is skipped. Re-running fills gaps.
"""
import csv, json, os, sys, time, urllib.parse, urllib.request, urllib.error

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "original"))
YEAR = "2024"  # ACS 2020-2024 5-year, released January 2026
API = f"https://api.census.gov/data/{YEAR}/acs/acs5"
STATE = "36"
COUNTIES = {"005": "Bronx", "047": "Kings", "061": "New York", "081": "Queens", "085": "Richmond"}
UA = "smt-fa2026/1.0 (Columbia GSAPP course site; adamvosburgh@gmail.com)"
EXPECTED_BG = 6807      # NYC block groups, per GEOINFO 2020-2025

# Block group detailed tables. "housing" ~ DP04, "demographic" ~ DP05.
TABLES = {
    "housing": [
        "B25001",  # housing units
        "B25002",  # occupancy status
        "B25003",  # tenure
        "B25010",  # average household size by tenure
        "B25014",  # tenure by occupants per room
        "B25017",  # rooms
        "B25018",  # median rooms
        "B25024",  # units in structure
        "B25034",  # year structure built
        "B25035",  # median year structure built
        "B25038",  # tenure by year householder moved in
        "B25040",  # house heating fuel
        "B25041",  # bedrooms
        "B25044",  # tenure by vehicles available
        "B25047",  # plumbing facilities
        "B25051",  # kitchen facilities
        "B25063",  # gross rent
        "B25064",  # median gross rent
        "B25070",  # gross rent as % of household income
        "B25075",  # value
        "B25077",  # median value
        "B25081",  # mortgage status
        "B25091",  # mortgage status by owner costs as % of income
    ],
    "demographic": [
        "B01001",  # sex by age
        "B01002",  # median age by sex
        "B01003",  # total population
        "B02001",  # race
        "B03002",  # Hispanic or Latino origin by race
    ],
}
TRACT_PROFILES = ["DP04", "DP05"]

LOG = []
def log(msg):
    print(msg, flush=True)
    LOG.append(msg)

def get(url, tries=4, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tok = os.environ.get("SOCRATA_APP_TOKEN")
    if tok and "cityofnewyork" in url:
        req.add_header("X-App-Token", tok)
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            msg = e.read()[:300].decode("utf-8", "replace")
            if e.code in (400, 204):          # bad variable / no data: not worth retrying
                raise ValueError(f"HTTP {e.code}: {msg}")
            err = f"HTTP {e.code}: {msg}"
            time.sleep(2 * (i + 1))
            continue
        except Exception as e:
            err = repr(e)
            time.sleep(2 * (i + 1))
            continue
        # A 200 with an error page or error JSON is never fixed by retrying.
        if b"Missing Key" in body[:400] or b"Invalid Key" in body[:400]:
            raise SystemExit("Census API key missing or invalid. Set CENSUS_API_KEY and run again.")
        if body[:1] == b"<" or body.startswith(b'{"code"') or body.startswith(b'{"error'):
            raise ValueError("error body: " + body[:200].decode("utf-8", "replace"))
        return body
    raise RuntimeError(f"failed after {tries} tries: {err} :: {url}")

def census(params):
    key = os.environ.get("CENSUS_API_KEY")
    if key:
        params = params + [("key", key)]
    return json.loads(get(API_BASE + "?" + urllib.parse.urlencode(params, safe=":*(),")))

def valid_csv(path, min_rows):
    if not os.path.exists(path):
        return False
    with open(path, newline="", encoding="utf-8") as f:
        first = f.read(1)
        if first in ("{", "<", ""):
            return False
        f.seek(0)
        n = sum(1 for _ in csv.reader(f)) - 1
    return n >= min_rows

def write_rows(path, header, rows):
    tmp = path + ".part"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)

def fetch_bg_table(table, kind):
    out = os.path.join(ROOT, "acs-bg", f"{table}.csv")
    if valid_csv(out, EXPECTED_BG):
        log(f"skip  {table} (already valid)")
        return
    header, rows = None, []
    for c in COUNTIES:
        data = census([("get", f"NAME,group({table})"), ("for", "block group:*"),
                       ("in", f"state:{STATE}"), ("in", f"county:{c}"), ("in", "tract:*")])
        h, body = data[0], data[1:]
        if header is None:
            header = h
        elif h != header:
            raise ValueError(f"{table}: header differs in county {c}")
        rows += body
        time.sleep(0.3)
    write_rows(out, header, rows)
    labels = json.loads(get(f"{API}/groups/{table}.json"))
    with open(os.path.join(ROOT, "acs-bg", f"{table}.labels.json"), "w") as f:
        json.dump({k: v.get("label") for k, v in labels.get("variables", {}).items()}, f, indent=1)
    flag = "" if len(rows) == EXPECTED_BG else f"  CHECK: expected {EXPECTED_BG}"
    log(f"ok    {table} [{kind}] {len(rows)} block groups, {len(header)} columns{flag}")

def fetch_tract_profile(table):
    out = os.path.join(ROOT, "acs-tract", f"{table}.csv")
    if valid_csv(out, 2000):
        log(f"skip  {table} (already valid)")
        return
    global API_BASE
    API_BASE = API + "/profile"
    try:
        data = census([("get", f"NAME,group({table})"), ("for", "tract:*"),
                       ("in", f"state:{STATE}"), ("in", "county:" + ",".join(COUNTIES))])
    finally:
        API_BASE = API
    write_rows(out, data[0], data[1:])
    labels = json.loads(get(f"{API}/profile/groups/{table}.json"))
    with open(os.path.join(ROOT, "acs-tract", f"{table}.labels.json"), "w") as f:
        json.dump({k: v.get("label") for k, v in labels.get("variables", {}).items()}, f, indent=1)
    log(f"ok    {table} {len(data) - 1} tracts, {len(data[0])} columns")

def fetch_trees():
    out = os.path.join(ROOT, "trees", "street_trees_2015.csv")
    if valid_csv(out, 600_000):
        log("skip  trees (already valid)")
        return
    base = "https://data.cityofnewyork.us/resource/uvpi-gqnh.csv"
    page, offset, n = 50000, 0, 0
    tmp = out + ".part"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        while True:
            q = urllib.parse.urlencode({"$order": "tree_id", "$limit": page, "$offset": offset})
            text = get(f"{base}?{q}", timeout=300).decode("utf-8")
            lines = text.splitlines(keepends=True)
            if not lines:
                break
            f.writelines(lines if offset == 0 else lines[1:])   # header once
            got = len(list(csv.reader(lines))) - 1
            n += got
            print(f"  trees {n:,}", flush=True)
            if got < page:
                break
            offset += page
    os.replace(tmp, out)
    log(f"ok    trees {n:,} records")

API_BASE = API

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    for d in ("acs-bg", "acs-tract", "trees"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    if what in ("all", "acs"):
        if not os.environ.get("CENSUS_API_KEY"):
            sys.exit("Set CENSUS_API_KEY first. Free key: https://api.census.gov/data/key_signup.html")
        for kind, tables in TABLES.items():
            for t in tables:
                try:
                    fetch_bg_table(t, kind)
                except Exception as e:
                    log(f"FAIL  {t} [{kind}]: {e}")
        for t in TRACT_PROFILES:
            try:
                fetch_tract_profile(t)
            except Exception as e:
                log(f"FAIL  {t}: {e}")
    if what in ("all", "trees"):
        try:
            fetch_trees()
        except Exception as e:
            log(f"FAIL  trees: {e}")
    with open(os.path.join(ROOT, "fetch_log.txt"), "a") as f:
        f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M')} ({what})\n" + "\n".join(LOG) + "\n")
    fails = [l for l in LOG if l.startswith("FAIL")]
    print(f"\n{len(fails)} failures. Log: data/original/fetch_log.txt")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
