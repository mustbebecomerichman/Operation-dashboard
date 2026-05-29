#!/usr/bin/env python3
"""
Rebuild VESSELS dictionary in delay_dashboard.html from:
  1. Vessel Code_HAL_2026-04-02.xls + Vessel Code_SKR_2026-04-02.xls
     → master own-fleet data (code, name, IMO, GT, DWT, TEU, LOA, flag, built, etc.)
  2. Schedule Code_2026-03-31.xls
     → vessel ↔ service assignment (column VSL × SVC)

A vessel can run on multiple services; this script lists it under EVERY service
it has been seen on per Schedule Code, ensuring no route is left with an empty
vessel list when there's a known assignment.

Run after each Excel drop:
    python scripts/rebuild-vessels.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

try:
    import xlrd
except ImportError:
    sys.exit("Install xlrd: pip install xlrd==1.2.0")

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "delay_dashboard.html"

# ─── 1. Master fleet (HAL + SKR) ─────────────────────────────────────────────
def read_company(fn: Path, owner_label: str) -> dict:
    """Return {code: vessel_info}."""
    wb = xlrd.open_workbook(str(fn))
    s = wb.sheets()[0]
    out = {}
    for r in range(1, s.nrows):
        row = [s.cell_value(r, c) for c in range(s.ncols)]
        code = str(row[3]).strip() if row[3] else ''
        # Skip junk rows (last row often has count/empty)
        if not code or len(code) > 8 or not re.match(r'^[A-Z0-9_-]+$', code):
            continue
        # Convert IMO from float to clean string
        imo = row[7]
        if isinstance(imo, float) and imo > 0:
            imo = str(int(imo))
        elif isinstance(imo, (int, str)):
            imo = str(imo).strip()
        else:
            imo = ''
        # Built year
        built = row[11]
        if isinstance(built, float) and built > 1900:
            built = str(int(built))
        else:
            built = str(built).strip() if built else ''
        out[code] = {
            'code': code,
            'name': str(row[4]).strip(),
            'type': str(row[5]).strip() or 'CNTR',
            'flag': str(row[8]).strip(),
            'built': built,
            'gt': int(row[16]) if isinstance(row[16], (int, float)) else 0,
            'dwt': int(row[20]) if isinstance(row[20], (int, float)) else 0,
            'teu': int(row[23]) if isinstance(row[23], (int, float)) else 0,
            'loa': float(row[25]) if isinstance(row[25], (int, float)) else 0.0,
            'imo': imo,
            'call': str(row[6]).strip(),
            'owner': owner_label,
            # T/C SVC from column 2 - primary service code, fallback if not in Schedule Code
            '_primary_svc': str(row[2]).strip(),
        }
    return out


print("[1] Reading HAL + SKR vessel master…")
hal = read_company(ROOT / 'Vessel Code_HAL_2026-04-02.xls', '사선')
skr = read_company(ROOT / 'Vessel Code_SKR_2026-04-02.xls', '사선')
master = {**hal, **skr}  # SKR overrides HAL if same code (unlikely but defensive)
print(f"  → HAL: {len(hal)} · SKR: {len(skr)} · combined: {len(master)} unique own vessels")

# ─── 2. Schedule Code → vessel-service assignments ───────────────────────────
print("[2] Reading Schedule Code assignments…")
wb = xlrd.open_workbook(str(ROOT / 'Schedule Code_2026-03-31.xls'))
s = wb.sheets()[0]
cols = {s.cell_value(0, c): c for c in range(s.ncols)}
vsl_idx = cols.get('VSL')
svc_idx = cols.get('SVC')
own_idx = cols.get('OWN')

# vessel → set of services they ran on
vessel_services: dict[str, set] = {}
for r in range(1, s.nrows):
    vsl = s.cell_value(r, vsl_idx)
    svc = s.cell_value(r, svc_idx)
    own = s.cell_value(r, own_idx)
    if not vsl or not svc:
        continue
    code = str(vsl).strip()
    svc = str(svc).strip()
    # Only consider OWN vessels (non-empty OWN) since this dict is for own fleet
    if not own:
        continue
    vessel_services.setdefault(code, set()).add(svc)

print(f"  → {len(vessel_services)} unique own vessels seen in Schedule, "
      f"avg {sum(len(s) for s in vessel_services.values())/max(1,len(vessel_services)):.1f} services/vessel")

# ─── 3. Build VESSELS dict ───────────────────────────────────────────────────
print("[3] Building VESSELS dictionary…")
# Pre-load existing VESSELS for two reasons:
#   1. Preserve service assignments not present in this month's Schedule Code
#      (e.g. KTS1's SWBT).
#   2. Preserve VESSELS entries whose code isn't in HAL/SKR master at all —
#      typically 용선/charter vessels documented manually in the dashboard.
text_pre = HTML.read_text(encoding='utf-8')
m_pre = re.search(r'var VESSELS = (\{.*?\});', text_pre)
existing_assignments: dict[str, set] = {}
existing_full: dict[str, dict] = {}  # code → full vessel object (for non-HAL/SKR codes)
if m_pre:
    for svc, vs in json.loads(m_pre.group(1)).items():
        for v in vs:
            code = v['code']
            existing_assignments.setdefault(code, set()).add(svc)
            # Keep the most-recent full record per code
            existing_full[code] = v

vessels_out: dict[str, list] = {}
unassigned = []

# Pass 1: master fleet (HAL + SKR) — definitive info
for code, info in master.items():
    services = set(vessel_services.get(code, set()))
    if info['_primary_svc']:
        services.add(info['_primary_svc'])
    services |= existing_assignments.get(code, set())
    if not services:
        unassigned.append(code)
        continue
    for svc in services:
        v = {k: v for k, v in info.items() if not k.startswith('_')}
        vessels_out.setdefault(svc, []).append(v)

# Pass 2: any code in old VESSELS but NOT in master (likely 용선/charter manually entered)
preserved_charter = []
for code, old_v in existing_full.items():
    if code in master:
        continue
    preserved_charter.append(code)
    for svc in existing_assignments.get(code, set()):
        # Keep the OLD entry verbatim (may have owner='용선' and other manual data)
        vessels_out.setdefault(svc, []).append(old_v)
print(f"  -> {len(preserved_charter)} non-master vessels preserved from existing VESSELS "
      f"(likely 용선): {preserved_charter[:10]}{'...' if len(preserved_charter)>10 else ''}")

# Sort vessels within each service by TEU desc (matches dashboard's display sort)
for svc in vessels_out:
    vessels_out[svc].sort(key=lambda v: -(v.get('teu') or 0))

# Sort services alphabetically for stable diff
vessels_out = dict(sorted(vessels_out.items()))

total_entries = sum(len(v) for v in vessels_out.values())
print(f"  → {len(vessels_out)} services, {total_entries} entries (vessel can repeat across services)")
print(f"  → {len(unassigned)} vessel(s) had no service assignment: {unassigned[:5]}{'…' if len(unassigned)>5 else ''}")

# ─── 4. Diff against current VESSELS ─────────────────────────────────────────
text = HTML.read_text(encoding='utf-8')
m = re.search(r'var VESSELS = (\{.*?\});', text)
if not m:
    sys.exit("VESSELS not found")
current = json.loads(m.group(1))

# Pull ROUTES list to find which routes had no vessels before
m2 = re.search(r'var ROUTES = (\{.*?\});', text)
routes = json.loads(m2.group(1))
before_empty = [svc for svc in routes if not current.get(svc)]
after_empty = [svc for svc in routes if not vessels_out.get(svc)]
print()
print(f"Routes with NO vessels - before: {len(before_empty)}, after: {len(after_empty)}")
if before_empty:
    fixed = sorted(set(before_empty) - set(after_empty))
    print(f"  Now filled: {fixed}")
if after_empty:
    print(f"  Still empty (no own vessel ever ran these): {after_empty}")

# ─── 5. Substitute back ──────────────────────────────────────────────────────
new_blob = json.dumps(vessels_out, ensure_ascii=False, separators=(',', ': '))
new_text, n = re.subn(r'var VESSELS = \{.*?\};', f'var VESSELS = {new_blob};', text, count=1, flags=re.DOTALL)
if n != 1:
    sys.exit("Substitution failed")
HTML.write_text(new_text, encoding='utf-8')
print()
print(f"  → VESSELS line updated in delay_dashboard.html")
