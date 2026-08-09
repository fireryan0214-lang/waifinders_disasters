"""Create live WARN and WISE outputs from current official feeds only.

Historical WARN/WISE catalogues are intentionally not read here.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from live_incident_exposure import ROOT, clamp

OUT = ROOT / "outputs" / "disaster_demo"
LIVE = OUT / "live_incident_exposure.json"
WARN = OUT / "live_warn_signals.json"
WISE = OUT / "live_wise_decision.json"
TIERS = {"NORMAL_OPERATION": 0, "MONITOR": 1, "MITIGATION_REQUIRED": 2, "EMERGENCY_RESPONSE": 3}

def tier(score):
    if score >= .75: return "EMERGENCY_RESPONSE"
    if score >= .50: return "MITIGATION_REQUIRED"
    if score >= .25: return "MONITOR"
    return "NORMAL_OPERATION"

def earthquake_score(event, exposure):
    d = event["details"]; mag = clamp((float(d.get("magnitude") or 0) - 3) / 5); shallow = clamp(1 - float(d.get("depth_km") or 70) / 70)
    return clamp(.55 * mag + .25 * shallow + .12 * exposure + .08 * .95)

def hurricane_score(event, exposure):
    wind = float(event["details"].get("intensity_kt") or 0); category = clamp((wind - 34) / 122)
    return clamp(.65 * category + .25 * exposure + .10 * .95)

def nws_score(event, exposure):
    return clamp(.65 * float(event["severity"]) + .25 * exposure + .10 * .95)

def main():
    live = json.loads(LIVE.read_text())
    action_counts = {}
    for action in live.get("actions", []): action_counts[action["event"]["event_id"]] = action_counts.get(action["event"]["event_id"], 0) + 1
    grouped = {key: [] for key in ("earthquake", "hurricane", "flood", "wildfire", "tornado")}
    for event in live.get("events", []):
        exposure = clamp(action_counts.get(event["event_id"], 0) / 10)
        if event["hazard"] == "earthquake": grouped["earthquake"].append((event, earthquake_score(event, exposure)))
        elif event["hazard"] == "tropical cyclone": grouped["hurricane"].append((event, hurricane_score(event, exposure)))
        elif "tornado" in event["hazard"]: grouped["tornado"].append((event, nws_score(event, exposure)))
        elif "flood" in event["hazard"] or "river" in event["hazard"]: grouped["flood"].append((event, nws_score(event, exposure)))
        elif "fire" in event["hazard"]: grouped["wildfire"].append((event, nws_score(event, exposure)))
    signals = {}
    for domain, records in grouped.items():
        best = max(records, key=lambda item: item[1], default=(None, 0.0)); event, score = best
        signals[domain] = {"score": round(score, 4), "tier": tier(score), "event_count": len(records), "representative_event": {k: event[k] for k in ("event_id", "title", "source_url", "occurred_utc")} if event else None}
    warn = {"generated_utc": datetime.now(timezone.utc).isoformat(), "mode": "LIVE_WARN", "signals": signals, "formula": "Earthquake: magnitude, depth, asset exposure, source confidence. Hurricane: wind/category, asset exposure, source confidence. NWS hazards: official alert severity, asset exposure, source confidence.", "claim_boundary": "Live decision support only; not an official warning or automated emergency action."}
    WARN.write_text(json.dumps(warn, indent=2))
    elevated = [name for name, signal in signals.items() if TIERS[signal["tier"]] >= 1]
    base = max((TIERS[signal["tier"]] for signal in signals.values()), default=0); final = min(3, base + (1 if len(elevated) >= 2 else 0))
    pending = [a for a in live.get("actions", []) if a["approval_status"] == "PENDING_HUMAN_APPROVAL"]
    wise = {"generated_utc": datetime.now(timezone.utc).isoformat(), "mode": "LIVE_WISE", "operational_status": list(TIERS)[final], "compound_event": len(elevated) >= 2, "elevated_hazards": elevated, "live_warn_signals": signals, "pending_human_actions": pending, "claim_boundary": "Live decision support only. Historical scenarios are excluded. Verify official sources and require trained human approval before action."}
    WISE.write_text(json.dumps(wise, indent=2))
    print(f"Live WARN domains: {sum(s['event_count'] > 0 for s in signals.values())}; LIVE WISE: {wise['operational_status']}")

if __name__ == "__main__": main()
