import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from asset_store import load_assets, nearby_assets, replace_assets
from public_infrastructure_store import cache_features, cached_context


def test_customer_asset_database_has_indexed_nearby_query(tmp_path):
    database = tmp_path / "assets.sqlite3"
    replace_assets([{"asset_id": "hospital-1", "name": "Hospital", "asset_type": "hospital", "lat": 40, "lon": -75, "criticality": "critical", "population_served": 100, "flood_gauge_id": ""}], database)
    assets, status = load_assets(database)
    assert status == "customer asset database loaded"
    assert assets[0]["asset_id"] == "hospital-1"
    assert nearby_assets(40, -75, .1, database)[0]["asset_type"] == "hospital"


def test_cached_public_context_does_not_need_live_provider(tmp_path):
    database = tmp_path / "public.sqlite3"
    cache_features(40, -75, [{"source_id": "n/1", "type": "substation", "name": "Test substation", "lat": 40, "lon": -75, "source_url": "https://example.test/1"}], "Authoritative source", database)
    context = cached_context({"lat": 40, "lon": -75, "match_radius_km": 50}, database)
    assert context["lookup_status"] == "cached_match"
    assert context["features"][0]["source"] == "Authoritative source"
