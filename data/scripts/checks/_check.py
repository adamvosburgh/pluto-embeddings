"""Tiny helper shared by the checks: record pass/fail lines, exit non-zero on any failure."""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common import p, write_json

FAILS = []
RESULTS = {}


def report(name, value, ok=True, note=""):
    RESULTS[name] = value
    flag = "ok  " if ok else "FAIL"
    print(f"{flag} {name}: {value}{'  (' + note + ')' if note else ''}", flush=True)
    if not ok:
        FAILS.append(name)


def finish(check):
    path = p("checks.json")
    allr = json.load(open(path)) if os.path.exists(path) else {}
    allr[check] = {"results": RESULTS, "failures": FAILS}
    write_json(path, allr)
    print(f"[{check}] {'PASS' if not FAILS else 'FAIL: ' + ', '.join(FAILS)}", flush=True)
    sys.exit(1 if FAILS else 0)
