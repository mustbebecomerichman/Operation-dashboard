#!/usr/bin/env python3
"""
Build comprehensive vessel dictionaries from 4 months of voyage data + the
latest master vessel registry.

Inputs:
  data/monthly/2026-01.xls .. 2026-04.xls
    Monthly voyage logs. Key columns:
      [1]  Op Svc      — operational service code (e.g. THS3, KJS1)
      [4]  Vessel      — 4-letter ship code
      [5]  Voyage      — voyage number
      [21] 자선여부      — Checked = own (HEUNG-A/SKR), Unchecked = chartered
  Vessel Code_2026-05-28.xls
    Master ship registry: 6149 vessels with IMO, name, dimensions, flag, etc.

Outputs:
  delay_dashboard.html VESSELS  — own-fleet vessel ↔ service mapping
  data/sched-non-own.json       — chartered vessels needing SeaVantage registration

A vessel can be both own AND chartered on different services across months (e.g.
AKTR is own on THS3 but chartered on KJS1 in 4월). Per-row 자선여부 governs.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

try:
    import xlrd
except ImportError:
    sys.exit("Install xlrd: pip install xlrd==1.2.0")

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "delay_dashboard.html"
MASTER = ROOT / "Vessel Code_2026-05-28.xls"
MONTHLY_DIR = ROOT / "data" / "monthly"
SCHED_NON_OWN = ROOT / "data" / "sched-non-own.json"


# ─── 1. Master vessel registry (code → full info) ────────────────────────────
def read_master(fn: Path) -> dict:
    """{code: {imo, name, flag, built, gt(GRT), dwt(SDWT), teu(14homo), loa, call}}"""
    wb = xlrd.open_workbook(str(fn))
    s = wb.sheets()[0]
    headers = [s.cell_value(0, c) for c in range(s.ncols)]
    idx = {h: i for i, h in enumerate(headers)}

    def num(row, col):
        if col is None:
            return 0
        v = row[col]
        try:
            return float(v) if isinstance(v, (int, float)) else (float(v) if v else 0)
        except (ValueError, TypeError):
            return 0

    def s_(row, col, default=''):
        if col is None:
            return default
        v = row[col]
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip() if v else default

    out = {}
    for r in range(1, s.nrows):
        row = [s.cell_value(r, c) for c in range(s.ncols)]
        code = s_(row, idx.get('Vessel'))
        if not code or len(code) > 8 or not re.match(r'^[A-Z0-9_-]+$', code):
            continue
        out[code] = {
            'code': code,
            'name': s_(row, idx.get('Vessel Name')),
            'flag': s_(row, idx.get('Flag')),
            'built': s_(row, idx.get('Built on'))[:4],  # YYYY only
            'gt': int(num(row, idx.get('GRT'))),
            'dwt': int(num(row, idx.get('Summer Dead Weight'))),
            'teu': int(num(row, idx.get('14 homo'))),
            'loa': round(num(row, idx.get('LOA')), 1),
            'call': s_(row, idx.get('Call Sign')),
            'imo': s_(row, idx.get('IMO Number')),
            'type': s_(row, idx.get('Kind of Vessel')) or 'Container',
        }
    return out


print("[1] Reading master registry…")
master = read_master(MASTER)
master_with_imo = sum(1 for v in master.values() if v['imo'] and v['imo'].isdigit() and len(v['imo']) == 7)
print(f"  -> {len(master)} vessels in master, {master_with_imo} with valid 7-digit IMO")

# Authoritative OWN-fleet list from HAL + SKR files. These two files define
# Heung-A Line's and Sinokor Marine's combined own fleet. Anything NOT in this
# set is treated as a charter vessel, regardless of what the monthly file's
# `자선여부` column says (that column is per-voyage and unreliable — a vessel
# can be marked own on one service and charter on another in the same month).
OWN_CODES = set()
for fn in [ROOT / "Vessel Code_HAL_2026-04-02.xls", ROOT / "Vessel Code_SKR_2026-04-02.xls"]:
    if not fn.exists():
        continue
    wb = xlrd.open_workbook(str(fn))
    s = wb.sheets()[0]
    for r in range(1, s.nrows):
        code = str(s.cell_value(r, 3)).strip() if s.cell_value(r, 3) else ''
        if code and re.match(r'^[A-Z0-9_-]+$', code) and len(code) <= 8:
            OWN_CODES.add(code)
print(f"  -> Authoritative OWN fleet (HAL+SKR): {len(OWN_CODES)} vessel codes")


# ─── 2. Aggregate 4 months of voyage data ────────────────────────────────────
def read_monthly(fn: Path) -> list:
    """Returns list of (code, svc, is_own) tuples."""
    wb = xlrd.open_workbook(str(fn))
    s = wb.sheets()[0]
    out = []
    for r in range(1, s.nrows):
        code = str(s.cell_value(r, 4)).strip()  # Vessel
        svc = str(s.cell_value(r, 1)).strip()   # Op Svc
        own_flag = str(s.cell_value(r, 21))     # 자선여부
        if not code or not svc:
            continue
        out.append((code, svc, own_flag == 'Checked'))
    return out


print("[2] Reading monthly voyage logs…")
all_voyages = []
for month_file in sorted(MONTHLY_DIR.glob("*.xls")):
    voyages = read_monthly(month_file)
    all_voyages.extend(voyages)
    print(f"  {month_file.name}: {len(voyages)} voyage rows")
print(f"  -> {len(all_voyages)} total voyage rows across 4 months")


# Build vessel → set of services. Bucket by AUTHORITATIVE own-codes set
# (HAL+SKR), NOT by the per-voyage 자선여부 column. That column flips for the
# same vessel across voyages (e.g. AKTR=THS3 Checked, AKTR=KJS1 Unchecked) and
# polluted the previous run with non-own vessels appearing as own.
own_assignments = defaultdict(set)
charter_assignments = defaultdict(set)
for code, svc, is_own_voyage in all_voyages:
    if code in OWN_CODES:
        own_assignments[code].add(svc)
    else:
        charter_assignments[code].add(svc)
print(f"  -> {len(own_assignments)} vessels matched HAL/SKR own list, "
      f"{len(charter_assignments)} non-own")


# ─── 3. Build VESSELS dict (own only) ────────────────────────────────────────
# Preserve any existing VESSELS entries whose code isn't in our data sources
# (manually-added historical records). Union services.
text = HTML.read_text(encoding='utf-8')
m_pre = re.search(r'var VESSELS = (\{.*?\});', text)
existing_full: dict[str, dict] = {}
existing_assignments: dict[str, set] = defaultdict(set)
if m_pre:
    for svc, vs in json.loads(m_pre.group(1)).items():
        for v in vs:
            existing_full[v['code']] = v
            existing_assignments[v['code']].add(svc)

print("[3] Building VESSELS (own fleet) dict…")
# IMPORTANT: VESSELS contains ONLY codes from the HAL+SKR authoritative own
# list. Any non-own vessel (slot-share / charter) goes to sched-non-own.json
# instead. Iterating OWN_CODES guarantees no charter vessel is mis-flagged as
# own — the previous union-of-sources approach pulled in mis-classified entries
# from the existing VESSELS dict.
vessels_out = defaultdict(list)
for code in OWN_CODES:
    services = set(own_assignments.get(code, set()))
    # Preserve service assignments from existing VESSELS, but only if the code
    # is genuinely own (i.e. it IS in OWN_CODES — guaranteed by this loop).
    services |= existing_assignments.get(code, set())
    if not services:
        continue
    info = master.get(code) or existing_full.get(code) or {
        'code': code, 'name': '', 'imo': '', 'flag': '',
        'built': '', 'gt': 0, 'dwt': 0, 'teu': 0, 'loa': 0.0,
        'call': '', 'type': 'Container'
    }
    base = {**info}
    base['owner'] = '사선'
    if base.get('type') == 'Container':
        base['type'] = 'CNTR'
    base = {k: v for k, v in base.items() if not k.startswith('_')}
    for svc in services:
        vessels_out[svc].append(base.copy())

# Sort vessels within each service by TEU desc
for svc in vessels_out:
    vessels_out[svc].sort(key=lambda v: -(v.get('teu') or 0))
vessels_out = dict(sorted(vessels_out.items()))
print(f"  -> {len(vessels_out)} services, {sum(len(v) for v in vessels_out.values())} total entries (HAL+SKR only)")


# ─── 4. Update VESSELS in HTML ───────────────────────────────────────────────
new_blob = json.dumps(vessels_out, ensure_ascii=False, separators=(',', ': '))
new_text, n = re.subn(r'var VESSELS = \{.*?\};', f'var VESSELS = {new_blob};', text, count=1, flags=re.DOTALL)
if n != 1:
    sys.exit("VESSELS substitution failed")
HTML.write_text(new_text, encoding='utf-8')
print(f"  -> VESSELS line updated")


# ─── 5. Build sched-non-own.json (charter vessels for SeaVantage register) ──
# Union of three sources to maximize SeaVantage coverage:
#   (a) Monthly 1-4월 charter assignments (specific, recent)
#   (b) Schedule Code 2026-03-31 (broader, may include future planned voyages)
#   (c) Existing data/sched-non-own.json (preserve any prior curation)
print("[4] Building sched-non-own.json (charter vessels)…")

# Load existing list to preserve
existing_non_own: dict[str, dict] = {}
if SCHED_NON_OWN.exists():
    for v in json.loads(SCHED_NON_OWN.read_text(encoding='utf-8')):
        existing_non_own[v['code']] = v

# Read Schedule Code 2026-03-31 charter assignments too
schedule_charter_assignments: dict[str, set] = defaultdict(set)
sched_path = ROOT / 'Schedule Code_2026-03-31.xls'
if sched_path.exists():
    wb_s = xlrd.open_workbook(str(sched_path))
    ss = wb_s.sheets()[0]
    sheader = {ss.cell_value(0, c): c for c in range(ss.ncols)}
    vsl_i = sheader.get('VSL')
    svc_i = sheader.get('SVC')
    own_i = sheader.get('OWN')
    for r in range(1, ss.nrows):
        code = str(ss.cell_value(r, vsl_i)).strip()
        svc = str(ss.cell_value(r, svc_i)).strip()
        own = ss.cell_value(r, own_i)
        if not code or not svc:
            continue
        if not own:  # empty OWN = charter
            schedule_charter_assignments[code].add(svc)
    print(f"  Schedule Code 2026-03-31: {len(schedule_charter_assignments)} charter vessels")

# Union all three
all_charter_codes = set(charter_assignments.keys()) | set(schedule_charter_assignments.keys()) | set(existing_non_own.keys())

non_own_out = []
skipped_no_master = 0
skipped_no_imo = 0
for code in sorted(all_charter_codes):
    info = master.get(code)
    imo = (info or {}).get('imo', '')
    # Fall back to existing record's IMO if master missing
    if (not imo or not imo.isdigit() or len(imo) != 7) and code in existing_non_own:
        existing_imo = existing_non_own[code].get('imo', '')
        if existing_imo and existing_imo.isdigit() and len(existing_imo) == 7:
            imo = existing_imo
            info = info or existing_non_own[code]
    if not info:
        skipped_no_master += 1
        continue
    if not (imo and imo.isdigit() and len(imo) == 7):
        skipped_no_imo += 1
        continue
    # Combine services from all sources
    services = (
        charter_assignments.get(code, set())
        | schedule_charter_assignments.get(code, set())
        | set(existing_non_own.get(code, {}).get('services', []))
    )
    non_own_out.append({
        'code': code,
        'imo': imo,
        'name': info.get('name', '') or existing_non_own.get(code, {}).get('name', ''),
        'flag': info.get('flag', '') or existing_non_own.get(code, {}).get('flag', ''),
        'services': sorted(services),
    })
SCHED_NON_OWN.write_text(json.dumps(non_own_out, ensure_ascii=False, separators=(",", ":")), encoding='utf-8')
print(f"  -> {len(non_own_out)} charter vessels with valid IMO -> {SCHED_NON_OWN.relative_to(ROOT)}")
print(f"     skipped: {skipped_no_master} not in master, {skipped_no_imo} missing/invalid IMO")


# ─── 6. Coverage report ──────────────────────────────────────────────────────
print()
print("[5] Coverage:")
m_routes = re.search(r'var ROUTES = (\{.*?\});', new_text)
routes = json.loads(m_routes.group(1))
empty_own = [svc for svc in routes if svc not in vessels_out]
print(f"  Routes with no OWN vessels: {len(empty_own)} / {len(routes)}")
if empty_own:
    print(f"    {empty_own}")

# Cross-ref charter-only routes
charter_only_routes = set()
for v in non_own_out:
    for svc in v['services']:
        charter_only_routes.add(svc)
print(f"  Services with at least one charter vessel: {len(charter_only_routes)}")
covered_routes = set(vessels_out.keys()) | charter_only_routes
known_routes = set(routes.keys())
truly_empty = known_routes - covered_routes
print(f"  Routes with NO vessels (own or charter) tracked anywhere: {len(truly_empty)}")
if truly_empty:
    print(f"    {sorted(truly_empty)}")
