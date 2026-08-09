import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_live_warn_wise import earthquake_score, hurricane_score, tier

def test_large_shallow_quake_scores_higher():
    low={"details":{"magnitude":4,"depth_km":60}}; high={"details":{"magnitude":7,"depth_km":5}}
    assert earthquake_score(high, 0) > earthquake_score(low, 0)
def test_higher_wind_scores_higher():
    assert hurricane_score({"details":{"intensity_kt":120}},0) > hurricane_score({"details":{"intensity_kt":40}},0)
def test_live_tiers_cover_bounds():
    assert tier(0)=="NORMAL_OPERATION" and tier(.8)=="EMERGENCY_RESPONSE"
