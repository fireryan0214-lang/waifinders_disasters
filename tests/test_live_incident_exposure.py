import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from live_incident_exposure import CRITICALITY, haversine_km, rank_exposures


def event():
    return {"event_id": "e1", "source": "USGS", "hazard": "earthquake", "title": "Test quake", "occurred_utc": "2026-08-09T00:00:00Z", "lat": 40.0, "lon": -75.0, "severity": .8, "match_radius_km": 100.0, "source_url": "https://example.test"}


def asset(name="Critical hospital", criticality="critical", lat=40.1, lon=-75.0):
    return {"asset_id": name.lower().replace(" ", "-"), "name": name, "asset_type": "hospital", "lat": lat, "lon": lon, "criticality": criticality, "population_served": 1000, "flood_gauge_id": ""}


def test_haversine_same_point_is_zero():
    assert haversine_km(40, -75, 40, -75) == 0


def test_haversine_distance_is_reasonable():
    assert 10 < haversine_km(40.0, -75.0, 40.1, -75.0) < 12


def test_only_assets_inside_event_radius_match():
    actions = rank_exposures([event()], [asset(), asset("Far site", lat=42, lon=-75)])
    assert len(actions) == 1


def test_match_requires_human_approval():
    assert rank_exposures([event()], [asset()])[0]["approval_status"] == "PENDING_HUMAN_APPROVAL"


def test_higher_criticality_ranks_higher_at_same_distance():
    actions = rank_exposures([event()], [asset("Critical", "critical"), asset("Low", "low")])
    assert actions[0]["asset"]["criticality"] == "critical"


def test_action_has_authoritative_source_link():
    assert rank_exposures([event()], [asset()])[0]["event"]["source_url"] == "https://example.test"


def test_criticality_constants_are_bounded():
    assert all(0 <= value <= 1 for value in CRITICALITY.values())
