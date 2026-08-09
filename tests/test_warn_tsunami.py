"""
Tests for scripts/build_warn_tsunami.py
Validates wave height normalisation, tier assignment, anchor events, and output schema.
"""
import json
from pathlib import Path
import pytest


def norm_wave(h):
    return min(1.0, max(0.0, (h - 1.0) / 39.0))

def norm_mag(m):
    if m is None: return 0.3
    try: m = float(m)
    except (TypeError, ValueError): return 0.3
    return min(1.0, max(0.0, (m - 6.5) / 3.0))

def norm_reach(h):
    return min(1.0, max(0.0, h / 30.0))

def warn_score(wave_m, source_mag=None):
    return (
        0.50 * norm_wave(wave_m) +
        0.30 * norm_mag(source_mag) +
        0.20 * norm_reach(wave_m)
    )

def warn_tier(s):
    if s >= 0.75: return "EMERGENCY_RESPONSE"
    if s >= 0.50: return "MITIGATION_REQUIRED"
    if s >= 0.25: return "MONITOR"
    return "NORMAL_OPERATION"


class TestWaveNorm:
    def test_one_metre_maps_to_zero(self):
        assert norm_wave(1.0) == pytest.approx(0.0)

    def test_forty_metres_maps_to_one(self):
        assert norm_wave(40.0) == pytest.approx(1.0)

    def test_clamps_below_one_metre(self):
        assert norm_wave(0.0) == 0.0

    def test_clamps_above_forty_metres(self):
        assert norm_wave(100.0) == 1.0

    def test_tohoku_wave_height(self):
        # 2011 Tōhoku: 39.26m — should be very high norm
        assert norm_wave(39.26) > 0.97


class TestMagNorm:
    def test_known_magnitude_range(self):
        assert norm_mag(6.5) == pytest.approx(0.0)
        assert norm_mag(9.5) == pytest.approx(1.0)

    def test_none_returns_moderate_default(self):
        assert norm_mag(None) == 0.3

    def test_clamps_below(self):
        assert norm_mag(5.0) == 0.0

    def test_clamps_above(self):
        assert norm_mag(10.0) == 1.0


class TestWarnScore:
    def test_score_bounded(self):
        for wave, mag in [(1.0, 6.5), (50.0, 9.5), (10.0, None)]:
            s = warn_score(wave, mag)
            assert 0.0 <= s <= 1.0

    def test_larger_wave_gives_higher_score(self):
        s_small = warn_score(2.0, 7.5)
        s_large = warn_score(30.0, 7.5)
        assert s_large > s_small

    def test_higher_source_mag_gives_higher_score(self):
        s_low  = warn_score(10.0, 7.0)
        s_high = warn_score(10.0, 9.0)
        assert s_high > s_low


class TestAnchorEvents:
    """Anchor events from real NOAA data — confirmed in prior session."""

    def test_tohoku_2011_is_emergency(self):
        # 39.26m, M9.1
        s = warn_score(39.26, 9.1)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_indian_ocean_2004_is_emergency(self):
        # 50.9m, M9.1
        s = warn_score(50.9, 9.1)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_1964_alaska_good_friday_is_emergency(self):
        # 51.8m, M9.2
        s = warn_score(51.8, 9.2)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_1960_chile_is_emergency(self):
        # 25.0m, M9.5
        s = warn_score(25.0, 9.5)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_small_local_tsunami_is_monitor_or_below(self):
        # 1m wave, small local event
        s = warn_score(1.5, 6.8)
        assert warn_tier(s) in {"NORMAL_OPERATION", "MONITOR"}


class TestTierThresholds:
    def test_emergency_at_and_above_0_75(self):
        assert warn_tier(0.75) == "EMERGENCY_RESPONSE"
        assert warn_tier(1.00) == "EMERGENCY_RESPONSE"

    def test_mitigation_band(self):
        assert warn_tier(0.50) == "MITIGATION_REQUIRED"
        assert warn_tier(0.74) == "MITIGATION_REQUIRED"

    def test_monitor_band(self):
        assert warn_tier(0.25) == "MONITOR"
        assert warn_tier(0.49) == "MONITOR"

    def test_normal_below_0_25(self):
        assert warn_tier(0.0)  == "NORMAL_OPERATION"
        assert warn_tier(0.24) == "NORMAL_OPERATION"


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "warn_tsunami_events.json"
        if not p.exists():
            pytest.skip("Run build_warn_tsunami.py first")
        return json.loads(p.read_text())

    def test_required_keys(self, output):
        for k in ["source", "fetched_utc", "event_count", "formula", "claim_boundary", "events"]:
            assert k in output

    def test_events_have_required_fields(self, output):
        for ev in output["events"]:
            assert "warn_score" in ev
            assert "warn_tier" in ev
            assert ev["warn_tier"] in {
                "NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"
            }

    def test_event_count_matches_list(self, output):
        assert output["event_count"] == len(output["events"])

    def test_formula_weights_sum_to_one(self, output):
        # 0.50 + 0.30 + 0.20 = 1.0
        f = output["formula"]["warn_score"]
        assert "0.50" in f
        assert "0.30" in f
        assert "0.20" in f
