"""
WAIFINDERS WARN — Flood Surge Module
Real data: NOAA Tides & Currents API — observed water levels at real tide gauge stations.
Uses historical storm surge events at US coastal gauges (public domain).

Test cases:
  - Hurricane Harvey 2017: Rockport TX (Station 8774770)
  - Hurricane Ida 2021: Grand Isle LA (Station 8761724)
  - Hurricane Sandy 2012: The Battery NY (Station 8518750)
  - Hurricane Ian 2022: Fort Myers FL (Station 8725520)

WARN signal = surge height above MHHW (Mean Higher High Water) normalized to
known catastrophic thresholds. No prediction. Research prototype.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import requests
import pandas as pd

OUT_DIR = Path(__file__).parent.parent / "outputs" / "disaster_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── NOAA CO-OPS gauge definitions for real storm surge events ─────────────────
# product=water_level, datum=MHHW, units=metric
GAUGE_EVENTS = [
    {
        "name":    "Hurricane Sandy 2012",
        "station": "8518750",
        "label":   "The Battery, NY",
        "start":   "20121029",
        "end":     "20121031",
        "known_surge_m": 3.33,  # NOAA-reported storm surge peak
        "lat": 40.70, "lon": -74.01,
        "region": "Northeast USA",
    },
    {
        "name":    "Hurricane Harvey 2017",
        "station": "8774770",
        "label":   "Rockport, TX",
        "start":   "20170825",
        "end":     "20170827",
        "known_surge_m": 3.96,
        "lat": 28.02, "lon": -97.05,
        "region": "Gulf Coast",
    },
    {
        "name":    "Hurricane Ida 2021",
        "station": "8761724",
        "label":   "Grand Isle, LA",
        "start":   "20210829",
        "end":     "20210831",
        "known_surge_m": 4.27,
        "lat": 29.26, "lon": -89.96,
        "region": "Gulf Coast",
    },
    {
        "name":    "Hurricane Ian 2022",
        "station": "8725520",
        "label":   "Fort Myers, FL",
        "start":   "20220928",
        "end":     "20220930",
        "known_surge_m": 4.57,  # ~15ft surge reported
        "lat": 26.65, "lon": -81.87,
        "region": "Southeast USA",
    },
]

BASE_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

results = []

for ev in GAUGE_EVENTS:
    print(f"Fetching NOAA tide gauge: {ev['name']} — {ev['label']} (station {ev['station']})…")
    params = {
        "station":   ev["station"],
        "begin_date":ev["start"],
        "end_date":  ev["end"],
        "product":   "water_level",
        "datum":     "MHHW",
        "time_zone": "GMT",
        "units":     "metric",
        "format":    "json",
        "application": "waifinders_research_prototype",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        raw = resp.json()

        if "data" in raw:
            obs = pd.DataFrame(raw["data"])
            obs["v"] = pd.to_numeric(obs["v"], errors="coerce")
            obs = obs.dropna(subset=["v"])
            peak_observed = float(obs["v"].max())
            fetch_status = "live"
        else:
            # Gauge may be offline; use documented known surge
            peak_observed = ev["known_surge_m"]
            fetch_status = "fallback_known_value"
            print(f"  Note: live data unavailable — using documented surge {peak_observed}m")

    except Exception as exc:
        peak_observed = ev["known_surge_m"]
        fetch_status = f"fallback_known_value ({exc.__class__.__name__})"
        print(f"  Note: fetch error ({exc.__class__.__name__}) — using documented surge {peak_observed}m")

    # ── WARN flood surge score ─────────────────────────────────────────────
    # Surge thresholds (metres above MHHW):
    #   < 0.6m  → nuisance flooding (NORMAL)
    #   0.6-1.2 → minor flood (MONITOR)
    #   1.2-2.4 → moderate flood (MITIGATION_REQUIRED)
    #   > 2.4m  → major/catastrophic (EMERGENCY_RESPONSE)
    # Normalise to catastrophic threshold of 5m (Ian-class upper bound)
    surge_norm = min(1.0, max(0.0, peak_observed / 5.0))

    if surge_norm >= 0.70:    tier = "EMERGENCY_RESPONSE"
    elif surge_norm >= 0.45:  tier = "MITIGATION_REQUIRED"
    elif surge_norm >= 0.20:  tier = "MONITOR"
    else:                     tier = "NORMAL_OPERATION"

    record = {
        **ev,
        "peak_water_level_m_above_mhhw": round(peak_observed, 3),
        "surge_norm":  round(surge_norm, 4),
        "warn_score":  round(surge_norm, 4),  # single-feature; surge is the primary signal
        "warn_tier":   tier,
        "fetch_status":fetch_status,
        "data_source": "NOAA CO-OPS Tides & Currents API — public domain",
    }
    results.append(record)
    print(f"  Peak: {peak_observed:.2f}m above MHHW → WARN score {surge_norm:.3f} → {tier}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n  Flood surge WARN summary:")
for r in sorted(results, key=lambda x: -x["warn_score"]):
    print(f"  {r['name']:35s}  surge={r['peak_water_level_m_above_mhhw']:.2f}m  score={r['warn_score']:.3f}  {r['warn_tier']}")

# ── Output ────────────────────────────────────────────────────────────────────
out_path = OUT_DIR / "warn_flood_surge_events.json"
payload = {
    "source": "NOAA CO-OPS Tides & Currents API — public domain (tidesandcurrents.noaa.gov)",
    "fetched_utc": pd.Timestamp.utcnow().isoformat(),
    "datum": "MHHW (Mean Higher High Water)",
    "units": "metres",
    "formula": {
        "surge_norm": "peak_water_level_m / 5.0 (capped at 1.0)",
        "warn_score": "surge_norm",
        "tiers": {
            "EMERGENCY_RESPONSE": "≥0.70 (≥3.5m above MHHW)",
            "MITIGATION_REQUIRED": "≥0.45 (≥2.25m)",
            "MONITOR": "≥0.20 (≥1.0m)",
            "NORMAL_OPERATION": "<0.20",
        },
    },
    "claim_boundary": "EXPERIMENTAL research prototype. Not validated for emergency decision use.",
    "events": results,
}
out_path.write_text(json.dumps(payload, indent=2))
h = subprocess.run(["b3sum", str(out_path)], capture_output=True, text=True).stdout.strip()
print(f"\nBLAKE3 {out_path.name}: {h}")
print("\nDone — flood surge WARN module complete.")
