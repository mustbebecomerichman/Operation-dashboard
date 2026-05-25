#!/usr/bin/env python3
"""
Build a JSON of non-own (비자자선) vessels from Schedule Code + Vessel Code Excel.

Output: data/sched-non-own.json
Shape:  [{"code","imo","name","flag","services":[...]}]

Run after each new Schedule Code / Vessel Code drop:
    python scripts/build-sched-non-own.py

The dashboard's "Bulk Register Schedule Vessels" admin button reads this file
to drive SeaVantage workspace registration.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    import xlrd
except ImportError:
    print("xlrd not installed. Run: pip install xlrd==1.2.0", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SCHED = ROOT / "Schedule Code_2026-03-31.xls"
REG   = ROOT / "Vessel Code_2026-03-31.xls"
OUT   = ROOT / "data" / "sched-non-own.json"


def load_sched() -> dict[str, dict]:
    """{code: {'own': bool, 'services': set}}"""
    wb = xlrd.open_workbook(str(SCHED))
    s = wb.sheets()[0]
    cols = {s.cell_value(0, c): c for c in range(s.ncols)}
    result: dict[str, dict] = {}
    for r in range(1, s.nrows):
        code = s.cell_value(r, cols["VSL"])
        own = s.cell_value(r, cols["OWN"])
        svc = s.cell_value(r, cols["SVC"])
        if not code:
            continue
        entry = result.setdefault(code, {"own": False, "services": set()})
        if own:
            entry["own"] = True
        if svc:
            entry["services"].add(svc)
    return result


def load_registry() -> dict[str, dict]:
    """{code: {'imo','name','flag'}}"""
    wb = xlrd.open_workbook(str(REG))
    s = wb.sheets()[0]
    cols = {s.cell_value(0, c): c for c in range(s.ncols)}
    result: dict[str, dict] = {}
    for r in range(1, s.nrows):
        code = s.cell_value(r, cols["Vessel"])
        if not code:
            continue
        imo = str(s.cell_value(r, cols["IMO Number"])).strip()
        if imo == "Imo no":  # header in second row (skip junk)
            continue
        name = s.cell_value(r, cols["Vessel Name"])
        flag = s.cell_value(r, cols["Port of"])
        if code not in result:
            result[code] = {"imo": imo, "name": name, "flag": flag}
    return result


def main() -> None:
    sched = load_sched()
    registry = load_registry()

    out: list[dict] = []
    skipped_no_reg = []
    skipped_no_imo = []
    for code, info in sched.items():
        if info["own"]:
            continue
        reg = registry.get(code)
        if not reg:
            skipped_no_reg.append(code)
            continue
        imo = reg["imo"]
        if not imo or imo == "0":
            skipped_no_imo.append(code)
            continue
        # Skip codes whose IMO looks malformed (anything not 7 digits)
        if not (imo.isdigit() and len(imo) == 7):
            skipped_no_imo.append(code)
            continue
        out.append({
            "code": code,
            "imo": imo,
            "name": reg["name"],
            "flag": reg["flag"],
            "services": sorted(info["services"]),
        })

    out.sort(key=lambda v: v["code"])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"Wrote {OUT.relative_to(ROOT)}: {len(out)} non-own vessels with IMO")
    print(f"  Skipped (not in registry): {len(skipped_no_reg)}")
    print(f"  Skipped (no/invalid IMO):  {len(skipped_no_imo)}")
    if skipped_no_reg:
        print(f"  First 5 no-registry:  {skipped_no_reg[:5]}")
    if skipped_no_imo:
        print(f"  First 5 no-IMO:       {skipped_no_imo[:5]}")


if __name__ == "__main__":
    main()
