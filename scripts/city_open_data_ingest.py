"""Preload city open-data infrastructure into the local public context cache."""
import argparse
import json
from pathlib import Path

import requests

from public_infrastructure_store import cache_features, tile_for

ROOT = Path(__file__).parent.parent
CATALOG = ROOT / "inputs" / "city_open_data_catalog.json"
USER_AGENT = "WAIFINDERS-Sentinel/0.1 contact: operations@example.invalid"


def positions(geometry):
    def walk(value):
        if isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)):
            return [value]
        return [point for child in value if isinstance(child, list) for point in walk(child)] if isinstance(value, list) else []
    return walk((geometry or {}).get("coordinates", []))


def context_points(feature, dataset):
    """Represent each line vertex locally so roads can be found without a live map call."""
    props, points = feature.get("properties", {}), positions(feature.get("geometry"))
    source_id = str(props.get(dataset.get("id_field", "id")) or feature.get("id") or "unknown")
    name = str(props.get(dataset.get("name_field", "name")) or props.get("name") or dataset["title"])
    output = []
    # Store endpoints and a midpoint for a line.  This keeps the cache compact;
    # the returned record is public route context, never a precise passability
    # or geometry-intersection claim.
    indexes = sorted({0, len(points) // 2, len(points) - 1}) if points else []
    for index in indexes:
        point = points[index]
        output.append({"source_id": f"{dataset['id']}:{source_id}:{index}", "type": dataset["infrastructure_type"], "name": name, "lat": point[1], "lon": point[0], "source_url": dataset["landing_page"]})
    return output


def fetch_socrata(dataset, limit=50_000):
    endpoint = dataset["endpoint"]
    response = requests.get(endpoint, params={"$limit": limit}, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}, timeout=60)
    response.raise_for_status()
    return response.json().get("features", [])


def fetch_arcgis(dataset, limit=None):
    """Download an official ArcGIS Feature/MapServer layer in bounded pages."""
    limit = int(limit or dataset.get("page_size", 2_000))
    features, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "returnGeometry": "true", "f": "geojson", "outSR": 4326, "resultRecordCount": limit}
        # Some otherwise valid public MapServer layers treat resultOffset=0 as
        # an empty query. Only send an offset after the first page.
        if offset:
            params["resultOffset"] = offset
        response = requests.get(dataset["endpoint"].rstrip("/") + "/query", params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}, timeout=60)
        response.raise_for_status()
        page = response.json().get("features", [])
        features.extend(page)
        if len(page) < limit:
            return features
        offset += len(page)


def ingest(dataset, database=None, fetcher=fetch_socrata):
    if dataset.get("portal") not in {"socrata", "arcgis"}:
        raise ValueError(f"Unsupported portal: {dataset.get('portal')}; add an adapter before enabling this dataset.")
    if fetcher is fetch_socrata:
        fetcher = fetch_socrata if dataset["portal"] == "socrata" else fetch_arcgis
    features = fetcher(dataset)
    points = [point for feature in features for point in context_points(feature, dataset)]
    # City centerlines can be large.  Cache in geographic tiles, which makes
    # repeated nearby events entirely local after preload.
    by_tile = {}
    for point in points:
        by_tile.setdefault(tile_for(point["lat"], point["lon"]), []).append(point)
    for tile_points in by_tile.values():
        reference = tile_points[0]
        if database:
            cache_features(reference["lat"], reference["lon"], tile_points, source=dataset["authority"], path=database)
        else:
            cache_features(reference["lat"], reference["lon"], tile_points, source=dataset["authority"])
    return {"dataset": dataset["id"], "features_downloaded": len(features), "local_context_points": len(points)}


def main():
    parser = argparse.ArgumentParser(description="Cache published city infrastructure datasets locally before an event.")
    parser.add_argument("--catalog", default=str(CATALOG))
    parser.add_argument("--city", help="Optional city ID to ingest")
    parser.add_argument("--database")
    args = parser.parse_args()
    datasets = json.loads(Path(args.catalog).read_text())
    for dataset in datasets:
        if not dataset.get("enabled") or (args.city and dataset["city"] != args.city):
            continue
        print(json.dumps(ingest(dataset, args.database), sort_keys=True))


if __name__ == "__main__": main()
