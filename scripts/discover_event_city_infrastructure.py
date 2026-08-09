"""Identify a recorded earthquake's nearest city and infrastructure-source path.

Discovery results are evidence for an operator to validate; only catalogued
government sources are eligible for automatic prefetch.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from city_open_data_ingest import CATALOG

ROOT = Path(__file__).parent.parent
ALERTS = ROOT / "outputs" / "disaster_demo" / "worldwide_hazard_alerts.json"
OUTPUT = ROOT / "outputs" / "disaster_demo" / "city_infrastructure_discovery.json"
USER_AGENT = "WAIFINDERS-Sentinel/0.1 contact: operations@example.invalid"


def within(event, dataset):
    box = dataset.get("coverage_bbox")
    if not box:
        return False
    west, south, east, north = box
    return west <= event["lon"] <= east and south <= event["lat"] <= north


def nearest_city(event, reverse=requests.get):
    """Use reverse geocoding only to name a nearby place, never for hazard facts."""
    try:
        response = reverse("https://nominatim.openstreetmap.org/reverse", params={"lat": event["lat"], "lon": event["lon"], "format": "jsonv2", "zoom": 10}, headers={"User-Agent": USER_AGENT}, timeout=15)
        response.raise_for_status()
        address = response.json().get("address", {})
        place = next((address.get(key) for key in ("city", "town", "village", "municipality", "county") if address.get(key)), None)
        return {"name": place or event["title"], "country": address.get("country"), "method": "reverse_geocoded_nearest_place"}
    except requests.RequestException:
        return {"name": event["title"], "country": None, "method": "event_title_fallback"}


def discover(alerts, catalog):
    records = []
    for alert in alerts:
        event = alert["event"]
        if event["hazard"] != "earthquake":
            continue
        known = [dataset for dataset in catalog if within(event, dataset)]
        city = nearest_city(event)
        records.append({"event_id": event["event_id"], "event_title": event["title"], "source_url": event["source_url"], "nearest_city": city,
            "available_official_datasets": [{key: dataset[key] for key in ("id", "city", "title", "authority", "portal", "landing_page", "infrastructure_type", "limitations")} for dataset in known],
            "discovery_status": "KNOWN_OFFICIAL_SOURCE_AVAILABLE" if known else "CITY_SOURCE_DISCOVERY_REQUIRED",
            "next_step": f"Run city_open_data_ingest.py --city {known[0]['city']}" if known else "Find and validate the city/county/state GIS source before adding it to city_open_data_catalog.json."})
    return {"generated_utc": datetime.now(timezone.utc).isoformat(), "mode": "EVENT_CITY_INFRASTRUCTURE_DISCOVERY", "records": records,
        "claim_boundary": "Nearest-city identification is geographic context only. Only catalogued government sources may be ingested automatically; infrastructure context is not a warning or proof of impact."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alerts", default=str(ALERTS)); parser.add_argument("--catalog", default=str(CATALOG))
    args = parser.parse_args()
    alerts = json.loads(Path(args.alerts).read_text()).get("alerts", [])
    payload = discover(alerts, json.loads(Path(args.catalog).read_text()))
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"City infrastructure discovery records: {len(payload['records'])}")


if __name__ == "__main__": main()
