import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_worldwide_hazard_alerts import build_earthquake_audit, infrastructure_near


def test_infrastructure_radius_is_bounded(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"elements": []}
    monkeypatch.setattr("build_worldwide_hazard_alerts.requests.get", lambda *args, **kwargs: Response())
    result = infrastructure_near({"lat": 0, "lon": 0, "match_radius_km": 1000})
    assert result["radius_km"] == 100
    assert result["provider"]


def test_full_earthquake_audit_counts_asset_and_context_stages(monkeypatch, tmp_path):
    monkeypatch.setattr("build_worldwide_hazard_alerts.AUDIT_OUTPUT", tmp_path / "audit.json")
    monkeypatch.setattr("build_worldwide_hazard_alerts.infrastructure_near", lambda event: {"feature_count": 2, "features": [], "radius_km": 50})
    event = {"event_id": "usgs-test", "source": "USGS", "hazard": "earthquake", "title": "M 4 test", "lat": 0, "lon": 0, "match_radius_km": 50}
    live = {"asset_input": {"asset_count": 1}, "actions": [{"event": {"event_id": "usgs-test"}}]}
    result = build_earthquake_audit(live, [event])
    assert result["metrics"]["earthquakes_received"] == 1
    assert result["metrics"]["earthquakes_with_customer_asset_matches"] == 1
    assert result["metrics"]["public_context_lookups_succeeded"] == 1
    assert result["records"][0]["approval_status"] == "PENDING_HUMAN_APPROVAL"
    assert result["records"][0]["status"] == "customer_assets_matched"
