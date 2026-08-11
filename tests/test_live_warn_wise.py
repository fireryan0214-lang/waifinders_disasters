import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_live_warn_wise import earthquake_score, hurricane_score, live_operational_status, tier

def test_large_shallow_quake_scores_higher():
    low={"details":{"magnitude":4,"depth_km":60}}; high={"details":{"magnitude":7,"depth_km":5}}
    assert earthquake_score(high, 0) > earthquake_score(low, 0)
def test_higher_wind_scores_higher():
    assert hurricane_score({"details":{"intensity_kt":120}},0) > hurricane_score({"details":{"intensity_kt":40}},0)
def test_live_tiers_cover_bounds():
    assert tier(0)=="NORMAL_OPERATION" and tier(.8)=="EMERGENCY_RESPONSE"


def test_unavailable_feed_overrides_empty_normal_signals():
    signals = {"earthquake": {"tier": "NORMAL_OPERATION"}}
    status, compound = live_operational_status(signals, {"status": "DATA_FEED_UNAVAILABLE", "normal_operation_allowed": False})
    assert status == "DATA_FEED_UNAVAILABLE"
    assert compound is False
