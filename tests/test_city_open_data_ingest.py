import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from city_open_data_ingest import context_points, ingest


def test_road_lines_are_converted_to_local_context_points():
    dataset = {"id": "roads", "title": "Roads", "id_field": "road_id", "name_field": "name", "infrastructure_type": "road", "landing_page": "https://example.test"}
    feature = {"properties": {"road_id": "7", "name": "Main Street"}, "geometry": {"type": "LineString", "coordinates": [[-75, 40], [-74.9, 40.1]]}}
    points = context_points(feature, dataset)
    assert len(points) == 2
    assert points[0]["type"] == "road"
    assert points[0]["name"] == "Main Street"


def test_arcgis_catalog_entry_uses_supplied_fetcher(tmp_path):
    dataset = {"id": "roads", "title": "Roads", "authority": "City", "portal": "arcgis", "id_field": "id", "name_field": "name", "infrastructure_type": "road", "landing_page": "https://example.test"}
    result = ingest(dataset, tmp_path / "public.sqlite3", fetcher=lambda _: [{"properties": {"id": "1", "name": "A"}, "geometry": {"type": "Point", "coordinates": [-75, 40]}}])
    assert result["local_context_points"] == 1
