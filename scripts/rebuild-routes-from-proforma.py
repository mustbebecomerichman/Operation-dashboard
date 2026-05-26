#!/usr/bin/env python3
"""
Authoritative route rebuild:
  1. Read port rotations from Proforma data_2026-03-31.xlsx (SVR_CD + SEQ + FR_PORT).
  2. Overwrite ROUTES[svc].ports[] in delay_dashboard.html for every existing
     route, preserving name/kind/region/manager/backup metadata.
  3. Recompute dense waypoints for each route using the searoute marnet
     (4109-segment global maritime network) via Dijkstra A*.
  4. Emit data/route-coords.json so the dashboard renders precise sea paths.

Hand-tuned routes (existing coords.length > ports.length, e.g. KST/SWRG) are
preserved as-is — author intent wins.

Run after each Proforma drop or ROUTES metadata edit:
    python scripts/rebuild-routes-from-proforma.py

Dependencies: openpyxl
"""
from __future__ import annotations
import json
import math
import re
import sys
import heapq
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("Install openpyxl: pip install openpyxl")

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "delay_dashboard.html"
PROFORMA = ROOT / "Proforma data_2026-03-31.xlsx"
MARNET = ROOT / "data" / "marnet" / "marnet.geojson"
OUT_COORDS = ROOT / "data" / "route-coords.json"

# ─── 1. Read Proforma → service rotations ────────────────────────────────────
print("[1/5] Reading Proforma port rotations…")
wb = openpyxl.load_workbook(PROFORMA, data_only=True)

def extract_rotations(ws):
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    idx = {h: i for i, h in enumerate(headers)}
    rot = {}
    for ri in range(2, ws.max_row + 1):
        row = [ws.cell(ri, c).value for c in range(1, ws.max_column + 1)]
        svc = row[idx['SVR_CD']]
        seq = row[idx['SEQ']]
        fr = row[idx['FR_PORT']]
        to = row[idx['TO_PORT']]
        if not svc or not fr:
            continue
        rot.setdefault(str(svc), []).append((str(seq) if seq else '', str(fr), str(to)))
    return rot

# Sheet 1 = 자선 (own), Sheet 2 = 슬롯 (slot). Prefer own, fall back to slot.
sheet_own = wb[wb.sheetnames[0]]
sheet_slot = wb[wb.sheetnames[1]]
own_rot = extract_rotations(sheet_own)
slot_rot = extract_rotations(sheet_slot)

def legs_to_ports(legs):
    """Convert FR→TO legs (sorted by SEQ) to ordered port list, truncated to
    ONE rotation cycle. Proforma often lists 2–3 voyages (PQS: PTK→TAO→PTK→TAO→PTK);
    we keep only the first cycle (PTK→TAO→PTK) so the displayed rotation
    represents one round trip."""
    try:
        legs = sorted(legs, key=lambda x: int(x[0]))
    except (ValueError, TypeError):
        pass
    ports = []
    for _, fr, to in legs:
        if fr and (not ports or ports[-1] != fr):
            ports.append(fr)
    if legs:
        last_to = legs[-1][2]
        if last_to and (not ports or ports[-1] != last_to):
            ports.append(last_to)
    # Truncate at first reoccurrence of ports[0] — that defines one cycle.
    # If ports[0] doesn't recur, return as-is (e.g. one-way feeders).
    if len(ports) >= 2:
        first = ports[0]
        for i in range(1, len(ports)):
            if ports[i] == first:
                return ports[: i + 1]
    return ports

proforma_ports = {}
for svc in set(list(own_rot.keys()) + list(slot_rot.keys())):
    legs = own_rot.get(svc) or slot_rot.get(svc) or []
    ports = legs_to_ports(legs)
    if ports:
        proforma_ports[svc] = ports
print(f"  → {len(proforma_ports)} services with port rotations from Proforma")

# ─── 2. Read current ROUTES + TERMINALS ──────────────────────────────────────
print("[2/5] Reading current ROUTES + TERMINALS from delay_dashboard.html…")
text = HTML.read_text(encoding="utf-8")

def extract_var(name):
    m = re.search(rf"var {re.escape(name)} = (\{{.*?\}}|\[.*?\]);", text)
    if not m:
        sys.exit(f"Could not find var {name}")
    return json.loads(m.group(1))

ROUTES = extract_var("ROUTES")
TERMINALS = extract_var("TERMINALS")

# Port lookup
PORT_LATLON = {}
for t in TERMINALS:
    pc = t.get("port_code")
    if pc and pc not in PORT_LATLON:
        PORT_LATLON[pc] = (t["lat"], t["lon"])
print(f"  → {len(ROUTES)} routes, {len(PORT_LATLON)} port coords")

# ─── 3. Update ROUTES.ports[] from Proforma ──────────────────────────────────
print("[3/5] Updating ROUTES.ports[] from Proforma…")
fixed = 0
preserved_hand = []
unknown_ports_per_svc = {}
for svc, route in ROUTES.items():
    if svc not in proforma_ports:
        continue
    new_ports = proforma_ports[svc]
    # Keep ALL ports in rotation (incl. those with no lat/lon — visible in the
    # port rotation list, just skipped when drawing waypoints). Previously we
    # filtered to known-only which silently dropped e.g. AEJEA from SGX1.
    unknown = [p for p in new_ports if p not in PORT_LATLON]
    if unknown:
        unknown_ports_per_svc[svc] = unknown
    if route.get("ports") != new_ports:
        route["ports"] = new_ports
        fixed += 1
    # Dense waypoints belong in data/route-coords.json (separate file) — never
    # write them into ROUTES.coords here, otherwise re-running this script
    # mistakes its own previous output for hand-tuned data. ROUTES.coords[]
    # stays port-only OR hand-tuned (e.g. KST/SWRG's 392 pts that pre-exist
    # in the HTML and are length-mismatched with ports).
    existing_coords = route.get("coords") or []
    port_len = len(new_ports)
    looks_port_only = (len(existing_coords) == port_len)
    if looks_port_only or not existing_coords:
        # Refresh port-only coords to match the (possibly new) ports order.
        route["coords"] = [
            {"port": p, "lat": PORT_LATLON[p][0], "lon": PORT_LATLON[p][1]}
            for p in new_ports if p in PORT_LATLON
        ]
print(f"  -> {fixed} routes had ports[] updated")
if unknown_ports_per_svc:
    total_unknown = sum(len(v) for v in unknown_ports_per_svc.values())
    print(f"  -> {len(unknown_ports_per_svc)} routes have {total_unknown} unknown port(s) - kept in ports[], skipped during waypoint draw")
    for s, u in list(unknown_ports_per_svc.items())[:5]:
        print(f"     {s}: missing {u}")

# ─── 4. Load marnet sea graph + build Dijkstra index ─────────────────────────
print("[4/5] Loading marnet sea network for accurate routing…")
with MARNET.open(encoding="utf-8") as f:
    marnet = json.load(f)

def hav(p1, p2):
    """Haversine distance in km. p = (lon, lat)."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, a)))

# Build undirected graph: node = (round(lon,3), round(lat,3))
def node_key(lon, lat):
    return (round(lon, 3), round(lat, 3))

graph = {}      # node → list of (neighbor, dist_km)
node_pos = {}   # node → (lon, lat)  (canonical position for output)

for feat in marnet["features"]:
    if feat["geometry"]["type"] != "LineString":
        continue
    coords = feat["geometry"]["coordinates"]
    if len(coords) < 2:
        continue
    for i in range(len(coords) - 1):
        c1, c2 = coords[i], coords[i+1]
        n1 = node_key(c1[0], c1[1])
        n2 = node_key(c2[0], c2[1])
        if n1 == n2:
            continue
        node_pos.setdefault(n1, (c1[0], c1[1]))
        node_pos.setdefault(n2, (c2[0], c2[1]))
        d = hav(c1, c2)
        graph.setdefault(n1, []).append((n2, d))
        graph.setdefault(n2, []).append((n1, d))

print(f"  → graph: {len(graph)} nodes, {sum(len(e) for e in graph.values())//2} edges")

# Spatial index — bucket nodes by 1°×1° cell for fast nearest-node lookup
buckets = {}
for n, (lon, lat) in node_pos.items():
    buckets.setdefault((int(lon), int(lat)), []).append(n)

def nearest_node(lat, lon):
    """Find graph node closest to a port lat/lon. Searches a 3×3 cell area
    first; widens if nothing found (e.g. very remote ports)."""
    best, best_d = None, float('inf')
    radius = 1
    while best is None and radius <= 8:
        for di in range(-radius, radius+1):
            for dj in range(-radius, radius+1):
                cell = (int(lon)+di, int(lat)+dj)
                for n in buckets.get(cell, []):
                    p = node_pos[n]
                    d = hav((lon, lat), p)
                    if d < best_d:
                        best_d = d
                        best = n
        radius += 1
    return best, best_d

# Dijkstra (heap-based) between two nodes
def dijkstra(start, end):
    if start == end:
        return [start], 0.0
    dist = {start: 0.0}
    prev = {}
    pq = [(0.0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == end:
            break
        if d > dist.get(u, float('inf')):
            continue
        for v, w in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if end not in dist:
        return None, None
    # Reconstruct path
    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[end]

# ─── 5. Compute dense coords per route using marnet ──────────────────────────
print("[5/5] Computing dense sea waypoints via Dijkstra…")
route_coords = {}
preserved = []
failed = []

for svc, route in ROUTES.items():
    # Preserve hand-tuned dense paths
    existing_coords = route.get("coords") or []
    ports = route.get("ports") or []
    if existing_coords and len(existing_coords) > len(ports):
        preserved.append(svc)
        continue
    # Use only the subset of ports with known lat/lon for waypoint generation,
    # but preserve the full ports[] list on the route (set above).
    ports_known = [p for p in ports if p in PORT_LATLON]
    if len(ports_known) < 2:
        continue
    dense = []
    first_pc = ports_known[0]
    first_lat, first_lon = PORT_LATLON[first_pc]
    dense.append({"port": first_pc, "lat": first_lat, "lon": first_lon})

    leg_failed = False
    for i in range(1, len(ports_known)):
        pc_prev = ports_known[i-1]
        pc_curr = ports_known[i]
        a_lat, a_lon = PORT_LATLON[pc_prev]
        b_lat, b_lon = PORT_LATLON[pc_curr]
        n_a, _ = nearest_node(a_lat, a_lon)
        n_b, _ = nearest_node(b_lat, b_lon)
        if not n_a or not n_b:
            leg_failed = True
            # Fallback: straight segment
            dense.append({"port": pc_curr, "lat": b_lat, "lon": b_lon})
            continue
        path, _ = dijkstra(n_a, n_b)
        if not path:
            leg_failed = True
            dense.append({"port": pc_curr, "lat": b_lat, "lon": b_lon})
            continue
        # Add intermediate waypoints (skip the start node since dense already
        # has the previous port; skip the end node since we'll add the port)
        for n in path[1:-1]:
            lon, lat = node_pos[n]
            dense.append({"lat": round(lat, 5), "lon": round(lon, 5)})
        dense.append({"port": pc_curr, "lat": b_lat, "lon": b_lon})

    if leg_failed:
        failed.append(svc)
    route_coords[svc] = dense

print(f"  → generated {len(route_coords)} routes, {len(preserved)} hand-tuned preserved, {len(failed)} partial fallbacks: {failed[:5]}{'…' if len(failed)>5 else ''}")

# ─── 6. Write outputs ────────────────────────────────────────────────────────
OUT_COORDS.parent.mkdir(exist_ok=True)
OUT_COORDS.write_text(json.dumps(route_coords, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
total_pts = sum(len(v) for v in route_coords.values())
print(f"  → Wrote {OUT_COORDS.relative_to(ROOT)}: {OUT_COORDS.stat().st_size//1024} KB · {total_pts:,} waypoints")

# Update ROUTES in delay_dashboard.html ----------------------------------------
# Find the ROUTES = {...}; line and replace
print()
print("Updating ROUTES line in delay_dashboard.html…")
routes_blob = json.dumps(ROUTES, ensure_ascii=False, separators=(',', ': '))
# Match the existing var ROUTES = {...};  line
new_text, n = re.subn(
    r"var ROUTES = \{.*?\};",
    f"var ROUTES = {routes_blob};",
    text,
    count=1,
    flags=re.DOTALL,
)
if n != 1:
    sys.exit("Failed to substitute ROUTES line")
HTML.write_text(new_text, encoding="utf-8")
print(f"  → ROUTES line updated, file size now {HTML.stat().st_size//1024} KB")
