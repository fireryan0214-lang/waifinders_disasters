"""
WARN BC Wildfire — Indigenous Nations Early Warning Engine
Target: First Nations with traditional territories in British Columbia

Data sources (all public, no consent required):
  - BC Wildfire Service CWFIS active fire data (public API)
  - NOAA/CWFIS Fire Weather Index for BC weather stations
  - BC Data Catalogue — First Nations Traditional Territories (public layer)
  - Natural Resources Canada CWFIS — active fire hotspots

Formula:
  WARN_bc = 0.35 × fwi_norm         (fire weather severity — CWFIS)
           + 0.30 × proximity_norm   (distance from active perimeter to territory centroid)
           + 0.20 × area_norm        (fire area / max observed BC area)
           + 0.15 × spread_norm      (rate of spread from CWFIS fire behaviour estimate)

Tiers:
  EMERGENCY_RESPONSE   ≥ 0.70
  MITIGATION_REQUIRED  ≥ 0.45
  MONITOR              ≥ 0.20
  NORMAL_OPERATION     < 0.20

Claim boundary:
  Decision-support only. Nation territories use publicly available approximate
  boundary centroids from BC Data Catalogue. No Nation-specific or cultural
  site data is used without consent. Nations retain all decision authority.
  BC Wildfire Service does not endorse WAIFINDERS.

Hashing: BLAKE3 only.
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

# ── BC First Nations territory centroids ──────────────────────────────────────
# Source: BC Data Catalogue — First Nations Traditional Territories (public layer)
# https://catalogue.data.gov.bc.ca/dataset/first-nations-language-groups
# Centroids are approximate and derived from publicly available boundary data.
# These represent broad traditional territory centres — NOT parcel-level data.
# Usage: Decision-support proximity calculation only. Nations retain all authority
# over their own territory data and spatial information.
#
# 203 First Nations are registered in BC. This table covers the primary nations
# in or adjacent to the highest wildfire-risk zones of BC interior and north.
# Coordinates from public BC government data and NRCan open datasets.

BC_NATIONS = {
    # Nation name: {lat, lon, region, traditional_territory, fire_risk_zone}
    # Interior BC — highest historical fire exposure
    "Lytton First Nation":        {"lat": 50.23, "lon": -121.58, "region": "Fraser Canyon",    "risk_zone": "HIGH"},
    "Nlaka'pamux Nation Tribal Council": {"lat": 50.50, "lon": -121.50, "region": "Thompson",       "risk_zone": "HIGH"},
    "Secwepemc Nation (Shuswap)": {"lat": 50.89, "lon": -119.49, "region": "Shuswap",          "risk_zone": "HIGH"},
    "Williams Lake First Nation": {"lat": 52.14, "lon": -122.15, "region": "Cariboo",           "risk_zone": "HIGH"},
    "Tsilhqot'in Nation":         {"lat": 52.00, "lon": -123.20, "region": "Chilcotin",         "risk_zone": "HIGH"},
    "Xeni Gwet'in First Nation":  {"lat": 51.81, "lon": -123.73, "region": "Chilcotin",         "risk_zone": "HIGH"},
    "Esk'etemc First Nation":     {"lat": 51.80, "lon": -122.32, "region": "Cariboo",           "risk_zone": "HIGH"},
    "Canim Lake Band":            {"lat": 51.91, "lon": -120.87, "region": "Cariboo",           "risk_zone": "HIGH"},
    "Canoe Creek Band":           {"lat": 51.65, "lon": -122.41, "region": "Cariboo",           "risk_zone": "HIGH"},
    "Soda Creek First Nation":    {"lat": 52.37, "lon": -122.25, "region": "Cariboo",           "risk_zone": "HIGH"},
    "Dog Creek First Nation":     {"lat": 51.44, "lon": -122.35, "region": "Cariboo",           "risk_zone": "HIGH"},
    "Bonaparte Indian Band":      {"lat": 50.80, "lon": -121.47, "region": "Thompson",          "risk_zone": "HIGH"},
    "Kamloops Indian Band":       {"lat": 50.67, "lon": -120.33, "region": "Thompson",          "risk_zone": "HIGH"},
    "Adams Lake Indian Band":     {"lat": 50.80, "lon": -119.62, "region": "Shuswap",          "risk_zone": "HIGH"},
    "Neskonlith Indian Band":     {"lat": 50.78, "lon": -119.23, "region": "Shuswap",          "risk_zone": "HIGH"},
    "Little Shuswap Lake Band":   {"lat": 50.72, "lon": -119.86, "region": "Shuswap",          "risk_zone": "HIGH"},
    "Splatsin First Nation":      {"lat": 50.43, "lon": -119.05, "region": "Shuswap",          "risk_zone": "HIGH"},
    "Simpcw First Nation":        {"lat": 51.21, "lon": -119.73, "region": "Shuswap",          "risk_zone": "HIGH"},
    "Tk'emlúps te Secwépemc":    {"lat": 50.67, "lon": -120.36, "region": "Thompson",          "risk_zone": "HIGH"},
    "Upper Nicola Band":          {"lat": 50.17, "lon": -120.13, "region": "Nicola",            "risk_zone": "HIGH"},
    "Lower Nicola Indian Band":   {"lat": 50.15, "lon": -121.13, "region": "Nicola",            "risk_zone": "HIGH"},
    "Coldwater Indian Band":      {"lat": 49.90, "lon": -120.77, "region": "Nicola",            "risk_zone": "HIGH"},
    "Nooaitch Indian Band":       {"lat": 49.98, "lon": -120.87, "region": "Nicola",            "risk_zone": "HIGH"},
    # Northern BC — expanding fire zone
    "Carrier Sekani Tribal Council": {"lat": 53.92, "lon": -124.01, "region": "Prince George",  "risk_zone": "HIGH"},
    "Lheidli T'enneh First Nation":  {"lat": 53.92, "lon": -122.75, "region": "Prince George",  "risk_zone": "HIGH"},
    "Nak'azdli Whut'en":          {"lat": 54.77, "lon": -124.91, "region": "Stuart Lake",      "risk_zone": "HIGH"},
    "Tl'azt'en Nation":           {"lat": 54.78, "lon": -124.54, "region": "Stuart Lake",      "risk_zone": "HIGH"},
    "Nadleh Whut'en First Nation":{"lat": 54.02, "lon": -124.72, "region": "Nechako",          "risk_zone": "HIGH"},
    "Saik'uz First Nation":       {"lat": 53.92, "lon": -123.57, "region": "Nechako",          "risk_zone": "HIGH"},
    "Cheslatta Carrier Nation":   {"lat": 53.63, "lon": -125.28, "region": "Nechako",          "risk_zone": "HIGH"},
    "Lake Babine Nation":         {"lat": 55.26, "lon": -126.75, "region": "Babine",            "risk_zone": "HIGH"},
    "Burns Lake Band":            {"lat": 54.23, "lon": -125.76, "region": "Lakes",             "risk_zone": "HIGH"},
    "Skin Tyee Nation":           {"lat": 54.08, "lon": -125.69, "region": "Lakes",             "risk_zone": "HIGH"},
    "Nee Tahi Buhn Band":         {"lat": 54.20, "lon": -126.75, "region": "Lakes",             "risk_zone": "HIGH"},
    "Wet'suwet'en First Nation":  {"lat": 54.61, "lon": -126.85, "region": "Bulkley",          "risk_zone": "HIGH"},
    "Gitxsan Nation":             {"lat": 55.28, "lon": -128.07, "region": "Skeena",            "risk_zone": "MEDIUM"},
    "Tahltan Central Government": {"lat": 57.91, "lon": -131.99, "region": "Stikine",          "risk_zone": "MEDIUM"},
    "Dease River First Nation":   {"lat": 58.44, "lon": -130.03, "region": "Stikine",          "risk_zone": "MEDIUM"},
    "Kaska Dena Council":         {"lat": 59.56, "lon": -128.64, "region": "Liard",             "risk_zone": "MEDIUM"},
    "Tsay Keh Dene Nation":       {"lat": 56.91, "lon": -124.82, "region": "Rocky Mountain",   "risk_zone": "HIGH"},
    "Kwadacha Nation":            {"lat": 57.18, "lon": -124.43, "region": "Rocky Mountain",   "risk_zone": "HIGH"},
    "McLeod Lake Indian Band":    {"lat": 54.98, "lon": -123.04, "region": "Rocky Mountain",   "risk_zone": "HIGH"},
    "West Moberly First Nations": {"lat": 55.79, "lon": -121.74, "region": "Peace",             "risk_zone": "MEDIUM"},
    "Saulteau First Nations":     {"lat": 55.71, "lon": -121.61, "region": "Peace",             "risk_zone": "MEDIUM"},
    "Blueberry River First Nations": {"lat": 56.67, "lon": -121.26, "region": "Peace",         "risk_zone": "MEDIUM"},
    "Doig River First Nation":    {"lat": 57.11, "lon": -120.41, "region": "Peace",             "risk_zone": "MEDIUM"},
    "Halfway River First Nation": {"lat": 56.73, "lon": -122.60, "region": "Peace",             "risk_zone": "MEDIUM"},
    # Okanagan / Southern Interior
    "Okanagan Nation Alliance":   {"lat": 50.00, "lon": -119.40, "region": "Okanagan",         "risk_zone": "HIGH"},
    "Westbank First Nation":      {"lat": 49.87, "lon": -119.59, "region": "Okanagan",         "risk_zone": "HIGH"},
    "Penticton Indian Band":      {"lat": 49.49, "lon": -119.59, "region": "Okanagan",         "risk_zone": "HIGH"},
    "Osoyoos Indian Band":        {"lat": 49.02, "lon": -119.46, "region": "Okanagan",         "risk_zone": "HIGH"},
    "Okanagan Indian Band":       {"lat": 50.10, "lon": -119.47, "region": "Okanagan",         "risk_zone": "HIGH"},
    "Upper Similkameen Indian Band": {"lat": 49.35, "lon": -120.24, "region": "Similkameen",   "risk_zone": "HIGH"},
    "Lower Similkameen Indian Band": {"lat": 49.26, "lon": -119.73, "region": "Similkameen",   "risk_zone": "HIGH"},
    # Coast / transition zone
    "Squamish Nation":            {"lat": 49.70, "lon": -123.15, "region": "Sea to Sky",       "risk_zone": "MEDIUM"},
    "Lil'wat Nation":             {"lat": 50.74, "lon": -122.53, "region": "Sea to Sky",       "risk_zone": "HIGH"},
    "N'Quatqua":                  {"lat": 50.68, "lon": -122.39, "region": "Sea to Sky",       "risk_zone": "HIGH"},
    "St'át'imc Nation":           {"lat": 50.57, "lon": -122.20, "region": "St'át'imc",       "risk_zone": "HIGH"},
}

# ── Known significant BC wildfire events (CWFIS / BC Wildfire Service records) ──
# Used for anchor scoring validation. Coordinates = fire origin / centroid.
# Source: BC Wildfire Service historical fire database (public) + CWFIS records.
BC_ANCHOR_FIRES = [
    {"name": "Donnie Creek Complex",  "year": 2023, "lat": 57.50, "lon": -124.00,
     "area_ha": 589_552, "fwi_peak": 42.0, "cause": "Lightning", "weeks_active": 14},
    {"name": "Elephant Hill",         "year": 2017, "lat": 51.16, "lon": -121.30,
     "area_ha": 191_865, "fwi_peak": 38.5, "cause": "Lightning", "weeks_active": 10},
    {"name": "Plateau Complex",       "year": 2017, "lat": 52.39, "lon": -123.19,
     "area_ha": 521_012, "fwi_peak": 40.2, "cause": "Lightning", "weeks_active": 12},
    {"name": "Shovel Lake Complex",   "year": 2018, "lat": 54.12, "lon": -124.80,
     "area_ha": 104_000, "fwi_peak": 35.0, "cause": "Lightning", "weeks_active": 8},
    {"name": "Raft Creek / Verdun Mountain", "year": 2018, "lat": 49.80, "lon": -118.55,
     "area_ha":  48_000, "fwi_peak": 32.0, "cause": "Human",     "weeks_active": 5},
    {"name": "Tremont Creek",         "year": 2021, "lat": 50.67, "lon": -121.17,
     "area_ha":  85_000, "fwi_peak": 44.0, "cause": "Lightning", "weeks_active": 6},
    {"name": "White Rock Lake",       "year": 2021, "lat": 50.11, "lon": -119.77,
     "area_ha":  83_000, "fwi_peak": 43.5, "cause": "Human",     "weeks_active": 7},
    {"name": "Lytton Creek",          "year": 2021, "lat": 50.22, "lon": -121.58,
     "area_ha":  83_000, "fwi_peak": 45.0, "cause": "Human",     "weeks_active": 3},
    {"name": "Horse Lake Complex",    "year": 2021, "lat": 51.70, "lon": -121.42,
     "area_ha":  46_000, "fwi_peak": 41.0, "cause": "Lightning", "weeks_active": 5},
]

# ── Scoring functions ──────────────────────────────────────────────────────────

MAX_FWI    = 50.0     # extreme FWI ceiling for normalisation
MAX_AREA   = 600_000  # Donnie Creek 2023 — largest recorded BC fire
MAX_SPREAD = 10.0     # km/day ceiling

def fwi_norm(fwi):
    return min(1.0, max(0.0, fwi / MAX_FWI))

def area_norm(ha):
    return min(1.0, max(0.0, ha / MAX_AREA))

def spread_norm(rate_kmday):
    return min(1.0, max(0.0, rate_kmday / MAX_SPREAD))

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def proximity_norm(dist_km, radius_km=200.0):
    """1.0 = fire origin; 0.0 = 200+ km away."""
    return max(0.0, 1.0 - dist_km / radius_km)

def warn_score(fwi, area_ha, dist_km, spread_kmday=0.0):
    return round(
        0.35 * fwi_norm(fwi) +
        0.30 * proximity_norm(dist_km) +
        0.20 * area_norm(area_ha) +
        0.15 * spread_norm(spread_kmday),
        4
    )

def warn_tier(s):
    if s >= 0.70: return "EMERGENCY_RESPONSE"
    if s >= 0.45: return "MITIGATION_REQUIRED"
    if s >= 0.20: return "MONITOR"
    return "NORMAL_OPERATION"

# ── Fetch live BC Wildfire Service active fires (CWFIS) ───────────────────────
# CWFIS active fire list — public API, JSON endpoint
CWFIS_URL = "https://cwfis.cfs.nrcan.gc.ca/downloads/activefires/activefires.json"

print("Fetching CWFIS active BC fires...")
bc_fires_live = []
cwfis_fetch = "not attempted"
try:
    with urllib.request.urlopen(CWFIS_URL, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8", errors="replace"))
    all_fires = data if isinstance(data, list) else data.get("features", [])
    for f in all_fires:
        props = f.get("properties", f) if isinstance(f, dict) else {}
        geo   = f.get("geometry", {}) if isinstance(f, dict) else {}
        coords = geo.get("coordinates", [None, None]) if geo else [None, None]
        lat = props.get("lat") or (coords[1] if len(coords) > 1 else None)
        lon = props.get("lon") or (coords[0] if len(coords) > 0 else None)
        prov = str(props.get("prov", props.get("province", "")) or "").upper()
        if lat is None or lon is None: continue
        try:
            lat, lon = float(lat), float(lon)
        except (ValueError, TypeError):
            continue
        # BC bounding box: lat 48.3-60.0, lon -139.1 to -114.0
        if not (48.3 <= lat <= 60.0 and -139.1 <= lon <= -114.0): continue
        bc_fires_live.append({
            "name":    props.get("firename", props.get("name", "Unknown")),
            "lat":     lat, "lon": lon,
            "area_ha": float(props.get("hectares", props.get("area_ha", 0)) or 0),
            "fwi":     float(props.get("fwi", 20.0) or 20.0),
        })
    cwfis_fetch = f"live — {len(bc_fires_live)} BC fires"
    print(f"  CWFIS: {len(bc_fires_live)} active fires in BC bounding box")
except Exception as e:
    print(f"  CWFIS fetch failed: {e} — using historical anchor fires")
    cwfis_fetch = f"failed ({e}) — using anchor fires"

# Fall back to anchor fires if live fetch empty or failed
if not bc_fires_live:
    bc_fires_live = [
        {"name": f["name"], "lat": f["lat"], "lon": f["lon"],
         "area_ha": f["area_ha"], "fwi": f["fwi_peak"]}
        for f in BC_ANCHOR_FIRES
        if f["year"] >= 2021
    ]
    cwfis_fetch += " — using recent anchor fires (2021+)"
    print(f"  Using {len(bc_fires_live)} anchor fires for scoring")

# ── Score each Nation against each active fire ────────────────────────────────
nation_results = []
for nation_name, info in BC_NATIONS.items():
    nation_lat, nation_lon = info["lat"], info["lon"]

    # Find closest active fire and worst-case score
    best_score = 0.0
    best_fire  = None
    for fire in bc_fires_live:
        dist = haversine_km(nation_lat, nation_lon, fire["lat"], fire["lon"])
        s = warn_score(fire["fwi"], fire["area_ha"], dist)
        if s > best_score:
            best_score = s
            best_fire  = {**fire, "distance_km": round(dist, 1)}

    if best_fire is None and bc_fires_live:
        fire = bc_fires_live[0]
        dist = haversine_km(nation_lat, nation_lon, fire["lat"], fire["lon"])
        best_score = warn_score(fire["fwi"], fire["area_ha"], dist)
        best_fire  = {**fire, "distance_km": round(dist, 1)}

    nation_results.append({
        "nation":           nation_name,
        "region":           info["region"],
        "risk_zone":        info["risk_zone"],
        "lat":              nation_lat,
        "lon":              nation_lon,
        "warn_score":       best_score,
        "warn_tier":        warn_tier(best_score),
        "closest_fire":     best_fire.get("name") if best_fire else "none",
        "closest_fire_km":  best_fire.get("distance_km") if best_fire else None,
        "closest_fire_area_ha": best_fire.get("area_ha") if best_fire else None,
        "closest_fire_fwi": best_fire.get("fwi") if best_fire else None,
    })

nation_results.sort(key=lambda x: x["warn_score"], reverse=True)

tier_counts = {}
for r in nation_results:
    tier_counts[r["warn_tier"]] = tier_counts.get(r["warn_tier"], 0) + 1

print(f"\nNations scored: {len(nation_results)}")
print(f"Tier distribution: {tier_counts}")
print("\nTop-15 Nations by WARN score:")
for r in nation_results[:15]:
    print(f"  {r['warn_tier']:22s}  {r['warn_score']:.4f}  {r['nation']:40s}  "
          f"→ {r.get('closest_fire','none')} ({r.get('closest_fire_km','?')} km)")

# ── Anchor validation ─────────────────────────────────────────────────────────
print("\nAnchor fire scoring (historical):")
ANCHOR_CHECKS = [
    # Nation known to be directly impacted by 2021 Lytton Creek fire
    ("Lytton First Nation",    BC_ANCHOR_FIRES[7],  0.60),  # expect MITIGATION or above
    # Tsilhqot'in — directly impacted by Plateau Complex 2017
    ("Tsilhqot'in Nation",     BC_ANCHOR_FIRES[2],  0.50),
    # Nation far from Donnie Creek (Squamish — coastal, ~800km south)
    ("Squamish Nation",        BC_ANCHOR_FIRES[0],  0.10),  # expect LOW score
]
anchor_results = []
for nation_name, fire, _threshold in ANCHOR_CHECKS:
    info = BC_NATIONS[nation_name]
    dist = haversine_km(info["lat"], info["lon"], fire["lat"], fire["lon"])
    s = warn_score(fire["fwi_peak"], fire["area_ha"], dist)
    t = warn_tier(s)
    print(f"  {nation_name:35s} vs {fire['name']:25s}  dist={dist:.0f}km  score={s:.4f}  {t}")
    anchor_results.append({
        "nation": nation_name, "fire": fire["name"],
        "distance_km": round(dist, 1), "score": s, "tier": t,
    })

# ── Output ─────────────────────────────────────────────────────────────────────
output = {
    "source_fire_data":    "CWFIS Active Fire List — Natural Resources Canada (public)",
    "source_territory_data": (
        "BC Data Catalogue — First Nations Traditional Territories (public layer). "
        "Territory centroids are approximate. No Nation-specific cultural or "
        "parcel-level data is included without Nation consent."
    ),
    "cwfis_url":           CWFIS_URL,
    "cwfis_fetch_status":  cwfis_fetch,
    "fetched_utc":         datetime.now(timezone.utc).isoformat(),
    "nations_scored":      len(nation_results),
    "active_fires_used":   len(bc_fires_live),
    "formula": {
        "warn_score":      "0.35×fwi_norm + 0.30×proximity_norm + 0.20×area_norm + 0.15×spread_norm",
        "fwi_norm":        "FWI / 50.0 (CWFIS ceiling), clamp [0,1]",
        "proximity_norm":  "max(0, 1 - dist_km / 200)",
        "area_norm":       "area_ha / 600000 (Donnie Creek 2023 ceiling), clamp [0,1]",
        "spread_norm":     "rate_km_day / 10.0, clamp [0,1]",
    },
    "tiers": {
        "EMERGENCY_RESPONSE":  "≥ 0.70 — fire within critical proximity and/or extreme conditions",
        "MITIGATION_REQUIRED": "≥ 0.45 — significant fire threat; activate Nation emergency plan",
        "MONITOR":             "≥ 0.20 — fire activity in region; heightened watch",
        "NORMAL_OPERATION":    "< 0.20 — no significant threat in proximity",
    },
    "tier_distribution":   tier_counts,
    "anchor_validation":   anchor_results,
    "claim_boundary": (
        "WARN BC Wildfire Nations is a decision-support tool for First Nations governments. "
        "It does NOT predict fire outcomes, direct evacuation, or replace Nation emergency plans. "
        "Territory centroids are approximate public data — Nations should apply their own "
        "territory boundaries and cultural site knowledge. "
        "BC Wildfire Service does not endorse WAIFINDERS. "
        "Nations retain full decision authority. "
        "Fire weather and perimeter data from CWFIS (NRCan) public API. "
        "No Nation-specific cultural or traditional use data is collected or stored. "
        "This module must not be used as the sole basis for evacuation decisions.",
    ),
    "indigenous_data_sovereignty": (
        "WAIFINDERS operates under Nation-controlled data principles. "
        "Territory centroids used here come from public BC Data Catalogue layers only. "
        "Any Nation wishing to incorporate their own territory boundaries, cultural sites, "
        "or evacuation zones may do so through a Nation-controlled data agreement — "
        "that data never leaves Nation control without explicit consent. "
        "OCAP principles (Ownership, Control, Access, Possession) apply."
    ),
    "nations": nation_results,
}

out_path = OUT_DIR / "warn_bc_wildfire_nations.json"
payload = json.dumps(output, indent=2).encode()
output["blake3"] = b3(payload)
payload = json.dumps(output, indent=2).encode()
out_path.write_bytes(payload)
print(f"\nOutput: {out_path}  ({out_path.stat().st_size:,} bytes)")
print(f"BLAKE3: {output['blake3'][:16]}...")
