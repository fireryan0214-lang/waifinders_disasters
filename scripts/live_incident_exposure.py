"""WAIFINDERS live incident and asset exposure pipeline.

This is decision support, not an alerting authority. It ingests public official
feeds, matches events to customer-provided assets, and produces ranked actions
that remain PENDING_HUMAN_APPROVAL until a trained operator accepts them.
"""
import csv
import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
OUT_PATH = ROOT / "outputs" / "disaster_demo" / "live_incident_exposure.json"
DEFAULT_ASSETS = ROOT / "inputs" / "assets.csv"
USER_AGENT = "WAIFINDERS-Sentinel/0.1 contact: operations@example.invalid"

SOURCE_RELIABILITY = {"USGS": 0.95, "NWS": 0.95, "NHC": 0.95, "USGS_WATER": 0.90, "NRC": 0.95}
CRITICALITY = {"low": 0.25, "medium": 0.50, "high": 0.75, "critical": 1.00}


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geometry_centroid(geometry):
    """Approximate centroid for Point, Polygon, and MultiPolygon GeoJSON."""
    if not geometry:
        return None
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point" and len(coordinates) >= 2:
        return float(coordinates[1]), float(coordinates[0])
    points = []
    if kind == "Polygon":
        points = [point for ring in coordinates for point in ring]
    elif kind == "MultiPolygon":
        points = [point for polygon in coordinates for ring in polygon for point in ring]
    if not points:
        return None
    return sum(point[1] for point in points) / len(points), sum(point[0] for point in points) / len(points)


def load_assets(path):
    if not path.exists():
        return [], f"asset file not found: {path.name}"
    assets = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            if not row.get("asset_id"):
                continue
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Asset row {line_number} needs numeric lat and lon") from exc
            criticality = (row.get("criticality") or "medium").lower()
            if criticality not in CRITICALITY:
                raise ValueError(f"Asset row {line_number} has invalid criticality: {criticality}")
            assets.append({
                "asset_id": row["asset_id"].strip(), "name": (row.get("name") or row["asset_id"]).strip(),
                "asset_type": (row.get("asset_type") or "facility").strip().lower(), "lat": lat, "lon": lon,
                "criticality": criticality, "population_served": int(float(row.get("population_served") or 0)),
                "flood_gauge_id": (row.get("flood_gauge_id") or "").strip(),
            })
    return assets, "loaded"


def fetch_json(url, params=None):
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"}, timeout=30)
    response.raise_for_status()
    return response.json(), response.url


def fetch_usgs_earthquakes():
    feed, url = fetch_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson")
    events = []
    for feature in feed.get("features", []):
        props, coords = feature.get("properties", {}), feature.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2 or props.get("mag") is None:
            continue
        magnitude = float(props["mag"])
        events.append({
            "event_id": f"usgs-{feature['id']}", "source": "USGS", "hazard": "earthquake", "title": props.get("title", "USGS earthquake"),
            "occurred_utc": datetime.fromtimestamp(props["time"] / 1000, timezone.utc).isoformat(),
            "lat": float(coords[1]), "lon": float(coords[0]), "severity": clamp((magnitude - 3.0) / 5.0),
            "match_radius_km": max(50.0, min(500.0, 30.0 * max(magnitude, 1.0))),
            "source_url": props.get("url", url), "details": {"magnitude": magnitude, "depth_km": coords[2] if len(coords) > 2 else None},
        })
    return events, {"source": "USGS earthquake feed", "url": url, "status": "live", "records": len(events)}


def fetch_nws_alerts():
    # /alerts/active already selects actual active alerts; unsupported filters
    # are intentionally not sent because NWS rejects them with HTTP 400.
    feed, url = fetch_json("https://api.weather.gov/alerts/active")
    severity_map = {"Extreme": 1.0, "Severe": 0.80, "Moderate": 0.60, "Minor": 0.40, "Unknown": 0.30}
    events = []
    for feature in feed.get("features", []):
        props = feature.get("properties", {})
        centre = geometry_centroid(feature.get("geometry"))
        if not centre:
            continue  # area-only alerts without usable geometry are retained in source metadata, not guessed
        events.append({
            "event_id": f"nws-{props.get('id', feature.get('id', 'unknown'))}", "source": "NWS", "hazard": (props.get("event") or "weather").lower(),
            "title": props.get("headline") or props.get("event") or "NWS alert", "occurred_utc": props.get("sent") or props.get("effective"),
            "expires_utc": props.get("expires"), "lat": centre[0], "lon": centre[1], "severity": severity_map.get(props.get("severity"), 0.30),
            "match_radius_km": 100.0, "source_url": props.get("@id") or props.get("uri") or url,
            "details": {"event": props.get("event"), "severity": props.get("severity"), "urgency": props.get("urgency"), "certainty": props.get("certainty")},
        })
    return events, {"source": "NWS active alerts", "url": url, "status": "live", "records": len(events)}


def fetch_nhc_advisories():
    """Use NHC's current-storm JSON; no storm means a successful zero-record refresh."""
    feed, url = fetch_json("https://www.nhc.noaa.gov/CurrentStorms.json")
    storms = feed.get("activeStorms", feed if isinstance(feed, list) else [])
    events = []
    for storm in storms:
        lat, lon = storm.get("latitude"), storm.get("longitude")
        if lat is None or lon is None:
            continue
        intensity = float(storm.get("intensity") or 0)
        name = storm.get("name") or storm.get("stormName") or "NHC storm"
        events.append({
            "event_id": f"nhc-{storm.get('id') or storm.get('binNumber') or name}", "source": "NHC", "hazard": "tropical cyclone",
            "title": f"NHC: {name}", "occurred_utc": storm.get("advisoryDate") or datetime.now(timezone.utc).isoformat(),
            "lat": float(lat), "lon": float(lon), "severity": clamp((intensity - 34.0) / 122.0), "match_radius_km": 300.0,
            "source_url": storm.get("url") or url, "details": {"classification": storm.get("classification"), "intensity_kt": intensity, "pressure_mb": storm.get("pressure")},
        })
    return events, {"source": "NHC current storms", "url": url, "status": "live", "records": len(events)}


def fetch_usgs_gauges(assets):
    site_ids = sorted({asset["flood_gauge_id"] for asset in assets if asset["flood_gauge_id"]})
    if not site_ids:
        return [], {"source": "USGS instant water values", "status": "not_configured", "records": 0, "note": "Add flood_gauge_id to assets.csv to enable gauge monitoring."}
    feed, url = fetch_json("https://waterservices.usgs.gov/nwis/iv/", {"format": "json", "sites": ",".join(site_ids), "parameterCd": "00065", "siteStatus": "all"})
    events = []
    for series in feed.get("value", {}).get("timeSeries", []):
        source = series.get("sourceInfo", {}); location = source.get("geoLocation", {}).get("geogLocation", {})
        values = series.get("values", [{}])[0].get("value", [])
        if not values or "latitude" not in location or "longitude" not in location:
            continue
        reading = values[-1]
        events.append({
            "event_id": f"usgs-gauge-{source.get('siteCode', [{}])[0].get('value', 'unknown')}", "source": "USGS_WATER", "hazard": "river gauge",
            "title": f"USGS gauge: {source.get('siteName', 'unnamed')}", "occurred_utc": reading.get("dateTime"), "lat": float(location["latitude"]), "lon": float(location["longitude"]),
            "severity": 0.30, "match_radius_km": 25.0, "source_url": url, "details": {"stage_ft": reading.get("value"), "qualifiers": reading.get("qualifiers", [])},
        })
    return events, {"source": "USGS instant water values", "url": url, "status": "live", "records": len(events)}


def fetch_nrc_notifications():
    """Ingest the NRC Daily Event Report RSS without guessing event geometry."""
    url = "https://www.nrc.gov/public-involve/rss?feed=event"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    notifications = []
    for item in root.findall(".//item"):
        notifications.append({
            "title": item.findtext("title", default="NRC event notification"), "link": item.findtext("link", default=response.url),
            "published": item.findtext("pubDate", default=""),
        })
    return [], {"source": "NRC Daily Event Report", "url": response.url, "status": "live", "records": 0, "notifications_fetched": len(notifications), "notifications": notifications, "note": "Notifications are ingested but deliberately not asset-matched until a facility location is verified from an authoritative record."}


def suggested_action(asset_type, hazard):
    if asset_type in {"hospital", "shelter"}: return f"Confirm continuity and access plan for {hazard}."
    if asset_type in {"bridge", "route"}: return f"Assess route condition and restrict access if field reports confirm {hazard} impact."
    if asset_type in {"substation", "water", "wastewater"}: return f"Request operator inspection and contingency check for {hazard}."
    return f"Review site status and assign an operator for {hazard}."


def rank_exposures(events, assets):
    ranked = []
    for event in events:
        for asset in assets:
            distance = haversine_km(event["lat"], event["lon"], asset["lat"], asset["lon"])
            if distance > event["match_radius_km"]:
                continue
            proximity = 1.0 - distance / event["match_radius_km"]
            score = 0.45 * event["severity"] + 0.35 * CRITICALITY[asset["criticality"]] + 0.20 * proximity
            confidence = clamp(0.60 * SOURCE_RELIABILITY[event["source"]] + 0.25 * proximity + 0.15 * (1.0 if event["source"] != "NWS" else 0.75))
            ranked.append({
                "action_id": f"{event['event_id']}::{asset['asset_id']}", "approval_status": "PENDING_HUMAN_APPROVAL",
                "priority_score": round(score, 4), "confidence": round(confidence, 4), "event": {key: event[key] for key in ("event_id", "source", "hazard", "title", "occurred_utc", "source_url")},
                "asset": {key: asset[key] for key in ("asset_id", "name", "asset_type", "criticality", "population_served")},
                "distance_km": round(distance, 2), "suggested_action": suggested_action(asset["asset_type"], event["hazard"]),
                "rationale": f"{event['source']} severity {event['severity']:.2f}; {asset['criticality']} criticality; {distance:.1f} km from event reference point.",
            })
    return sorted(ranked, key=lambda action: (-action["priority_score"], -action["confidence"], action["distance_km"]))


def safe_fetch(fetcher, *args):
    try:
        return fetcher(*args)
    except Exception as exc:
        return [], {"source": fetcher.__name__, "status": "failed", "records": 0, "note": f"{exc.__class__.__name__}: {exc}"}


def build(assets_path=DEFAULT_ASSETS):
    assets, asset_status = load_assets(Path(assets_path))
    batches, sources = [], []
    for fetcher, args in ((fetch_usgs_earthquakes, ()), (fetch_nws_alerts, ()), (fetch_nhc_advisories, ()), (fetch_usgs_gauges, (assets,)), (fetch_nrc_notifications, ())):
        events, source = safe_fetch(fetcher, *args)
        batches.extend(events); sources.append(source)
    actions = rank_exposures(batches, assets)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "mode": "LIVE_DECISION_SUPPORT", "asset_input": {"path": str(Path(assets_path)), "status": asset_status, "asset_count": len(assets)},
        "source_refreshes": sources, "live_event_count": len(batches), "events": batches, "action_count": len(actions), "actions": actions,
        "formula": "priority = 0.45 event_severity + 0.35 asset_criticality + 0.20 proximity; confidence combines source reliability and match proximity",
        "claim_boundary": "Decision support only. WAIFINDERS is not an official warning authority. All recommended actions require trained human review and approval; source links must be checked before action.",
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    result = build()
    print(f"Live events: {result['live_event_count']}; matched actions: {result['action_count']}; assets: {result['asset_input']['asset_count']}")
