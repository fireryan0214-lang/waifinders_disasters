"""Create auditable worldwide earthquake and hurricane alerts with public infrastructure context."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from live_incident_exposure import ROOT, build

STATE = ROOT / "outputs" / "disaster_demo" / "worldwide_alert_state.json"
OUTPUT = ROOT / "outputs" / "disaster_demo" / "worldwide_hazard_alerts.json"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def infrastructure_near(event):
    """Return public OSM features near the event reference point; never call these customer assets."""
    radius = int(min(max(event["match_radius_km"] * 1000, 10_000), 100_000))
    query = f'''[out:json][timeout:25];(
      nwr["amenity"="hospital"](around:{radius},{event["lat"]},{event["lon"]});
      nwr["emergency"="shelter"](around:{radius},{event["lat"]},{event["lon"]});
      nwr["power"="substation"](around:{radius},{event["lat"]},{event["lon"]});
      way["bridge"="yes"](around:{radius},{event["lat"]},{event["lon"]});
      way["highway"~"motorway|trunk|primary"](around:{radius},{event["lat"]},{event["lon"]});
    );out center tags 100;'''
    failures = []
    response = None
    provider = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            candidate = requests.get(endpoint, params={"data": query}, headers={"User-Agent": "WAIFINDERS-Sentinel/0.1"}, timeout=25)
            candidate.raise_for_status()
            response, provider = candidate, endpoint
            break
        except requests.RequestException as exc:
            failures.append(f"{endpoint}: {exc.__class__.__name__}")
    if response is None:
        raise ConnectionError("; ".join(failures))
    features = []
    for item in response.json().get("elements", []):
        tags = item.get("tags", {})
        kind = "hospital" if tags.get("amenity") == "hospital" else "shelter" if tags.get("emergency") == "shelter" else "substation" if tags.get("power") == "substation" else "bridge" if tags.get("bridge") == "yes" else "major route"
        features.append({"osm_id": f"{item['type']}/{item['id']}", "type": kind, "name": tags.get("name") or tags.get("ref") or "Unnamed public infrastructure", "osm_url": f"https://www.openstreetmap.org/{item['type']}/{item['id']}"})
    return {"provider": provider, "radius_km": radius / 1000, "feature_count": len(features), "features": features}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize", action="store_true", help="Record current events without emitting historical notifications")
    args = parser.parse_args()
    live = build()
    relevant = [event for event in live["events"] if event["hazard"] in {"earthquake", "tropical cyclone"}]
    prior = set(json.loads(STATE.read_text()).get("seen_event_ids", [])) if STATE.exists() else set()
    new_events = [event for event in relevant if event["event_id"] not in prior]
    alerts = [] if args.initialize else []
    if not args.initialize:
        for event in new_events:
            try:
                context = infrastructure_near(event)
                status = "ready_for_human_review"
            except Exception as exc:
                context = {"feature_count": 0, "features": [], "note": f"Infrastructure lookup unavailable: {exc.__class__.__name__}"}
                status = "source_event_alert_only"
            alerts.append({"alert_id": event["event_id"], "approval_status": "PENDING_HUMAN_APPROVAL", "status": status, "event": event, "public_infrastructure_context": context, "claim_boundary": "Public OpenStreetMap context only; verify asset ownership, completeness, and event relevance before action."})
    STATE.write_text(json.dumps({"initialized_utc": datetime.now(timezone.utc).isoformat(), "seen_event_ids": sorted({event["event_id"] for event in relevant})}, indent=2))
    lookup_successes = sum(alert["status"] == "ready_for_human_review" for alert in alerts)
    payload = {"generated_utc": datetime.now(timezone.utc).isoformat(), "mode": "WORLDWIDE_EVENT_ALERTS", "initialization": args.initialize, "relevant_events_seen": len(relevant), "new_alert_count": len(alerts), "alerts": alerts,
        "pipeline_metrics": {"new_events_processed": len(new_events), "infrastructure_lookup_successes": lookup_successes, "infrastructure_lookup_failures": len(alerts) - lookup_successes, "public_features_found": sum(alert["public_infrastructure_context"].get("feature_count", 0) for alert in alerts), "source_event_only_alerts": sum(alert["status"] == "source_event_alert_only" for alert in alerts)},
        "claim_boundary": "Decision support only. These are not official warnings and every action requires trained human review."}
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"Relevant events: {len(relevant)}; new alerts: {len(alerts)}")


if __name__ == "__main__": main()
