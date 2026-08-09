"""
WAIFINDERS WISE — Multi-Hazard Decision Engine
Combines all WARN signals (wildfire, earthquake, tsunami, flood surge, hurricane) and PULSE
infrastructure exposure into a single operational decision state.

Decision states (from project archive):
  NORMAL_OPERATION     — all hazards low, infrastructure nominal
  MONITOR              — one or more hazards elevated; watch
  MITIGATION_REQUIRED  — significant hazard + infrastructure exposure; act
  EMERGENCY_RESPONSE   — critical hazard or compound event; full response

Cost-of-failure estimates are explicitly labeled ILLUSTRATIVE —
no real traffic/ridership/repair-cost data exists.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

OUT_DIR = Path(__file__).parent.parent / "outputs" / "disaster_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TIER_ORDER = {"NORMAL_OPERATION": 0, "MONITOR": 1, "MITIGATION_REQUIRED": 2, "EMERGENCY_RESPONSE": 3}
# The built-in WARN catalogues contain historical or baseline records. Their
# aggregate is useful for scenario planning, never a present-tense alert.
DATA_MODE = "HISTORICAL_CATALOGUE"

def tier_int(t): return TIER_ORDER.get(t, 0)
def int_tier(i): return list(TIER_ORDER.keys())[min(i, 3)]

# ── Load WARN outputs ─────────────────────────────────────────────────────────
def load(fname):
    p = OUT_DIR / fname
    return json.loads(p.read_text()) if p.exists() else {}

eq_data     = load("warn_earthquake_events.json")
tsun_data   = load("warn_tsunami_events.json")
flood_data  = load("warn_flood_surge_events.json")
hurr_data   = load("warn_hurricane_events.json")
nuke_data   = load("warn_nuclear_plants.json")
pulse_data  = load("pulse_disaster_exposure.json")

# Wildfire WARN — pull from wildfire repo outputs if available
wildfire_path = Path(__file__).parent.parent / "outputs" / "wildfire" / "sentinel" / "ontario_sentinel_intelligence.json"
wildfire_data = json.loads(wildfire_path.read_text()) if wildfire_path.exists() else {}

# ── Extract peak WARN signals per hazard ──────────────────────────────────────
def peak_eq_score(data):
    events = data.get("events", [])
    if not events: return 0.0, "NORMAL_OPERATION"
    top = max(events, key=lambda e: float(e.get("warn_score", 0)))
    return float(top.get("warn_score", 0)), top.get("warn_tier", "NORMAL_OPERATION")

def peak_tsun_score(data):
    events = data.get("events", [])
    if not events: return 0.0, "NORMAL_OPERATION"
    top = max(events, key=lambda e: float(str(e.get("warn_score", 0)) or 0))
    return float(str(top.get("warn_score", 0)) or 0), top.get("warn_tier", "NORMAL_OPERATION")

def peak_flood_score(data):
    events = data.get("events", [])
    if not events: return 0.0, "NORMAL_OPERATION"
    top = max(events, key=lambda e: float(e.get("warn_score", 0)))
    return float(top.get("warn_score", 0)), top.get("warn_tier", "NORMAL_OPERATION")

def peak_hurr_score(data):
    storms = data.get("storms", [])
    if not storms: return 0.0, "NORMAL_OPERATION"
    top = max(storms, key=lambda s: float(s.get("warn_score", 0)))
    return float(top.get("warn_score", 0)), top.get("warn_tier", "NORMAL_OPERATION")

def peak_nuke_score(data):
    plants = data.get("plants", [])
    if not plants: return 0.0, "NORMAL_OPERATION"
    top = max(plants, key=lambda p: float(p.get("warn_score", 0)))
    return float(top.get("warn_score", 0)), top.get("warn_tier", "NORMAL_OPERATION")

def wildfire_tier(data):
    # Pull from ontario sentinel if available
    fwi = data.get("fire_weather", {}).get("fwi", {})
    tier = fwi.get("warn_tier", "NORMAL_OPERATION")
    score = float(fwi.get("fwi_normalized", 0.0))
    return score, tier

eq_score,    eq_tier    = peak_eq_score(eq_data)
tsun_score,  tsun_tier  = peak_tsun_score(tsun_data)
flood_score, flood_tier = peak_flood_score(flood_data)
hurr_score,  hurr_tier  = peak_hurr_score(hurr_data)
nuke_score,  nuke_tier  = peak_nuke_score(nuke_data)
wf_score,    wf_tier    = wildfire_tier(wildfire_data)

# PULSE state
pulse_red   = pulse_data.get("risk_summary", {}).get("RED", 0)
pulse_amber = pulse_data.get("risk_summary", {}).get("AMBER", 0)
pulse_total = sum(pulse_data.get("risk_summary", {}).values()) or 1
pulse_red_pct = pulse_red / pulse_total

if pulse_red_pct >= 0.15:       pulse_tier = "EMERGENCY_RESPONSE"
elif pulse_red_pct >= 0.05:     pulse_tier = "MITIGATION_REQUIRED"
elif pulse_amber / pulse_total >= 0.20: pulse_tier = "MONITOR"
else:                           pulse_tier = "NORMAL_OPERATION"

print("WISE Multi-Hazard Signal Summary:")
print(f"  Wildfire WARN:      score={wf_score:.3f}  tier={wf_tier}")
print(f"  Earthquake WARN:    score={eq_score:.3f}  tier={eq_tier}")
print(f"  Tsunami WARN:       score={tsun_score:.3f}  tier={tsun_tier}")
print(f"  Flood Surge WARN:   score={flood_score:.3f}  tier={flood_tier}")
print(f"  Hurricane WARN:     score={hurr_score:.3f}  tier={hurr_tier}")
print(f"  Nuclear baseline:   score={nuke_score:.3f}  tier={nuke_tier} (planning only; excluded from live decision)")
print(f"  PULSE infra:        RED={pulse_red} ({pulse_red_pct:.1%})  tier={pulse_tier}")

# ── WISE decision logic ───────────────────────────────────────────────────────
hazard_tiers = {
    "wildfire":   wf_tier,
    "earthquake": eq_tier,
    "tsunami":    tsun_tier,
    "flood_surge":flood_tier,
    "hurricane":  hurr_tier,
    "pulse":      pulse_tier,
}

# Base decision = highest individual hazard tier
base_tier_int = max(tier_int(t) for t in hazard_tiers.values())

# Compound escalation: if 2+ hazards are at MONITOR or above, escalate one level
elevated = [h for h, t in hazard_tiers.items() if tier_int(t) >= 1]
compound = len(elevated) >= 2

if compound:
    compound_boost = 1
    print(f"\n  Compound event detected: {elevated} → escalating one level")
else:
    compound_boost = 0

final_tier_int = min(3, base_tier_int + compound_boost)
final_tier = int_tier(final_tier_int)

# ── Cost-of-failure estimate (ILLUSTRATIVE — no real cost data) ───────────────
ILLUSTRATIVE_COSTS = {
    "NORMAL_OPERATION":    {"label": "$0–$10M",    "note": "Routine maintenance window"},
    "MONITOR":             {"label": "$10–$100M",   "note": "Minor infrastructure damage"},
    "MITIGATION_REQUIRED": {"label": "$100M–$1B",   "note": "Significant repair + service disruption"},
    "EMERGENCY_RESPONSE":  {"label": "$1B–$10B+",   "note": "Major disaster — historical range from NOAA damage records"},
}
cost = ILLUSTRATIVE_COSTS[final_tier]

print(f"\n  WISE Decision: {final_tier}")
print(f"  Compound:      {compound} ({len(elevated)} hazards elevated)")
print(f"  Cost estimate: {cost['label']} (ILLUSTRATIVE — {cost['note']})")

# ── Recommended actions per tier ──────────────────────────────────────────────
ACTIONS = {
    "NORMAL_OPERATION": [
        "Maintain standard inspection schedules",
        "Review PULSE priority lists for next maintenance cycle",
    ],
    "MONITOR": [
        "Activate 24h WARN watch — review signals every 6 hours",
        "Pre-position PULSE RED-band assets for priority inspection",
        "Notify operations centres — no public advisory yet",
    ],
    "MITIGATION_REQUIRED": [
        "Deploy repair crews to PULSE RED-band + hazard-zone intersection",
        "Issue public advisory for affected corridors",
        "Open emergency operations coordination with utilities and transport agencies",
        "Pre-position emergency repair stock at highest-risk staging areas",
    ],
    "EMERGENCY_RESPONSE": [
        "Activate full emergency operations protocol",
        "Coordinate with municipal, provincial/state, and federal emergency management",
        "Execute pre-ranked PULSE priority list — do not wait for damage reports",
        "Restrict access to PULSE RED-band bridges and tunnels pending inspection",
        "Issue public emergency notification for all affected communities",
        "Activate mutual-aid agreements with neighbouring utilities/operators",
    ],
}

HISTORICAL_ACTIONS = [
    "Use ranked records for scenario planning and score validation only",
    "Do not activate operations or issue public notices from catalogue scores",
    "Use separately labelled official alert feeds for live incident response",
]

# ── Output ────────────────────────────────────────────────────────────────────
decision = {
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "data_mode": DATA_MODE,
    "operational_status": "NOT_EVALUATED",
    "wise_decision": final_tier,
    "compound_event": compound,
    "elevated_hazards": elevated,
    "hazard_signals": {
        "wildfire":    {"score": round(wf_score,3),    "tier": wf_tier},
        "earthquake":  {"score": round(eq_score,3),    "tier": eq_tier},
        "tsunami":     {"score": round(tsun_score,3),  "tier": tsun_tier},
        "flood_surge": {"score": round(flood_score,3), "tier": flood_tier},
        "hurricane":   {"score": round(hurr_score,3),  "tier": hurr_tier},
        "nuclear":     {"score": round(nuke_score,3),  "tier": nuke_tier, "decision_inclusion": False},
    },
    "pulse_state": {
        "tier": pulse_tier,
        "red_band_count": pulse_red,
        "amber_band_count": pulse_amber,
        "red_band_pct": round(pulse_red_pct, 4),
    },
    "cost_estimate_illustrative": cost,
    "recommended_actions": HISTORICAL_ACTIONS if DATA_MODE == "HISTORICAL_CATALOGUE" else ACTIONS[final_tier],
    "claim_boundary": (
        "WISE historical peak is a research prototype combining experimental WARN signals "
        "and PULSE infrastructure scores. It is not a live operational status. Nuclear baseline "
        "proximity scores are planning-only and are excluded from compound-event escalation. "
        "Not validated for emergency management use. "
        "Cost estimates are illustrative only — no real cost data is embedded."
    ),
    "formula": {
        "base_tier": "max(tier_int) across live decision signals; excludes nuclear baseline",
        "compound_escalation": "+1 tier if 2+ live decision hazards at MONITOR or above",
        "final_tier": "min(EMERGENCY_RESPONSE, base_tier + compound_boost)",
    },
}

out_path = OUT_DIR / "wise_multihazard_decision.json"
out_path.write_text(json.dumps(decision, indent=2))
h = subprocess.run(["b3sum", str(out_path)], capture_output=True, text=True).stdout.strip()
print(f"\nBLAKE3 {out_path.name}: {h}")
print("\nDone — WISE multi-hazard decision engine complete.")
