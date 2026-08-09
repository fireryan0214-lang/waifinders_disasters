import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_hazard_registry import import_geojson


def test_imports_fault_line_with_spatial_bounds(tmp_path):
    geojson = tmp_path / "faults.geojson"
    geojson.write_text('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":"f-1","name":"Test Fault"},"geometry":{"type":"LineString","coordinates":[[-122,38],[-121,39]]}}]}')
    source = {"source_id": "test", "name": "Test", "url": "https://example.test", "authority": "Test agency", "hazard_type": "earthquake_fault"}
    assert import_geojson(geojson, source, tmp_path / "registry.sqlite3") == 1
