"""Build a local, provenance-first hazard registry from GIS GeoJSON exports.

Designed to run unchanged from VS Code.  It stores lines (faults/tracks) and
areas (tsunami/hurricane risk zones) locally, with a spatial bounding-box index.
It does not turn historical hazard data into an official warning.
"""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_DB = ROOT / "data" / "waifinders_hazard_registry.sqlite3"


def connect(path=DEFAULT_DB):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS hazard_sources (
      source_id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
      authority TEXT NOT NULL, retrieved_utc TEXT NOT NULL, license_note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hazard_features (
      id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES hazard_sources(source_id),
      feature_id TEXT NOT NULL, hazard_type TEXT NOT NULL, feature_kind TEXT NOT NULL,
      name TEXT NOT NULL, properties_json TEXT NOT NULL, geometry_json TEXT NOT NULL,
      UNIQUE(source_id, feature_id));
    CREATE VIRTUAL TABLE IF NOT EXISTS hazard_feature_rtree USING rtree(id,min_lat,max_lat,min_lon,max_lon);
    CREATE INDEX IF NOT EXISTS hazard_features_hazard_idx ON hazard_features(hazard_type);
    """)
    return db


def coordinates(geometry):
    def collect(value):
        if isinstance(value, (list, tuple)) and len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return [value]
        if isinstance(value, (list, tuple)):
            return [point for child in value for point in collect(child)]
        return []
    return collect(geometry.get("coordinates", []))


def bounds(geometry):
    points = coordinates(geometry)
    if not points:
        raise ValueError("Feature geometry has no usable coordinates")
    lons, lats = zip(*[(float(point[0]), float(point[1])) for point in points])
    return min(lats), max(lats), min(lons), max(lons)


def import_geojson(path, source, database=DEFAULT_DB):
    """Import one authoritative GeoJSON export using a source manifest entry."""
    document = json.loads(Path(path).read_text())
    now = datetime.now(timezone.utc).isoformat()
    imported = 0
    with connect(database) as db:
        db.execute("INSERT OR REPLACE INTO hazard_sources VALUES (?,?,?,?,?,?)", (source["source_id"], source["name"], source["url"], source["authority"], now, source.get("license_note", "Verify terms before redistribution.")))
        for index, feature in enumerate(document.get("features", [])):
            geometry, props = feature.get("geometry") or {}, feature.get("properties") or {}
            if geometry.get("type") not in {"Point", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
                continue
            try:
                min_lat, max_lat, min_lon, max_lon = bounds(geometry)
            except ValueError:
                continue
            feature_id = str(props.get("id") or props.get("OBJECTID") or props.get("FID") or index)
            cursor = db.execute("INSERT INTO hazard_features(source_id,feature_id,hazard_type,feature_kind,name,properties_json,geometry_json) VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_id,feature_id) DO UPDATE SET hazard_type=excluded.hazard_type,feature_kind=excluded.feature_kind,name=excluded.name,properties_json=excluded.properties_json,geometry_json=excluded.geometry_json",
                (source["source_id"], feature_id, source["hazard_type"], geometry["type"], str(props.get("name") or props.get("NAME") or feature_id), json.dumps(props), json.dumps(geometry)))
            row = db.execute("SELECT id FROM hazard_features WHERE source_id=? AND feature_id=?", (source["source_id"], feature_id)).fetchone()
            db.execute("INSERT OR REPLACE INTO hazard_feature_rtree VALUES (?,?,?,?,?)", (row["id"], min_lat, max_lat, min_lon, max_lon))
            imported += 1
    return imported


def main():
    parser = argparse.ArgumentParser(description="Import official fault, tsunami, or hurricane risk GIS exports into the local registry.")
    parser.add_argument("geojson", help="Downloaded authoritative GeoJSON file")
    parser.add_argument("--source", required=True, help="Source ID defined in inputs/hazard_registry_sources.json")
    parser.add_argument("--manifest", default=str(ROOT / "inputs" / "hazard_registry_sources.json"))
    parser.add_argument("--database", default=str(DEFAULT_DB))
    args = parser.parse_args()
    sources = {item["source_id"]: item for item in json.loads(Path(args.manifest).read_text())}
    if args.source not in sources:
        parser.error(f"Unknown source {args.source}. Add it to the manifest with authority and provenance.")
    print(f"Imported {import_geojson(args.geojson, sources[args.source], args.database)} {sources[args.source]['hazard_type']} features")


if __name__ == "__main__": main()
