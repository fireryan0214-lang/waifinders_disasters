"""
WARN Hurricane/Tropical Cyclone Engine
Data: NOAA NHC HURDAT2 Atlantic Best Track 1851-2023 (real data)
Format: https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-nov2019.pdf
Formula: 0.45 × wind_norm + 0.35 × surge_norm + 0.20 × proximity_norm
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

HURDAT2_URL = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2023-051124.txt"

# Major Atlantic/Gulf/Caribbean coastal population centres
COAST_CITIES = [
    (25.77, -80.19, "Miami FL"),
    (29.95, -90.07, "New Orleans LA"),
    (29.76, -95.37, "Houston TX"),
    (27.80, -97.40, "Corpus Christi TX"),
    (30.33, -81.66, "Jacksonville FL"),
    (32.78, -79.94, "Charleston SC"),
    (35.23, -75.60, "Outer Banks NC"),
    (40.71, -74.01, "New York NY"),
    (25.67, -80.36, "Homestead FL"),
    (18.47, -66.12, "San Juan PR"),
    (17.99, -76.79, "Kingston Jamaica"),
    (23.13, -82.38, "Havana Cuba"),
]

# ── Scoring ────────────────────────────────────────────────────────────────────

def wind_norm(kt):
    """Cat-1 threshold (64kt) → 0; extreme Cat-5 (185kt) → 1.0."""
    return min(1.0, max(0.0, (kt - 64) / (185 - 64)))

def category(kt):
    if kt >= 137: return 5
    if kt >= 113: return 4
    if kt >= 96:  return 3
    if kt >= 83:  return 2
    if kt >= 64:  return 1
    return 0

def surge_norm(kt):
    """Saffir-Simpson categorical surge proxy, normalised to 6m scale."""
    surge_m = {0: 0.3, 1: 1.2, 2: 2.1, 3: 3.0, 4: 4.5, 5: 5.5}[category(kt)]
    return min(1.0, surge_m / 6.0)

def proximity_norm(lat, lon):
    """Inverse-distance exposure to coastal population centres, max 500km."""
    min_dist = min(
        math.sqrt((lat - cy)**2 + (lon - cx)**2) * 111
        for cy, cx, _ in COAST_CITIES
    )
    return max(0.0, 1.0 - min_dist / 500.0)

def warn_score(kt, lat, lon):
    return round(
        0.45 * wind_norm(kt) +
        0.35 * surge_norm(kt) +
        0.20 * proximity_norm(lat, lon),
        4
    )

def warn_tier(s):
    if s >= 0.75: return "EMERGENCY_RESPONSE"
    if s >= 0.50: return "MITIGATION_REQUIRED"
    if s >= 0.25: return "MONITOR"
    return "NORMAL_OPERATION"

# ── Fetch & Parse HURDAT2 ──────────────────────────────────────────────────────

print(f"Fetching NOAA NHC HURDAT2: {HURDAT2_URL}")
with urllib.request.urlopen(HURDAT2_URL, timeout=60) as resp:
    raw = resp.read().decode("utf-8")

lines = raw.strip().splitlines()
print(f"  Lines fetched: {len(lines):,}")

storms = []
current = None

for line in lines:
    parts = [p.strip() for p in line.split(",")]
    # Header line: AL012005, ARLENE, 31,
    if len(parts) >= 3 and parts[0].startswith(("AL","EP","CP")):
        current = {
            "storm_id": parts[0],
            "name":     parts[1].strip(),
            "obs":      [],
        }
        storms.append(current)
    elif current and len(parts) >= 8:
        try:
            date_str = parts[0].strip()  # YYYYMMDD
            time_str = parts[1].strip()  # HHMM
            status   = parts[3].strip()  # HU, TS, TD, etc.
            lat_s    = parts[4].strip()  # e.g. "28.5N"
            lon_s    = parts[5].strip()  # e.g. "94.8W"
            wind_kt  = int(parts[6].strip())
            lat = float(lat_s[:-1]) * (1 if lat_s[-1] == "N" else -1)
            lon = float(lon_s[:-1]) * (-1 if lon_s[-1] == "W" else 1)
            year = int(date_str[:4])
            current["obs"].append({
                "date": date_str,
                "time": time_str,
                "status": status,
                "lat": lat,
                "lon": lon,
                "wind_kt": wind_kt,
                "year": year,
            })
        except (ValueError, IndexError):
            pass

print(f"  Storms parsed: {len(storms):,}")

# ── Score: peak intensity per storm (Cat-3+, 1980-2023) ───────────────────────

results = []
for storm in storms:
    peak_obs = None
    peak_score = -1.0
    for obs in storm["obs"]:
        if obs["year"] < 1980 or obs["year"] > 2023: continue
        if obs["wind_kt"] < 96: continue  # Cat-3+ only
        s = warn_score(obs["wind_kt"], obs["lat"], obs["lon"])
        if s > peak_score:
            peak_score = s
            peak_obs = obs

    if peak_obs:
        results.append({
            "storm_id":   storm["storm_id"],
            "name":       storm["name"],
            "year":       peak_obs["year"],
            "date":       peak_obs["date"],
            "lat":        peak_obs["lat"],
            "lon":        peak_obs["lon"],
            "wind_kt":    peak_obs["wind_kt"],
            "category":   category(peak_obs["wind_kt"]),
            "status":     peak_obs["status"],
            "warn_score": peak_score,
            "warn_tier":  warn_tier(peak_score),
        })

results.sort(key=lambda x: x["warn_score"], reverse=True)
print(f"\nCat-3+ storms scored (1980–2023): {len(results)}")

# Tier summary
tier_counts = {}
for r in results:
    tier_counts[r["warn_tier"]] = tier_counts.get(r["warn_tier"], 0) + 1
print("Tier distribution:", tier_counts)

print("\nTop-15 by WARN score:")
for r in results[:15]:
    print(f"  {r['year']} {r['name']:18s}  Cat-{r['category']}  {r['wind_kt']}kt  "
          f"({r['lat']:.1f},{r['lon']:.1f})  WARN={r['warn_score']:.4f}  {r['warn_tier']}")

# ── Known anchor storms (validation) ──────────────────────────────────────────

anchor_names = {"ANDREW","KATRINA","IRMA","MARIA","DORIAN","MICHAEL","IAN","GILBERT","ALLEN","HUGO","WILMA"}
anchors = [r for r in results if r["name"] in anchor_names]
anchor_labels = [str(r["year"]) + " " + r["name"] for r in anchors]
print(f"\nAnchor storms found: {anchor_labels}")

# ── Output ─────────────────────────────────────────────────────────────────────

output = {
    "source":        "NOAA NHC HURDAT2 Atlantic Best Track 1851-2023",
    "url":           HURDAT2_URL,
    "fetched_utc":   datetime.now(timezone.utc).isoformat(),
    "basin":         "North Atlantic",
    "filter":        "Cat-3+ (wind >= 96kt), years 1980–2023",
    "storms_parsed": len(storms),
    "storms_scored": len(results),
    "tier_summary":  tier_counts,
    "formula": {
        "warn_score":      "0.45 × wind_norm + 0.35 × surge_norm + 0.20 × proximity_norm",
        "wind_norm":       "(wind_kt - 64) / (185 - 64), clamp [0,1]",
        "surge_norm":      "Saffir-Simpson categorical proxy / 6.0, clamp [0,1]",
        "proximity_norm":  "1 - min_coast_city_dist_km / 500, clamp [0,1]",
    },
    "tiers": {
        "EMERGENCY_RESPONSE":  "≥ 0.75",
        "MITIGATION_REQUIRED": "≥ 0.50",
        "MONITOR":             "≥ 0.25",
        "NORMAL_OPERATION":    "< 0.25",
    },
    "coastal_cities_used": [c[2] for c in COAST_CITIES],
    "claim_boundary": (
        "Surge potential is a Saffir-Simpson categorical proxy, not a hydrodynamic model. "
        "Proximity uses straight-line distance to city centroids — no landfall analysis or "
        "track projection. Scores represent peak 6-hourly intensity, not integrated hazard exposure. "
        "Offshore Cat-5 storms score lower than weaker storms making direct landfall."
    ),
    "storms": results,
}

out_path = OUT_DIR / "warn_hurricane_events.json"
payload = json.dumps(output, indent=2).encode()
output["blake3"] = b3(payload)
payload = json.dumps(output, indent=2).encode()
out_path.write_bytes(payload)
print(f"\nOutput: {out_path}  ({out_path.stat().st_size:,} bytes)")
print(f"BLAKE3: {output['blake3'][:16]}...")
