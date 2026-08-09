import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discover_event_city_infrastructure import discover, within


def test_known_city_dataset_is_selected_by_coverage_box(monkeypatch):
    monkeypatch.setattr("discover_event_city_infrastructure.nearest_city", lambda event: {"name": "Test City", "method": "test"})
    alert = {"event": {"event_id": "e", "hazard": "earthquake", "title": "M 3 test", "lat": 40, "lon": -75, "source_url": "https://example.test"}}
    catalog = [{"id": "roads", "city": "test_city", "title": "Roads", "authority": "City", "portal": "arcgis", "landing_page": "https://example.test", "infrastructure_type": "road", "limitations": "context", "coverage_bbox": [-76, 39, -74, 41]}]
    result = discover([alert], catalog)
    assert result["records"][0]["discovery_status"] == "KNOWN_OFFICIAL_SOURCE_AVAILABLE"
    assert within(alert["event"], catalog[0])
