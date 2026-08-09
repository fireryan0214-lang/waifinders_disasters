"""Create auditable worldwide earthquake and hurricane alerts with public infrastructure context."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

from live_incident_exposure import ROOT, build
from public_infrastructure_store import cache_features, cached_context

STATE = ROOT / "outputs" / "disaster_demo" / "worldwide_alert_state.json"
OUTPUT = ROOT / "outputs" / "disaster_demo" / "worldwide_hazard_alerts.json"
AUDIT_OUTPUT = ROOT / "outputs" / "disaster_demo" / "worldwide_earthquake_pipeline_audit.json"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def infrastructure_near(event):
    """Return public OSM features near the event reference point; never call these customer assets."""
    local = cached_context(event)
    if local["lookup_status"] != "cache_miss":
        local["provider"] = "local public-infrastructure cache"
        return local
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
            # Keep a scheduled alert run bounded even when a public Overpass
            # mirror is unavailable; source-event alerts still go out.
            candidate = requests.get(endpoint, params={"data": query}, headers={"User-Agent": "WAIFINDERS-Sentinel/0.1"}, timeout=8)
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
        osm_id = f"{item['type']}/{item['id']}"
        lat = item.get("lat") or item.get("center", {}).get("lat")
        lon = item.get("lon") or item.get("center", {}).get("lon")
        features.append({"source_id": osm_id, "osm_id": osm_id, "type": kind, "name": tags.get("name") or tags.get("ref") or "Unnamed public infrastructure", "lat": lat, "lon": lon, "source_url": f"https://www.openstreetmap.org/{item['type']}/{item['id']}", "osm_url": f"https://www.openstreetmap.org/{item['type']}/{item['id']}"})
    cache_features(event["lat"], event["lon"], features, source="OpenStreetMap")
    return {"provider": provider, "lookup_status": "live_fallback_match" if features else "live_fallback_no_features", "radius_km": radius / 1000, "feature_count": len(features), "features": features}


def process_event(event, asset_action_count=0, allow_live_fallback=True, unavailable_note=None):
    """Run the public-context stage and retain an auditable result for one event."""
    try:
        context = infrastructure_near(event) if allow_live_fallback else cached_context(event)
        if not allow_live_fallback and context["lookup_status"] == "cache_miss":
            raise ConnectionError(unavailable_note or "public infrastructure provider unavailable")
        if asset_action_count:
            status = "customer_assets_matched"
        elif context.get("feature_count", 0):
            status = "public_infrastructure_context_matched"
        else:
            status = "source_only_event"
    except Exception as exc:
        context = {"feature_count": 0, "features": [], "note": f"Infrastructure lookup unavailable: {exc.__class__.__name__}"}
        status = "lookup_unavailable"
    return {
        "alert_id": event["event_id"],
        "approval_status": "PENDING_HUMAN_APPROVAL",
        "status": status,
        "event": event,
        "customer_asset_action_count": asset_action_count,
        "public_infrastructure_context": context,
        "claim_boundary": "Public OpenStreetMap context only; verify asset ownership, completeness, and event relevance before action.",
    }


def build_earthquake_audit(live, earthquakes):
    """Exercise every current earthquake through asset, context, and action stages.

    This is deliberately an audit artefact, not an alert queue.  It lets the
    team measure coverage even for low-impact events without treating them as
    operational incidents.
    """
    action_counts = {}
    for action in live.get("actions", []):
        event_id = action["event"]["event_id"]
        action_counts[event_id] = action_counts.get(event_id, 0) + 1
    # Probe the public provider once before fan-out.  When it is unavailable,
    # every event still completes the pipeline with an explicit blocked stage;
    # issuing hundreds of identical failing public requests would only hide the
    # real weakness and overload a community service.
    provider_available = False
    provider_failure = "No earthquake records available for public-context probe."
    probe_context = None
    if earthquakes:
        try:
            probe_context = infrastructure_near(earthquakes[0])
            provider_available = True
        except Exception as exc:
            provider_failure = f"Infrastructure provider unavailable: {exc.__class__.__name__}"
    if provider_available:
        records = [process_event(earthquakes[0], action_counts.get(earthquakes[0]["event_id"], 0))]
        remaining = earthquakes[1:]
        with ThreadPoolExecutor(max_workers=max(1, min(8, len(remaining)))) as pool:
            records.extend(pool.map(lambda event: process_event(event, action_counts.get(event["event_id"], 0)), remaining))
    else:
        # Still run every record through the local cache. Only cache misses are
        # blocked by the unavailable live provider.
        records = [process_event(event, action_counts.get(event["event_id"], 0), allow_live_fallback=False, unavailable_note=provider_failure) for event in earthquakes]
    context_ready = sum(record["status"] in {"customer_assets_matched", "public_infrastructure_context_matched", "source_only_event"} for record in records)
    asset_matched = sum(record["customer_asset_action_count"] > 0 for record in records)
    public_features = sum(record["public_infrastructure_context"].get("feature_count", 0) for record in records)
    status_counts = {status: sum(record["status"] == status for record in records) for status in ("customer_assets_matched", "public_infrastructure_context_matched", "source_only_event", "lookup_unavailable")}
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "FULL_EARTHQUAKE_PIPELINE_AUDIT",
        "audit_scope": "Every earthquake in the current USGS all-day feed is run through official-feed ingestion, customer-asset exposure matching, public infrastructure context lookup, and the human-review gate.",
        "metrics": {
            "earthquakes_received": len(earthquakes),
            "official_source_records": len(earthquakes),
            "customer_assets_loaded": live["asset_input"]["asset_count"],
            "earthquakes_with_customer_asset_matches": asset_matched,
            "customer_asset_actions_created": sum(action_counts.values()),
            "public_context_lookups_succeeded": context_ready,
            "public_context_lookups_failed": len(records) - context_ready,
            "public_context_provider_available": provider_available,
            "public_context_provider_probes": 1 if earthquakes else 0,
            "public_context_records_blocked_by_provider": len(records) if not provider_available else 0,
            "public_infrastructure_features_found": public_features,
            "source_only_records": sum(record["status"] == "source_only_event" for record in records),
            "lookup_unavailable_records": sum(record["status"] == "lookup_unavailable" for record in records),
            "status_counts": status_counts,
            "pipeline_completion_rate": round((context_ready / len(records)) if records else 1.0, 4),
        },
        "records": records,
        "claim_boundary": "Audit and decision support only. A record is not an official warning, and no action is authorized without trained human approval.",
    }
    AUDIT_OUTPUT.write_text(json.dumps(payload, indent=2))
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize", action="store_true", help="Record current events without emitting historical notifications")
    parser.add_argument("--audit-all-earthquakes", action="store_true", help="Run every current earthquake through the complete audit pipeline and write coverage metrics")
    args = parser.parse_args()
    live = build()
    relevant = [event for event in live["events"] if event["hazard"] in {"earthquake", "tropical cyclone"}]
    earthquakes = [event for event in relevant if event["hazard"] == "earthquake"]
    prior = set(json.loads(STATE.read_text()).get("seen_event_ids", [])) if STATE.exists() else set()
    new_events = [event for event in relevant if event["event_id"] not in prior]
    alerts = [] if args.initialize else []
    action_counts = {}
    for action in live.get("actions", []):
        event_id = action["event"]["event_id"]
        action_counts[event_id] = action_counts.get(event_id, 0) + 1
    if not args.initialize:
        with ThreadPoolExecutor(max_workers=max(1, min(8, len(new_events)))) as pool:
            alerts = list(pool.map(lambda event: process_event(event, action_counts.get(event["event_id"], 0)), new_events))
    STATE.write_text(json.dumps({"initialized_utc": datetime.now(timezone.utc).isoformat(), "seen_event_ids": sorted({event["event_id"] for event in relevant})}, indent=2))
    lookup_successes = sum(alert["status"] in {"customer_assets_matched", "public_infrastructure_context_matched", "source_only_event"} for alert in alerts)
    payload = {"generated_utc": datetime.now(timezone.utc).isoformat(), "mode": "WORLDWIDE_EVENT_ALERTS", "initialization": args.initialize, "relevant_events_seen": len(relevant), "new_alert_count": len(alerts), "alerts": alerts,
        "pipeline_metrics": {"new_events_processed": len(new_events), "infrastructure_lookup_successes": lookup_successes, "infrastructure_lookup_failures": len(alerts) - lookup_successes, "public_features_found": sum(alert["public_infrastructure_context"].get("feature_count", 0) for alert in alerts), "customer_assets_matched": sum(alert["status"] == "customer_assets_matched" for alert in alerts), "public_infrastructure_context_matched": sum(alert["status"] == "public_infrastructure_context_matched" for alert in alerts), "source_only_events": sum(alert["status"] == "source_only_event" for alert in alerts), "lookup_unavailable": sum(alert["status"] == "lookup_unavailable" for alert in alerts)},
        "claim_boundary": "Decision support only. These are not official warnings and every action requires trained human review."}
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"Relevant events: {len(relevant)}; new alerts: {len(alerts)}")
    if args.audit_all_earthquakes:
        audit = build_earthquake_audit(live, earthquakes)
        print("Full earthquake audit: " + json.dumps(audit["metrics"], sort_keys=True))


if __name__ == "__main__": main()
