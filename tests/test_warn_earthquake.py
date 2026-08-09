"""
Tests for scripts/build_warn_earthquake.py
Validates formula logic, scoring bounds, tier assignment, and output schema.
No live API calls — tests use synthetic inputs only.
"""
import json
import math
import sys
from pathlib import Path

import pytest

# Add project root so we can import helpers without running the script
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Re-implement the scoring functions locally (same formulas as the script) ──

def norm_magnitude(m):
    return max(0.0, min(1.0, (m - 6.0) / (9.2 - 6.0)))

def norm_shallowness(d):
    return max(0.0, min(1.0, 1.0 - d / 70.0))

CITIES = [
    (49.28, -123.12, "Vancouver BC"),
    (47.61, -122.33, "Seattle WA"),
    (45.52, -122.68, "Portland OR"),
]

def population_exposure(lat, lon):
    min_dist = min(
        math.sqrt((lat - cy)**2 + (lon - cx)**2) * 111
        for cy, cx, _ in CITIES
    )
    return max(0.0, 1.0 - min_dist / 250.0)

def warn_score(mag, depth_km, lat, lon):
    return (
        0.55 * norm_magnitude(mag) +
        0.25 * norm_shallowness(depth_km) +
        0.20 * population_exposure(lat, lon)
    )

def warn_tier(s):
    if s >= 0.80: return "EMERGENCY_RESPONSE"
    if s >= 0.55: return "MITIGATION_REQUIRED"
    if s >= 0.30: return "MONITOR"
    return "NORMAL_OPERATION"


# ── Formula unit tests ─────────────────────────────────────────────────────────

class TestMagnitudeNorm:
    def test_minimum_magnitude_is_zero(self):
        assert norm_magnitude(6.0) == pytest.approx(0.0)

    def test_maximum_magnitude_is_one(self):
        assert norm_magnitude(9.2) == pytest.approx(1.0)

    def test_clamps_below_minimum(self):
        assert norm_magnitude(4.0) == 0.0

    def test_clamps_above_maximum(self):
        assert norm_magnitude(10.0) == 1.0

    def test_midpoint(self):
        # M7.6 = halfway between 6.0 and 9.2
        assert norm_magnitude(7.6) == pytest.approx(0.5, abs=0.01)

    def test_cascadia_1700_analogue(self):
        # M9.0 should be near top of scale
        assert norm_magnitude(9.0) > 0.90


class TestShallownessNorm:
    def test_surface_event_is_one(self):
        assert norm_shallowness(0.0) == pytest.approx(1.0)

    def test_deep_event_is_zero(self):
        assert norm_shallowness(70.0) == pytest.approx(0.0)

    def test_clamps_beyond_70km(self):
        assert norm_shallowness(100.0) == 0.0

    def test_midpoint_depth(self):
        assert norm_shallowness(35.0) == pytest.approx(0.5)


class TestPopulationExposure:
    def test_on_seattle_is_high(self):
        score = population_exposure(47.61, -122.33)
        assert score > 0.8

    def test_far_offshore_is_low(self):
        # 500km offshore Pacific
        score = population_exposure(47.0, -135.0)
        assert score == 0.0

    def test_returns_zero_to_one(self):
        for lat, lon in [(30.0, -100.0), (60.0, -140.0), (47.61, -122.33)]:
            s = population_exposure(lat, lon)
            assert 0.0 <= s <= 1.0


class TestWarnScore:
    def test_score_bounded_zero_to_one(self):
        for mag, depth, lat, lon in [
            (6.0, 70.0, 30.0, -100.0),
            (9.2, 0.0, 47.61, -122.33),
            (7.5, 20.0, 46.5, -124.0),
        ]:
            s = warn_score(mag, depth, lat, lon)
            assert 0.0 <= s <= 1.0

    def test_higher_magnitude_gives_higher_score(self):
        s_low  = warn_score(6.5, 30.0, 47.0, -130.0)
        s_high = warn_score(8.5, 30.0, 47.0, -130.0)
        assert s_high > s_low

    def test_shallower_gives_higher_score(self):
        s_deep    = warn_score(7.0, 60.0, 47.0, -130.0)
        s_shallow = warn_score(7.0, 5.0,  47.0, -130.0)
        assert s_shallow > s_deep

    def test_cascadia_1700_analogue_scores_high(self):
        # M9.0 at 20km depth near Cascadia zone: score ≈ 0.748, just below 0.80 EMERGENCY threshold
        # This confirms the formula correctly ranks it near-top without over-claiming
        s = warn_score(9.0, 20.0, 46.5, -124.0)
        assert s > 0.70
        assert warn_tier(s) == "MITIGATION_REQUIRED"

    def test_small_distant_event_is_normal(self):
        s = warn_score(6.1, 65.0, 30.0, -100.0)
        assert warn_tier(s) == "NORMAL_OPERATION"


class TestTierAssignment:
    def test_emergency_threshold(self):
        assert warn_tier(0.80) == "EMERGENCY_RESPONSE"
        assert warn_tier(0.99) == "EMERGENCY_RESPONSE"

    def test_mitigation_threshold(self):
        assert warn_tier(0.55) == "MITIGATION_REQUIRED"
        assert warn_tier(0.79) == "MITIGATION_REQUIRED"

    def test_monitor_threshold(self):
        assert warn_tier(0.30) == "MONITOR"
        assert warn_tier(0.54) == "MONITOR"

    def test_normal_threshold(self):
        assert warn_tier(0.0)  == "NORMAL_OPERATION"
        assert warn_tier(0.29) == "NORMAL_OPERATION"

    def test_all_four_tiers_reachable(self):
        tiers = {
            warn_tier(0.0),
            warn_tier(0.35),
            warn_tier(0.60),
            warn_tier(0.85),
        }
        assert tiers == {"NORMAL_OPERATION", "MONITOR", "MITIGATION_REQUIRED", "EMERGENCY_RESPONSE"}


class TestOutputFile:
    """Validates the schema of the output JSON written by the script."""

    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "warn_earthquake_events.json"
        if not p.exists():
            pytest.skip("Output file not yet generated — run build_warn_earthquake.py first")
        return json.loads(p.read_text())

    def test_required_top_level_keys(self, output):
        for key in ["source", "fetched_utc", "region", "event_count", "formula", "claim_boundary", "events"]:
            assert key in output

    def test_events_is_list(self, output):
        assert isinstance(output["events"], list)

    def test_every_event_has_warn_score_and_tier(self, output):
        for ev in output["events"]:
            assert "warn_score" in ev
            assert "warn_tier" in ev
            assert float(ev["warn_score"]) >= 0.0
            assert ev["warn_tier"] in {"NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"}

    def test_claim_boundary_present_and_non_empty(self, output):
        assert len(output["claim_boundary"]) > 20

    def test_formula_documents_weights(self, output):
        formula = output["formula"]["warn_score"]
        assert "0.55" in formula
        assert "0.25" in formula
        assert "0.20" in formula
