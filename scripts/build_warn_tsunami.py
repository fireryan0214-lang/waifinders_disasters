"""
WAIFINDERS WARN — Tsunami Module
Real data: NOAA NCEI Global Historical Tsunami Database (public domain).
Fetches real recorded tsunami events: source earthquake magnitude, max wave height,
number of fatalities, runup distance.

WARN signal = weighted composite of wave height, source magnitude, and coastal reach.
No predictions. No calibrated probabilities. Research prototype.
"""
import json
import subprocess
from pathlib import Path

import requests
import pandas as pd

OUT_DIR = Path(__file__).parent.parent / "outputs" / "disaster_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── NOAA NCEI Global Historical Tsunami Database ──────────────────────────────
# Public domain — NOAA National Centers for Environmental Information
BASE = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/events"
NOAA_URL = BASE + "?minYear=1900&maxYear=2024&itemsPerPage=200"

print("Fetching NOAA NCEI Global Historical Tsunami Database (paginated, 1900-2024)…")

items = []
for page in range(1, 10):  # max 9 pages × 200 = 1800 records
    resp = requests.get(BASE, params={"minYear": 1900, "maxYear": 2024, "itemsPerPage": 200, "page": page}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    batch = data.get("items", [])
    items.extend(batch)
    total_pages = data.get("totalPages", 1)
    if page >= total_pages:
        break

print(f"  {len(items)} total tsunami events fetched ({total_pages} pages)")
print(f"  {len(items)} tsunami events returned")

rows = []
for ev in items:
    rows.append({
        "id":               ev.get("id"),
        "year":             ev.get("year"),
        "month":            ev.get("month"),
        "day":              ev.get("day"),
        "country":          ev.get("country", ""),
        "location":         ev.get("locationName", ""),
        "lat":              ev.get("latitude"),
        "lon":              ev.get("longitude"),
        "source_mag":       ev.get("eqMagnitude"),
        "source_depth_km":  ev.get("eqDepth"),
        "max_wave_height_m":ev.get("maxWaterHeight"),
        "num_deaths":       ev.get("deaths"),
        "damage_millions":  ev.get("damageMillionsDollars"),
        "cause":            ev.get("causeCode"),
        "validity":         ev.get("eventValidity"),
    })

df = pd.DataFrame(rows)
df = df.dropna(subset=["max_wave_height_m"])
df["max_wave_height_m"] = pd.to_numeric(df["max_wave_height_m"], errors="coerce")
df["source_mag"] = pd.to_numeric(df["source_mag"], errors="coerce")
df = df[df["max_wave_height_m"] > 0].copy()

print(f"  Events with wave height data: {len(df)}")
print(f"  Max wave height: {df['max_wave_height_m'].max():.1f} m")
print(f"  Year range: {df['year'].min()} – {df['year'].max()}")

# ── WARN scoring ──────────────────────────────────────────────────────────────
# Wave height: 0-1 from 1m to 40m (40m = 2011 Tōhoku measured max ~40.5m)
def norm_wave(h):
    return min(1.0, max(0.0, (h - 1.0) / 39.0))

# Source magnitude: 0-1 from M6.5 to M9.5
def norm_mag(m):
    if pd.isna(m): return 0.3  # unknown → moderate assumption
    return min(1.0, max(0.0, (m - 6.5) / 3.0))

# Coastal reach: proxy — higher wave events tend to travel farther
def norm_reach(h):
    return min(1.0, max(0.0, h / 30.0))

df["wave_norm"]  = df["max_wave_height_m"].apply(norm_wave)
df["mag_norm"]   = df["source_mag"].apply(norm_mag)
df["reach_norm"] = df["max_wave_height_m"].apply(norm_reach)

# WARN composite
df["warn_score"] = (
    0.50 * df["wave_norm"] +
    0.30 * df["mag_norm"] +
    0.20 * df["reach_norm"]
)

def warn_tier(s):
    if s >= 0.75: return "EMERGENCY_RESPONSE"
    if s >= 0.50: return "MITIGATION_REQUIRED"
    if s >= 0.25: return "MONITOR"
    return "NORMAL_OPERATION"

df["warn_tier"] = df["warn_score"].apply(warn_tier)

print(f"\n  Top 5 events by WARN score:")
cols = ["year","location","country","max_wave_height_m","source_mag","warn_score","warn_tier"]
top5 = df.nlargest(5, "warn_score")[cols]
print(top5.to_string(index=False))

# Tier distribution
tier_counts = df["warn_tier"].value_counts()
print(f"\n  Tier distribution:\n{tier_counts.to_string()}")

# ── Known anchor events for validation ───────────────────────────────────────
def check_event(name, year, country):
    match = df[(df["year"] == year) & (df["country"].str.upper() == country.upper())]
    if not match.empty:
        row = match.nlargest(1, "warn_score").iloc[0]
        print(f"  {name}: wave={row['max_wave_height_m']:.1f}m  WARN={row['warn_score']:.3f}  tier={row['warn_tier']}")
    else:
        print(f"  {name}: not found in dataset (may be listed differently)")

print("\n  Anchor event checks:")
check_event("2011 Tōhoku (Japan)", 2011, "JAPAN")
check_event("2004 Indian Ocean", 2004, "INDONESIA")
check_event("1960 Chile", 1960, "CHILE")
check_event("1964 Alaska Good Friday", 1964, "USA")

# ── Output ────────────────────────────────────────────────────────────────────
out_path = OUT_DIR / "warn_tsunami_events.json"

payload = {
    "source": "NOAA NCEI Global Historical Tsunami Database — public domain",
    "url": NOAA_URL,
    "fetched_utc": pd.Timestamp.utcnow().isoformat(),
    "event_count": len(df),
    "formula": {
        "warn_score": "0.50 × wave_norm + 0.30 × mag_norm + 0.20 × reach_norm",
        "wave_norm": "(max_wave_height_m - 1) / 39",
        "mag_norm": "(source_mag - 6.5) / 3.0",
        "reach_norm": "min(1, max_wave_height_m / 30)",
        "tiers": {"EMERGENCY_RESPONSE": "≥0.75", "MITIGATION_REQUIRED": "≥0.50", "MONITOR": "≥0.25", "NORMAL_OPERATION": "<0.25"},
    },
    "claim_boundary": "EXPERIMENTAL research prototype. Not validated for emergency decision use.",
    "events": df.fillna("").astype(str).to_dict(orient="records"),
}

out_path.write_text(json.dumps(payload, indent=2))
h = subprocess.run(["b3sum", str(out_path)], capture_output=True, text=True).stdout.strip()
print(f"\nBLAKE3 {out_path.name}: {h}")
print("\nDone — tsunami WARN module complete.")
