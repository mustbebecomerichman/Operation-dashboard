#!/usr/bin/env python3
"""
Auto-generate dense sea waypoints for every route in delay_dashboard.html
that doesn't already have a hand-tuned dense `coords[]` array (e.g. KST/SWRG
sample with 392 hand-placed points).

Strategy:
1. Parse ROUTES + WP + _RT tables from delay_dashboard.html.
2. For each route, for each consecutive port pair:
   - Use the regional routing table (_RT) to find sea waypoints between the
     two ports' regions.
   - Linear-interpolate ~30 great-circle points between each pair of
     consecutive waypoints (so curves look smooth, not jagged).
3. Emit `data/route-coords.json`: {svc: [{lat,lon,port?}, ...]}.
4. Skip routes whose existing coords array is already dense (more points than
   ports[] length) — preserves hand-tuned samples like KST.

Run after editing ROUTES or WP/_RT tables:
    python scripts/generate-route-coords.py

The dashboard loads `data/route-coords.json` at startup and uses its coords
in `showRoute()` whenever the embedded ROUTES[svc].coords is port-only.
"""
from __future__ import annotations
import json
import re
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "delay_dashboard.html"
OUT = ROOT / "data" / "route-coords.json"

# ─── Parse data from HTML ────────────────────────────────────────────────────
text = HTML.read_text(encoding="utf-8")


def extract_var(name: str) -> dict | list:
    """Pull `var NAME = {...};` or `var NAME = [...];` blob from HTML."""
    m = re.search(rf"var {re.escape(name)} = (\{{.*?\}}|\[.*?\]);", text)
    if not m:
        raise SystemExit(f"Could not find var {name} in HTML")
    return json.loads(m.group(1))


ROUTES = extract_var("ROUTES")
TERMINALS = extract_var("TERMINALS")

# WP is structured as JS object literal with arrays — parse manually.
WP: dict[str, tuple[float, float]] = {}
wp_block = re.search(r"var WP = \{([\s\S]*?)\n\};", text)
if not wp_block:
    raise SystemExit("Could not find WP table")
for line in wp_block.group(1).splitlines():
    m = re.match(r"\s*(\w+)\s*:\s*\[(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", line)
    if m:
        WP[m.group(1)] = (float(m.group(2)), float(m.group(3)))
print(f"Loaded WP table: {len(WP)} waypoints")

# Build port_code → (lat,lon) lookup from TERMINALS.
PORT_LATLON: dict[str, tuple[float, float]] = {}
for t in TERMINALS:
    pc = t.get("port_code")
    if pc and pc not in PORT_LATLON:
        PORT_LATLON[pc] = (t["lat"], t["lon"])
print(f"Port lat/lons: {len(PORT_LATLON)}")


# ─── Region classifier (mirrors pregion() in dashboard JS) ───────────────────
def pregion(la: float, lo: float) -> str:
    if la > 40 and 130 <= lo <= 142: return "russia"
    if la > 40 and 135 <= lo <= 145: return "russia"
    if la > 30 and lo > 130: return "japan"
    if 33 <= la <= 38 and 124 <= lo <= 132: return "korea"
    if la > 30 and 118 <= lo <= 126: return "china_n"
    if la > 28 and 115 <= lo < 126: return "china_n"
    if 21 <= la <= 26 and 119 <= lo <= 122.5: return "taiwan"
    if 20 <= la < 28 and 108 <= lo < 122: return "china_s"
    if 15 <= la < 22 and 105 <= lo < 110: return "vietnam_n"
    if 10 <= la < 15 and 107 <= lo < 110: return "vietnam_s"
    if 5 <= la < 15 and 99 <= lo < 105: return "thailand"
    if 0.5 <= la < 6 and 100 <= lo < 105: return "malaysia"
    if -8 <= la < 6 and 95 <= lo < 108: return "indonesia_w"
    if -10 <= la < 0 and 108 <= lo < 125: return "indonesia_e"
    if 5 <= la <= 20 and 118 <= lo <= 127: return "philippines"
    if 0 <= la < 22 and 105 <= lo < 120: return "scs"
    if 5 <= la <= 25 and 85 <= lo < 100: return "bay_bengal"
    if 8 <= la <= 22 and 78 <= lo < 90: return "india_e"
    if 8 <= la <= 23 and 68 <= lo < 78: return "india_w"
    if 5 <= la < 9 and 79 <= lo < 82: return "india_e"
    if lo < 72 and la < 30: return "mideast"
    if lo < 80 and 20 <= la < 30: return "mideast"
    if la > 15 and -100 <= lo <= -80: return "mexico"
    return "other"


# ─── Regional routing table (mirrors _RT) ────────────────────────────────────
# Keys are "from:to", values are lists of WP keys.
_RT_RAW = """
korea:japan ['korea_str']
korea:china_n ['yellow_sea']
korea:china_s ['ecs_s','taiwan_n']
korea:taiwan ['ecs_s']
korea:vietnam_n ['ecs_s','taiwan_s','scs_n','scs_w']
korea:vietnam_s ['ecs_s','taiwan_s','scs_c','scs_sw']
korea:thailand ['ecs_s','taiwan_s','scs_c','scs_sw','gulf_thai']
korea:malaysia ['ecs_s','taiwan_s','scs_c','sing']
korea:scs ['ecs_s','taiwan_s','scs_n']
korea:indonesia_w ['ecs_s','taiwan_s','scs_c','sing','malacca_s']
korea:indonesia_e ['ecs_s','taiwan_s','scs_c','scs_sw','java_e']
korea:philippines ['ecs_s','luzon']
korea:bay_bengal ['ecs_s','taiwan_s','scs_c','sing','malacca_n','bay_s']
korea:india_e ['ecs_s','taiwan_s','scs_c','sing','malacca_n','bay_s']
korea:india_w ['ecs_s','taiwan_s','scs_c','sing','malacca_n','indian']
korea:mideast ['ecs_s','taiwan_s','scs_c','sing','malacca_n','arabian_e','arabian_c']
korea:russia ['korea_str','russia_e']
korea:mexico ['ecs_s','luzon','pac_e']
japan:china_n ['korea_str','yellow_sea']
japan:china_s ['ecs_s','taiwan_n']
japan:taiwan ['ecs_s']
japan:vietnam_n ['ecs_s','taiwan_s','scs_n','scs_w']
japan:vietnam_s ['ecs_s','taiwan_s','scs_c','scs_sw']
japan:thailand ['ecs_s','taiwan_s','scs_c','scs_sw','gulf_thai']
japan:malaysia ['ecs_s','taiwan_s','scs_c','sing']
japan:scs ['ecs_s','taiwan_s','scs_n']
japan:indonesia_w ['ecs_s','taiwan_s','scs_c','sing','malacca_s']
japan:indonesia_e ['taiwan_s','scs_c','scs_sw','java_e']
japan:philippines ['luzon']
japan:bay_bengal ['ecs_s','taiwan_s','scs_c','sing','malacca_n','bay_s']
japan:india_e ['ecs_s','taiwan_s','scs_c','sing','malacca_n','bay_s']
japan:india_w ['ecs_s','taiwan_s','scs_c','sing','malacca_n','indian']
japan:mideast ['ecs_s','taiwan_s','scs_c','sing','malacca_n','arabian_e','arabian_c']
japan:russia ['korea_str','russia_e']
china_n:china_s ['ecs','taiwan_n']
china_n:taiwan ['ecs','ecs_s']
china_n:vietnam_n ['ecs','taiwan_s','scs_n','scs_w']
china_n:vietnam_s ['ecs','taiwan_s','scs_c','scs_sw']
china_n:thailand ['ecs','taiwan_s','scs_c','scs_sw','gulf_thai']
china_n:malaysia ['ecs','taiwan_s','scs_c','sing']
china_n:indonesia_w ['ecs','taiwan_s','scs_c','sing','malacca_s']
china_n:indonesia_e ['ecs','taiwan_s','scs_c','scs_sw','java_e']
china_n:philippines ['ecs','luzon']
china_n:bay_bengal ['ecs','taiwan_s','scs_c','sing','malacca_n','bay_s']
china_n:india_e ['ecs','taiwan_s','scs_c','sing','malacca_n','bay_s']
china_n:india_w ['ecs','taiwan_s','scs_c','sing','malacca_n','indian']
china_n:mideast ['ecs','taiwan_s','scs_c','sing','malacca_n','arabian_e','arabian_c']
china_s:vietnam_n ['scs_n','scs_w']
china_s:vietnam_s ['scs_c','scs_sw']
china_s:thailand ['scs_c','scs_sw','gulf_thai']
china_s:malaysia ['scs_c','sing']
china_s:indonesia_w ['scs_c','sing','malacca_s']
china_s:indonesia_e ['scs_c','scs_sw','java_e']
china_s:philippines ['luzon']
china_s:bay_bengal ['scs_c','sing','malacca_n','bay_s']
china_s:india_e ['scs_c','sing','malacca_n','bay_s']
china_s:india_w ['scs_c','sing','malacca_n','indian']
china_s:mideast ['scs_c','sing','malacca_n','arabian_e','arabian_c']
taiwan:vietnam_n ['scs_n','scs_w']
taiwan:vietnam_s ['scs_c','scs_sw']
taiwan:thailand ['scs_c','scs_sw','gulf_thai']
taiwan:malaysia ['scs_c','sing']
taiwan:indonesia_w ['scs_c','sing','malacca_s']
taiwan:indonesia_e ['scs_c','scs_sw','java_e']
taiwan:philippines ['luzon']
vietnam_n:vietnam_s ['scs_w','scs_sw']
vietnam_n:thailand ['scs_w','scs_sw','gulf_thai']
vietnam_n:malaysia ['scs_sw','sing']
vietnam_n:indonesia_w ['scs_sw','sing','malacca_s']
vietnam_s:thailand ['scs_sw','gulf_thai']
vietnam_s:malaysia ['sing']
vietnam_s:indonesia_w ['sing','malacca_s']
vietnam_s:indonesia_e ['java_e']
thailand:malaysia ['gulf_thai','sing']
thailand:indonesia_w ['gulf_thai','sing','malacca_s']
malaysia:indonesia_w ['malacca_s']
malaysia:indonesia_e ['sing','java_e']
malaysia:bay_bengal ['malacca_n','bay_s']
malaysia:india_e ['malacca_n','bay_s']
malaysia:india_w ['malacca_n','indian']
malaysia:mideast ['malacca_n','arabian_e','arabian_c']
indonesia_w:indonesia_e ['java_w','java_e']
indonesia_w:bay_bengal ['malacca_s','malacca_n','bay_s']
indonesia_e:philippines ['java_e','scs_c','luzon']
bay_bengal:india_e []
bay_bengal:india_w ['indian']
india_e:india_w ['indian']
india_w:mideast ['arabian_e','arabian_c']
"""

_RT: dict[str, list[str]] = {}
for line in _RT_RAW.strip().splitlines():
    key, wps = line.split(" ", 1)
    wps_list = json.loads(wps.replace("'", '"'))
    _RT[key] = wps_list
    # Reverse direction
    fr, to = key.split(":")
    _RT[f"{to}:{fr}"] = list(reversed(wps_list))
print(f"Loaded _RT table: {len(_RT)} region pairs")


# ─── Sea routing (mirrors seaRoute() in dashboard JS) ────────────────────────
def sea_route(a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    """Return path [a, wp1, wp2, ..., b] following sea waypoints between regions."""
    fr = pregion(a[0], a[1])
    to = pregion(b[0], b[1])
    if fr == to:
        if fr in ("indonesia_w", "indonesia_e"):
            return [a, WP["java_w"], b]
        return [a, b]
    key = f"{fr}:{to}"
    wps_keys = _RT.get(key)
    if wps_keys is None:
        # Generic fallback through Singapore
        near_sing = {"scs","vietnam_s","malaysia","indonesia_w","indonesia_e","thailand","bay_bengal","india_e","india_w","mideast"}
        east = {"korea","japan","china_n","china_s","taiwan","vietnam_n","vietnam_s","philippines"}
        if fr in east and to in near_sing:
            wps_keys = ["scs_c", "sing", "malacca_n"]
        elif fr in near_sing and to in east:
            wps_keys = ["malacca_n", "sing", "scs_c"]
        else:
            wps_keys = ["scs_c", "sing"]
    pts = [a]
    for k in wps_keys:
        if k in WP:
            pts.append(WP[k])
    pts.append(b)
    return pts


# ─── Great-circle interpolation between two lat/lon points ──────────────────
def great_circle_interp(a: tuple[float, float], b: tuple[float, float], n: int) -> list[tuple[float, float]]:
    """Return n intermediate points (exclusive of endpoints) along a great circle."""
    if n <= 0:
        return []
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = math.sin(d_lat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(d_lon/2)**2
    d = 2 * math.asin(math.sqrt(min(1.0, h)))
    if d == 0:
        return []
    out = []
    for i in range(1, n + 1):
        f = i / (n + 1)
        A = math.sin((1-f)*d) / math.sin(d)
        B = math.sin(f*d) / math.sin(d)
        x = A*math.cos(lat1)*math.cos(lon1) + B*math.cos(lat2)*math.cos(lon2)
        y = A*math.cos(lat1)*math.sin(lon1) + B*math.cos(lat2)*math.sin(lon2)
        z = A*math.sin(lat1) + B*math.sin(lat2)
        lat = math.degrees(math.atan2(z, math.sqrt(x*x + y*y)))
        lon = math.degrees(math.atan2(y, x))
        out.append((lat, lon))
    return out


# Points between consecutive waypoints. ~30 gives a smooth curve without bloat.
INTERP_BETWEEN_WPS = 30


def dense_path(ports: list[str]) -> list[dict]:
    """Build dense sea waypoint list for a sequence of port codes."""
    if len(ports) < 2:
        return [{"port": pc, **dict(zip(("lat","lon"), PORT_LATLON[pc]))} for pc in ports if pc in PORT_LATLON]
    out: list[dict] = []
    # Add the first port
    first_pc = ports[0]
    if first_pc not in PORT_LATLON:
        return []
    out.append({"port": first_pc, "lat": PORT_LATLON[first_pc][0], "lon": PORT_LATLON[first_pc][1]})
    for i in range(1, len(ports)):
        pc_prev, pc_curr = ports[i-1], ports[i]
        if pc_prev not in PORT_LATLON or pc_curr not in PORT_LATLON:
            continue
        a = PORT_LATLON[pc_prev]
        b = PORT_LATLON[pc_curr]
        wps = sea_route(a, b)
        # Interpolate between each consecutive waypoint pair
        for j in range(len(wps) - 1):
            interp = great_circle_interp(wps[j], wps[j+1], INTERP_BETWEEN_WPS)
            for pt in interp:
                out.append({"lat": round(pt[0], 5), "lon": round(pt[1], 5)})
            # Add the destination of this leg (which is wps[j+1]); but skip if
            # it equals the next port (we'll add ports below as labeled points).
            nxt = wps[j+1]
            is_last_in_segment = (j == len(wps) - 2)
            if is_last_in_segment:
                # Last point of this segment IS the next port — add it labeled.
                out.append({"port": pc_curr, "lat": PORT_LATLON[pc_curr][0], "lon": PORT_LATLON[pc_curr][1]})
            else:
                # Intermediate WP — add unlabeled.
                out.append({"lat": round(nxt[0], 5), "lon": round(nxt[1], 5)})
    return out


# ─── Main ───────────────────────────────────────────────────────────────────
result: dict[str, list[dict]] = {}
skipped_hand_tuned = []
skipped_no_ports = []

for svc, route in ROUTES.items():
    ports = route.get("ports") or []
    existing_coords = route.get("coords") or []
    # Skip if hand-tuned (coords longer than ports = user already added dense path)
    if len(existing_coords) > len(ports):
        skipped_hand_tuned.append(svc)
        continue
    if len(ports) < 2:
        skipped_no_ports.append(svc)
        continue
    dense = dense_path(ports)
    if dense:
        result[svc] = dense

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

print()
print(f"Wrote {OUT.relative_to(ROOT)}")
print(f"  Generated: {len(result)} routes")
print(f"  Skipped (hand-tuned, e.g. KST): {len(skipped_hand_tuned)} → {skipped_hand_tuned[:5]}{'…' if len(skipped_hand_tuned)>5 else ''}")
print(f"  Skipped (<2 ports): {len(skipped_no_ports)} → {skipped_no_ports[:5]}")
print(f"  File size: {OUT.stat().st_size//1024} KB")
total_pts = sum(len(v) for v in result.values())
print(f"  Total waypoints: {total_pts:,}")
