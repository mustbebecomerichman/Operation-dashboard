#!/usr/bin/env python3
"""Append missing port entries to TERMINALS in delay_dashboard.html.

These ports appear in Proforma rotations but were absent from TERMINALS,
which meant they were silently skipped during waypoint drawing.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "delay_dashboard.html"

# Coordinates from public sources (Google Maps / port authorities).
MISSING = [
    {"depot": "LCH01", "port_code": "THLCH", "port_name": "LAEM CHABANG, THAILAND",      "country": "TH", "lat": 13.0827, "lon": 100.8830, "hist_delay": 0},
    {"depot": "JEA01", "port_code": "AEJEA", "port_name": "JEBEL ALI, UAE",              "country": "AE", "lat": 24.9858, "lon":  55.0271, "hist_delay": 0},
    {"depot": "HUA01", "port_code": "CNHUA", "port_name": "HUANGPU, CHINA",              "country": "CN", "lat": 23.0832, "lon": 113.4400, "hist_delay": 0},
    {"depot": "NTG01", "port_code": "CNNTG", "port_name": "NANTONG, CHINA",              "country": "CN", "lat": 32.0162, "lon": 120.8651, "hist_delay": 0},
    {"depot": "SWA01", "port_code": "CNSWA", "port_name": "SHANTOU, CHINA",              "country": "CN", "lat": 23.3506, "lon": 116.7567, "hist_delay": 0},
    {"depot": "YNT01", "port_code": "CNYNT", "port_name": "YANTAI, CHINA",               "country": "CN", "lat": 37.4621, "lon": 121.4400, "hist_delay": 0},
    {"depot": "ZPU01", "port_code": "CNZPU", "port_name": "ZHAPU, CHINA",                "country": "CN", "lat": 30.6356, "lon": 121.0894, "hist_delay": 0},
    {"depot": "MAA01", "port_code": "INMAA", "port_name": "CHENNAI, INDIA",              "country": "IN", "lat": 13.0907, "lon":  80.2945, "hist_delay": 0},
    {"depot": "PIP01", "port_code": "INPIP", "port_name": "PIPAVAV, INDIA",              "country": "IN", "lat": 20.9292, "lon":  71.5236, "hist_delay": 0},
    {"depot": "VTZ01", "port_code": "INVTZ", "port_name": "VISAKHAPATNAM, INDIA",        "country": "IN", "lat": 17.6868, "lon":  83.2185, "hist_delay": 0},
    {"depot": "HMD01", "port_code": "JPHMD", "port_name": "HAMADA, JAPAN",               "country": "JP", "lat": 34.8923, "lon": 132.0824, "hist_delay": 0},
    {"depot": "ISS01", "port_code": "JPISS", "port_name": "ISHINOMAKI, JAPAN",           "country": "JP", "lat": 38.4310, "lon": 141.3060, "hist_delay": 0},
    {"depot": "TKS01", "port_code": "JPTKS", "port_name": "TOKUSHIMA, JAPAN",            "country": "JP", "lat": 34.0707, "lon": 134.5750, "hist_delay": 0},
    {"depot": "TOS01", "port_code": "JPTOS", "port_name": "TOYAMA-SHINKO, JAPAN",        "country": "JP", "lat": 36.7800, "lon": 137.1100, "hist_delay": 0},
    {"depot": "VST01", "port_code": "RUVST", "port_name": "VOSTOCHNY, RUSSIA",           "country": "RU", "lat": 42.7340, "lon": 132.9220, "hist_delay": 0},
]

text = HTML.read_text(encoding="utf-8")
m = re.search(r"var TERMINALS = (\[.*?\]);", text)
if not m:
    raise SystemExit("TERMINALS not found")
terms = json.loads(m.group(1))
existing_codes = {t.get("port_code") for t in terms}
existing_depots = {t.get("depot") for t in terms}
added = 0
for new in MISSING:
    if new["port_code"] in existing_codes:
        continue
    # Avoid depot code collision
    if new["depot"] in existing_depots:
        new["depot"] = new["port_code"][2:] + "_X"
    terms.append(new)
    added += 1
    existing_codes.add(new["port_code"])
    existing_depots.add(new["depot"])

new_blob = json.dumps(terms, ensure_ascii=False, separators=(",", ": "))
new_text, n = re.subn(r"var TERMINALS = \[.*?\];", f"var TERMINALS = {new_blob};", text, count=1, flags=re.DOTALL)
if n != 1:
    raise SystemExit("Substitution failed")
HTML.write_text(new_text, encoding="utf-8")
print(f"Added {added} missing terminals -> TERMINALS now has {len(terms)} entries.")
