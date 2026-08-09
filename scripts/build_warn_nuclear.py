"""
WARN Nuclear Incident Proximity Engine
Data sources:
  - NRC Power Reactor Status Report (daily, public) — current power output
  - NRC/IAEA plant location table (public record, precompiled from NRC FOIA data)
  - NRC Emergency Planning Zone: 10-mile radius (Plume EPZ), 50-mile (Ingestion EPZ)

WARN_nuclear scores baseline proximity risk per plant:
  0.45 × capacity_norm        — reactor net capacity relative to largest US unit
  0.35 × epz_population_norm  — population exposure within 10-mile EPZ (city-centroid proxy)
  0.20 × power_output_norm    — current power level (100% = at-power, 0% = shutdown)

Hashing: BLAKE3 only
"""
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import blake3
    def b3(data): return blake3.blake3(data).hexdigest()
except ImportError:
    import hashlib
    def b3(data): return "blake3-unavailable:" + hashlib.sha256(data).hexdigest()

OUT_DIR = Path(__file__).parent.parent / "outputs" / "disaster_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NRC_STATUS_URL = (
    "https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/"
    "powerreactorstatusforlast365days.txt"
)

# ── NRC plant location table ──────────────────────────────────────────────────
# Source: NRC "List of Power Reactor Units" public record + IAEA PRIS coordinates
# All US operating commercial reactors as of 2024.
# Capacity (MWe net) from NRC/EIA; coordinates from NRC facility addresses.
# EPZ_pop: approximate population within 10-mile radius using county centroid proximity.

PLANT_DATA = {
    # name (as in NRC status report, unit stripped) → {lat, lon, capacity_mwe, state, epz_pop_est}
    "Arkansas Nuclear":    {"lat": 35.31, "lon": -93.23, "cap_mwe": 836,  "state": "AR", "epz_pop": 8400},
    "Beaver Valley":       {"lat": 40.62, "lon": -80.43, "cap_mwe": 892,  "state": "PA", "epz_pop": 87000},
    "Braidwood":           {"lat": 41.24, "lon": -88.23, "cap_mwe": 1178, "state": "IL", "epz_pop": 18000},
    "Browns Ferry":        {"lat": 34.70, "lon": -87.12, "cap_mwe": 1065, "state": "AL", "epz_pop": 11000},
    "Brunswick":           {"lat": 33.96, "lon": -78.02, "cap_mwe": 938,  "state": "NC", "epz_pop": 16000},
    "Byron":               {"lat": 42.08, "lon": -89.28, "cap_mwe": 1164, "state": "IL", "epz_pop": 22000},
    "Callaway":            {"lat": 38.77, "lon": -91.78, "cap_mwe": 1236, "state": "MO", "epz_pop": 9000},
    "Calvert Cliffs":      {"lat": 38.43, "lon": -76.44, "cap_mwe": 873,  "state": "MD", "epz_pop": 14000},
    "Catawba":             {"lat": 35.06, "lon": -81.07, "cap_mwe": 1129, "state": "SC", "epz_pop": 88000},
    "Clinton":             {"lat": 40.15, "lon": -88.84, "cap_mwe": 1065, "state": "IL", "epz_pop": 34000},
    "Columbia":            {"lat": 46.47, "lon": -119.32,"cap_mwe": 1131, "state": "WA", "epz_pop": 7000},
    "Comanche Peak":       {"lat": 32.30, "lon": -97.79, "cap_mwe": 1200, "state": "TX", "epz_pop": 19000},
    "Cook":                {"lat": 41.97, "lon": -86.57, "cap_mwe": 1030, "state": "MI", "epz_pop": 24000},
    "Cooper":              {"lat": 40.36, "lon": -95.64, "cap_mwe": 769,  "state": "NE", "epz_pop": 5000},
    "Davis-Besse":         {"lat": 41.60, "lon": -83.09, "cap_mwe": 894,  "state": "OH", "epz_pop": 21000},
    "Diablo Canyon":       {"lat": 35.21, "lon": -120.85,"cap_mwe": 1118, "state": "CA", "epz_pop": 9000},
    "Dresden":             {"lat": 41.39, "lon": -88.27, "cap_mwe": 867,  "state": "IL", "epz_pop": 41000},
    "Duane Arnold":        {"lat": 42.10, "lon": -91.78, "cap_mwe": 601,  "state": "IA", "epz_pop": 48000},
    "Farley":              {"lat": 31.22, "lon": -85.11, "cap_mwe": 851,  "state": "AL", "epz_pop": 11000},
    "Fermi":               {"lat": 41.96, "lon": -83.26, "cap_mwe": 1122, "state": "MI", "epz_pop": 136000},
    "Fitzpatrick":         {"lat": 43.52, "lon": -76.40, "cap_mwe": 852,  "state": "NY", "epz_pop": 18000},
    "Fort Calhoun":        {"lat": 41.52, "lon": -96.08, "cap_mwe": 478,  "state": "NE", "epz_pop": 41000},
    "Ginna":               {"lat": 43.28, "lon": -77.31, "cap_mwe": 498,  "state": "NY", "epz_pop": 38000},
    "Grand Gulf":          {"lat": 32.01, "lon": -90.96, "cap_mwe": 1297, "state": "MS", "epz_pop": 9000},
    "Hatch":               {"lat": 31.93, "lon": -82.35, "cap_mwe": 876,  "state": "GA", "epz_pop": 8000},
    "Hope Creek":          {"lat": 39.47, "lon": -75.54, "cap_mwe": 1172, "state": "NJ", "epz_pop": 30000},
    "Indian Point":        {"lat": 41.27, "lon": -73.95, "cap_mwe": 1041, "state": "NY", "epz_pop": 310000},
    "Joseph M. Farley":    {"lat": 31.22, "lon": -85.11, "cap_mwe": 851,  "state": "AL", "epz_pop": 11000},
    "Kewaunee":            {"lat": 44.34, "lon": -87.54, "cap_mwe": 556,  "state": "WI", "epz_pop": 14000},
    "LaSalle":             {"lat": 41.24, "lon": -88.67, "cap_mwe": 1137, "state": "IL", "epz_pop": 10000},
    "Limerick":            {"lat": 40.22, "lon": -75.59, "cap_mwe": 1134, "state": "PA", "epz_pop": 178000},
    "McGuire":             {"lat": 35.43, "lon": -80.95, "cap_mwe": 1100, "state": "NC", "epz_pop": 97000},
    "Millstone":           {"lat": 41.31, "lon": -72.17, "cap_mwe": 1227, "state": "CT", "epz_pop": 46000},
    "Monticello":          {"lat": 45.33, "lon": -93.85, "cap_mwe": 671,  "state": "MN", "epz_pop": 40000},
    "Nine Mile Point":     {"lat": 43.52, "lon": -76.41, "cap_mwe": 1299, "state": "NY", "epz_pop": 18000},
    "North Anna":          {"lat": 38.07, "lon": -77.79, "cap_mwe": 942,  "state": "VA", "epz_pop": 15000},
    "Oconee":              {"lat": 34.79, "lon": -82.90, "cap_mwe": 846,  "state": "SC", "epz_pop": 26000},
    "Oyster Creek":        {"lat": 39.81, "lon": -74.21, "cap_mwe": 619,  "state": "NJ", "epz_pop": 31000},
    "Palisades":           {"lat": 42.32, "lon": -86.31, "cap_mwe": 805,  "state": "MI", "epz_pop": 18000},
    "Palo Verde":          {"lat": 33.39, "lon": -112.86,"cap_mwe": 1270, "state": "AZ", "epz_pop": 1500},
    "Peach Bottom":        {"lat": 39.76, "lon": -76.27, "cap_mwe": 1112, "state": "PA", "epz_pop": 112000},
    "Perry":               {"lat": 41.80, "lon": -81.15, "cap_mwe": 1261, "state": "OH", "epz_pop": 31000},
    "Pilgrim":             {"lat": 41.94, "lon": -70.58, "cap_mwe": 677,  "state": "MA", "epz_pop": 24000},
    "Point Beach":         {"lat": 44.28, "lon": -87.54, "cap_mwe": 512,  "state": "WI", "epz_pop": 14000},
    "Prairie Island":      {"lat": 44.62, "lon": -92.63, "cap_mwe": 520,  "state": "MN", "epz_pop": 14000},
    "Quad Cities":         {"lat": 41.73, "lon": -90.33, "cap_mwe": 908,  "state": "IL", "epz_pop": 129000},
    "Rancho Seco":         {"lat": 38.35, "lon": -121.12,"cap_mwe": 913,  "state": "CA", "epz_pop": 46000},
    "River Bend":          {"lat": 30.76, "lon": -91.33, "cap_mwe": 967,  "state": "LA", "epz_pop": 21000},
    "Robinson":            {"lat": 34.40, "lon": -80.16, "cap_mwe": 710,  "state": "SC", "epz_pop": 20000},
    "Salem":               {"lat": 39.47, "lon": -75.54, "cap_mwe": 1174, "state": "NJ", "epz_pop": 30000},
    "San Onofre":          {"lat": 33.37, "lon": -117.56,"cap_mwe": 1127, "state": "CA", "epz_pop": 104000},
    "Seabrook":            {"lat": 42.90, "lon": -70.85, "cap_mwe": 1246, "state": "NH", "epz_pop": 101000},
    "Sequoyah":            {"lat": 35.23, "lon": -85.09, "cap_mwe": 1148, "state": "TN", "epz_pop": 22000},
    "Shearon Harris":      {"lat": 35.63, "lon": -79.10, "cap_mwe": 900,  "state": "NC", "epz_pop": 36000},
    "South Texas":         {"lat": 28.79, "lon": -96.05, "cap_mwe": 1280, "state": "TX", "epz_pop": 3500},
    "St. Lucie":           {"lat": 27.35, "lon": -80.25, "cap_mwe": 839,  "state": "FL", "epz_pop": 53000},
    "Summer":              {"lat": 34.30, "lon": -81.32, "cap_mwe": 966,  "state": "SC", "epz_pop": 14000},
    "Surry":               {"lat": 37.17, "lon": -76.70, "cap_mwe": 799,  "state": "VA", "epz_pop": 44000},
    "Susquehanna":         {"lat": 41.10, "lon": -76.15, "cap_mwe": 1257, "state": "PA", "epz_pop": 43000},
    "Three Mile Island":   {"lat": 40.15, "lon": -76.73, "cap_mwe": 906,  "state": "PA", "epz_pop": 89000},
    "Turkey Point":        {"lat": 25.43, "lon": -80.33, "cap_mwe": 693,  "state": "FL", "epz_pop": 58000},
    "Vermont Yankee":      {"lat": 42.78, "lon": -72.52, "cap_mwe": 620,  "state": "VT", "epz_pop": 16000},
    "Vogtle":              {"lat": 33.14, "lon": -81.76, "cap_mwe": 1254, "state": "GA", "epz_pop": 15000},
    "Waterford":           {"lat": 29.99, "lon": -90.48, "cap_mwe": 1075, "state": "LA", "epz_pop": 46000},
    "Watts Bar":           {"lat": 35.60, "lon": -84.79, "cap_mwe": 1173, "state": "TN", "epz_pop": 19000},
    "Wolf Creek":          {"lat": 38.24, "lon": -96.09, "cap_mwe": 1200, "state": "KS", "epz_pop": 7000},
    "Zion":                {"lat": 42.45, "lon": -87.80, "cap_mwe": 1040, "state": "IL", "epz_pop": 108000},
}

MAX_CAPACITY_MWE = 1299   # Nine Mile Point 2 / Grand Gulf — largest US unit
MAX_EPZ_POP      = 350000 # conservative ceiling for normalisation

# ── Scoring ────────────────────────────────────────────────────────────────────

def capacity_norm(mwe):
    return min(1.0, max(0.0, mwe / MAX_CAPACITY_MWE))

def epz_pop_norm(pop):
    return min(1.0, max(0.0, pop / MAX_EPZ_POP))

def power_norm(pct):
    return min(1.0, max(0.0, pct / 100.0))

def warn_score(mwe, epz_pop, power_pct):
    return round(
        0.45 * capacity_norm(mwe) +
        0.35 * epz_pop_norm(epz_pop) +
        0.20 * power_norm(power_pct),
        4
    )

def warn_tier(s):
    # Nuclear: conservative thresholds — even moderate scores warrant attention
    if s >= 0.65: return "EMERGENCY_RESPONSE"
    if s >= 0.40: return "MITIGATION_REQUIRED"
    if s >= 0.20: return "MONITOR"
    return "NORMAL_OPERATION"

# ── Fetch NRC daily power status ───────────────────────────────────────────────

print(f"Fetching NRC Power Reactor Status Report...")
try:
    with urllib.request.urlopen(NRC_STATUS_URL, timeout=30) as r:
        raw = r.read().decode("utf-8", errors="replace")
    lines = raw.strip().splitlines()
    # Format: ReportDt|Unit|Power  — keep most recent date only
    current_power = {}
    most_recent_date = None
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 3: continue
        dt_str, unit_name, power_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
        try:
            power_pct = float(power_str)
        except ValueError:
            continue
        if most_recent_date is None or dt_str > most_recent_date:
            most_recent_date = dt_str
        if dt_str == most_recent_date or dt_str > (most_recent_date or ""):
            current_power[unit_name] = power_pct

    # Re-filter to only most recent date
    current_power = {}
    first_date = lines[1].split("|")[0].strip() if len(lines) > 1 else ""
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 3: continue
        dt_str, unit_name, power_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if dt_str != first_date: continue
        try:
            current_power[unit_name] = float(power_str)
        except ValueError:
            pass

    print(f"  NRC report date: {first_date}")
    print(f"  Units in report: {len(current_power)}")
    nrc_fetch = "live"
except Exception as e:
    print(f"  NRC fetch failed: {e}")
    current_power = {}
    first_date = "unavailable"
    nrc_fetch = f"failed ({e})"

# ── Match NRC units to plant data and score ────────────────────────────────────

def find_plant(unit_name):
    """Match NRC unit name (e.g. 'Indian Point 2') to plant key."""
    for plant_key in PLANT_DATA:
        if unit_name.startswith(plant_key):
            return plant_key
    # Fuzzy: try first two words
    first_two = " ".join(unit_name.split()[:2])
    for plant_key in PLANT_DATA:
        if plant_key.startswith(first_two):
            return plant_key
    return None

# Aggregate power by plant (average across units)
plant_power = {}
plant_units = {}
for unit_name, pwr in current_power.items():
    key = find_plant(unit_name)
    if key:
        plant_power.setdefault(key, []).append(pwr)
        plant_units.setdefault(key, []).append(unit_name)

results = []
matched = 0
for plant_key, info in PLANT_DATA.items():
    units_matched = plant_units.get(plant_key, [])
    powers = plant_power.get(plant_key, [100.0])  # default 100% if no NRC match
    avg_power = sum(powers) / len(powers)
    if units_matched:
        matched += 1

    s = warn_score(info["cap_mwe"], info["epz_pop"], avg_power)
    results.append({
        "plant":        plant_key,
        "state":        info["state"],
        "lat":          info["lat"],
        "lon":          info["lon"],
        "capacity_mwe": info["cap_mwe"],
        "epz_pop_est":  info["epz_pop"],
        "power_pct":    round(avg_power, 1),
        "nrc_units":    units_matched or ["not_in_nrc_status"],
        "warn_score":   s,
        "warn_tier":    warn_tier(s),
    })

results.sort(key=lambda x: x["warn_score"], reverse=True)
print(f"  Plants scored: {len(results)}  (NRC power matched: {matched})")

tier_counts = {}
for r in results:
    tier_counts[r["warn_tier"]] = tier_counts.get(r["warn_tier"], 0) + 1
print(f"  Tier distribution: {tier_counts}")

print("\nTop-15 by WARN score:")
for r in results[:15]:
    print(f"  {r['state']}  {r['plant']:24s}  {r['capacity_mwe']}MWe  "
          f"EPZ_pop={r['epz_pop_est']:,}  {r['power_pct']}%  "
          f"WARN={r['warn_score']:.4f}  {r['warn_tier']}")

# ── Output ─────────────────────────────────────────────────────────────────────

output = {
    "source_power_status": "NRC Power Reactor Status Report (daily, public)",
    "source_plant_data":   "NRC/IAEA operating reactor inventory — compiled from public NRC records",
    "nrc_status_url":      NRC_STATUS_URL,
    "nrc_report_date":     first_date,
    "nrc_fetch_status":    nrc_fetch,
    "fetched_utc":         datetime.now(timezone.utc).isoformat(),
    "plants_scored":       len(results),
    "formula": {
        "warn_score":      "0.45 × capacity_norm + 0.35 × epz_pop_norm + 0.20 × power_norm",
        "capacity_norm":   "net_capacity_mwe / 1299 (largest US unit), clamp [0,1]",
        "epz_pop_norm":    "epz_population_10mi / 350000, clamp [0,1]",
        "power_norm":      "current_power_pct / 100, clamp [0,1]",
        "epz_definition":  "NRC 10-mile Plume Exposure Pathway Emergency Planning Zone",
    },
    "tiers": {
        "EMERGENCY_RESPONSE":  "≥ 0.65 — high-capacity plant, dense EPZ, at power",
        "MITIGATION_REQUIRED": "≥ 0.40 — significant exposure",
        "MONITOR":             "≥ 0.20 — moderate baseline risk",
        "NORMAL_OPERATION":    "< 0.20 — low-capacity or remote plant",
    },
    "claim_boundary": (
        "WARN_nuclear scores BASELINE proximity risk from licensed operating plants — "
        "not a real-time incident alert. EPZ population figures are estimates from "
        "NRC/census data, not modelled plume dispersion. Power output from NRC daily "
        "status; 100% assumed for plants not in current report. "
        "This module does NOT model radiation release, dose rates, or dispersion. "
        "For incident response, use NRC event notification system and state radiological "
        "emergency plans directly. Not validated for emergency management use."
    ),
    "plants": results,
}

out_path = OUT_DIR / "warn_nuclear_plants.json"
payload = json.dumps(output, indent=2).encode()
output["blake3"] = b3(payload)
payload = json.dumps(output, indent=2).encode()
out_path.write_bytes(payload)
print(f"\nOutput: {out_path}  ({out_path.stat().st_size:,} bytes)")
print(f"BLAKE3: {output['blake3'][:16]}...")
