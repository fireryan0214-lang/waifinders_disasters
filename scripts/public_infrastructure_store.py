"""Cached local public-infrastructure context, separate from customer assets."""
import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_DB = ROOT / "data" / "waifinders_public_infrastructure.sqlite3"


def connect(path=DEFAULT_DB):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS public_infrastructure (
      id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, feature_type TEXT NOT NULL,
      name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, source_url TEXT NOT NULL, updated_utc TEXT NOT NULL,
      UNIQUE(source, source_id));
    CREATE VIRTUAL TABLE IF NOT EXISTS public_infrastructure_rtree USING rtree(id,min_lat,max_lat,min_lon,max_lon);
    CREATE TABLE IF NOT EXISTS public_tiles (tile TEXT PRIMARY KEY, source TEXT NOT NULL, refreshed_utc TEXT NOT NULL, feature_count INTEGER NOT NULL);
    """)
    return db


def tile_for(lat, lon):
    return f"{math.floor(float(lat))}:{math.floor(float(lon))}"


def cache_features(lat, lon, features, source="OpenStreetMap", path=DEFAULT_DB):
    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        for feature in features:
            if feature.get("lat") is None or feature.get("lon") is None:
                continue
            db.execute("INSERT INTO public_infrastructure(source,source_id,feature_type,name,lat,lon,source_url,updated_utc) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(source,source_id) DO UPDATE SET feature_type=excluded.feature_type,name=excluded.name,lat=excluded.lat,lon=excluded.lon,source_url=excluded.source_url,updated_utc=excluded.updated_utc",
                (source, feature["source_id"], feature["type"], feature.get("name") or "Unnamed public infrastructure", float(feature["lat"]), float(feature["lon"]), feature.get("source_url", ""), now))
            row = db.execute("SELECT id FROM public_infrastructure WHERE source=? AND source_id=?", (source, feature["source_id"])).fetchone()
            db.execute("INSERT OR REPLACE INTO public_infrastructure_rtree VALUES (?,?,?,?,?)", (row["id"], float(feature["lat"]), float(feature["lat"]), float(feature["lon"]), float(feature["lon"])))
        db.execute("INSERT OR REPLACE INTO public_tiles VALUES (?,?,?,?)", (tile_for(lat, lon), source, now, len(features)))


def cached_context(event, path=DEFAULT_DB):
    """Query local cache. `cache_miss` means a live fallback may be attempted."""
    if not Path(path).exists():
        return {"lookup_status": "cache_miss", "feature_count": 0, "features": []}
    radius = min(max(float(event["match_radius_km"]), 10), 100)
    lat, lon = float(event["lat"]), float(event["lon"])
    # A deliberately broad bounding box; the event runner is a context finder,
    # not a claim that every returned public feature is affected.
    degrees = radius / 111
    with connect(path) as db:
        rows = db.execute("""SELECT p.source,p.source_id,p.feature_type,p.name,p.source_url
          FROM public_infrastructure_rtree r JOIN public_infrastructure p ON p.id=r.id
          WHERE r.min_lat<=? AND r.max_lat>=? AND r.min_lon<=? AND r.max_lon>=? LIMIT 100""",
          (lat + degrees, lat - degrees, lon + degrees, lon - degrees)).fetchall()
        tile = db.execute("SELECT source,refreshed_utc,feature_count FROM public_tiles WHERE tile=?", (tile_for(lat, lon),)).fetchone()
    features = [{"type": row["feature_type"], "name": row["name"], "source": row["source"], "source_url": row["source_url"]} for row in rows]
    if features:
        return {"lookup_status": "cached_match", "feature_count": len(features), "features": features, "radius_km": radius}
    if tile:
        return {"lookup_status": "cached_no_features", "feature_count": 0, "features": [], "radius_km": radius, "note": f"Cached {tile['source']} tile refreshed {tile['refreshed_utc']}"}
    return {"lookup_status": "cache_miss", "feature_count": 0, "features": [], "radius_km": radius}


def import_geojson(path, source, database=DEFAULT_DB):
    """Import an authoritative national/regional GeoJSON export into the local layer."""
    document = json.loads(Path(path).read_text())
    features = []
    for index, item in enumerate(document.get("features", [])):
        geometry, props = item.get("geometry") or {}, item.get("properties") or {}
        if geometry.get("type") != "Point" or len(geometry.get("coordinates", [])) < 2:
            continue
        lon, lat = geometry["coordinates"][:2]
        features.append({"source_id": str(props.get("id") or props.get("asset_id") or index), "type": props.get("type") or props.get("asset_type") or "public infrastructure", "name": props.get("name") or "Unnamed public infrastructure", "lat": lat, "lon": lon, "source_url": props.get("source_url") or ""})
    # Stamp every touched geographic tile, allowing zero-result cache checks.
    for feature in features:
        cache_features(feature["lat"], feature["lon"], [feature], source, database)
    return len(features)


def main():
    parser = argparse.ArgumentParser(description="Manage the locally cached public-infrastructure layer.")
    parser.add_argument("--import-geojson", help="Authoritative national or regional Point GeoJSON export")
    parser.add_argument("--source", default="Authoritative regional source")
    parser.add_argument("--database", default=str(DEFAULT_DB))
    args = parser.parse_args()
    if not args.import_geojson:
        parser.error("--import-geojson is required")
    print(f"Public infrastructure imported: {import_geojson(args.import_geojson, args.source, args.database)}")


if __name__ == "__main__": main()
