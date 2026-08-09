"""Local customer-asset database with a SQLite spatial index.

Customer assets are deliberately kept separate from public context.  Importing
an asset file replaces only the local customer inventory; it never sends the
inventory to a public provider.
"""
import argparse
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_DB = ROOT / "data" / "waifinders_assets.sqlite3"
CRITICALITIES = {"low", "medium", "high", "critical"}


def connect(path=DEFAULT_DB):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS customer_assets (
      id INTEGER PRIMARY KEY, asset_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
      asset_type TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
      criticality TEXT NOT NULL, population_served INTEGER NOT NULL DEFAULT 0,
      flood_gauge_id TEXT NOT NULL DEFAULT '', updated_utc TEXT NOT NULL);
    CREATE VIRTUAL TABLE IF NOT EXISTS customer_asset_rtree USING rtree(id, min_lat, max_lat, min_lon, max_lon);
    CREATE INDEX IF NOT EXISTS customer_assets_type_idx ON customer_assets(asset_type);
    """)
    return db


def read_csv(path):
    assets = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            if not row.get("asset_id"):
                continue
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Asset row {line} needs numeric lat and lon") from exc
            criticality = (row.get("criticality") or "medium").lower()
            if criticality not in CRITICALITIES:
                raise ValueError(f"Asset row {line} has invalid criticality: {criticality}")
            assets.append({"asset_id": row["asset_id"].strip(), "name": (row.get("name") or row["asset_id"]).strip(),
                "asset_type": (row.get("asset_type") or "facility").strip().lower(), "lat": lat, "lon": lon,
                "criticality": criticality, "population_served": int(float(row.get("population_served") or 0)),
                "flood_gauge_id": (row.get("flood_gauge_id") or "").strip()})
    return assets


def replace_assets(assets, path=DEFAULT_DB):
    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute("DELETE FROM customer_asset_rtree"); db.execute("DELETE FROM customer_assets")
        for asset in assets:
            cursor = db.execute("INSERT INTO customer_assets (asset_id,name,asset_type,lat,lon,criticality,population_served,flood_gauge_id,updated_utc) VALUES (?,?,?,?,?,?,?,?,?)",
                (asset["asset_id"], asset["name"], asset["asset_type"], asset["lat"], asset["lon"], asset["criticality"], asset["population_served"], asset["flood_gauge_id"], now))
            db.execute("INSERT INTO customer_asset_rtree VALUES (?,?,?,?,?)", (cursor.lastrowid, asset["lat"], asset["lat"], asset["lon"], asset["lon"]))
    return len(assets)


def load_assets(path=DEFAULT_DB):
    path = Path(path)
    if not path.exists():
        return [], "asset database not initialized"
    with connect(path) as db:
        rows = [dict(row) for row in db.execute("SELECT asset_id,name,asset_type,lat,lon,criticality,population_served,flood_gauge_id FROM customer_assets ORDER BY asset_id")]
    return rows, "customer asset database loaded"


def nearby_assets(lat, lon, radius_degrees, path=DEFAULT_DB):
    """Return indexed candidates; final great-circle distance remains the caller's job."""
    with connect(path) as db:
        rows = db.execute("""SELECT a.asset_id,a.name,a.asset_type,a.lat,a.lon,a.criticality,a.population_served,a.flood_gauge_id
          FROM customer_asset_rtree r JOIN customer_assets a ON a.id=r.id
          WHERE r.min_lat<=? AND r.max_lat>=? AND r.min_lon<=? AND r.max_lon>=?""",
          (lat + radius_degrees, lat - radius_degrees, lon + radius_degrees, lon - radius_degrees)).fetchall()
    return [dict(row) for row in rows]


def main():
    parser = argparse.ArgumentParser(description="Initialize or replace the local customer asset database.")
    parser.add_argument("csv", help="CSV with asset_id, name, asset_type, lat, lon, criticality, population_served, flood_gauge_id")
    parser.add_argument("--database", default=str(DEFAULT_DB))
    args = parser.parse_args()
    print(f"Customer assets imported: {replace_assets(read_csv(args.csv), args.database)}")


if __name__ == "__main__": main()
