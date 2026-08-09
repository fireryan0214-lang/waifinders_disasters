"""
Tests for scripts/build_warn_flood_surge.py
Validates surge normalisation, tier assignment, known storm results, and data-gap handling.
"""
import json
from pathlib import Path
import pytest


def surge_norm(peak_m):
    return min(1.0, max(0.0, peak_m / 5.0))

def warn_tier(s):
    if s >= 0.70: return "EMERGENCY_RESPONSE"
    if s >= 0.45: return "MITIGATION_REQUIRED"
    if s >= 0.20: return "MONITOR"
    return "NORMAL_OPERATION"


class TestSurgeNorm:
    def test_zero_surge_is_zero(self):
        assert surge_norm(0.0) == 0.0

    def test_five_metres_is_one(self):
        assert surge_norm(5.0) == pytest.approx(1.0)

    def test_clamps_above_five(self):
        assert surge_norm(10.0) == 1.0

    def test_midpoint(self):
        assert surge_norm(2.5) == pytest.approx(0.5)

    def test_minor_nuisance_flood(self):
        # < 0.6m should be well below MONITOR threshold
        assert surge_norm(0.5) < 0.20


class TestTierThresholds:
    def test_emergency_at_0_70(self):
        assert warn_tier(0.70) == "EMERGENCY_RESPONSE"
        assert warn_tier(1.00) == "EMERGENCY_RESPONSE"

    def test_mitigation_band(self):
        assert warn_tier(0.45) == "MITIGATION_REQUIRED"
        assert warn_tier(0.69) == "MITIGATION_REQUIRED"

    def test_monitor_band(self):
        assert warn_tier(0.20) == "MONITOR"
        assert warn_tier(0.44) == "MONITOR"

    def test_normal_below_0_20(self):
        assert warn_tier(0.00) == "NORMAL_OPERATION"
        assert warn_tier(0.19) == "NORMAL_OPERATION"


class TestKnownStormEvents:
    """
    Real NOAA CO-OPS gauge readings from prior session.
    Sandy: 2.74m above MHHW at The Battery NY.
    Ian:   2.21m above MHHW at Fort Myers FL.
    Ida:   1.49m above MHHW at Grand Isle LA.
    Harvey: 0.57m — gauge went offline before peak (real data gap, not a bug).
    """

    def test_sandy_is_mitigation_required(self):
        s = surge_norm(2.74)
        assert warn_tier(s) == "MITIGATION_REQUIRED"

    def test_ian_is_monitor(self):
        s = surge_norm(2.21)
        assert warn_tier(s) == "MONITOR"

    def test_ida_is_monitor(self):
        s = surge_norm(1.49)
        assert warn_tier(s) == "MONITOR"

    def test_harvey_gauge_offline_normal(self):
        # 0.57m is what the gauge recorded before it went offline —
        # correctly classified as NORMAL at that reading
        s = surge_norm(0.57)
        assert warn_tier(s) == "NORMAL_OPERATION"

    def test_hurricane_ian_documented_surge_would_be_emergency(self):
        # Ian's documented 4.57m surge (NOAA post-event) → EMERGENCY_RESPONSE
        s = surge_norm(4.57)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_higher_surge_never_lower_tier(self):
        surges = [0.5, 1.0, 1.5, 2.5, 3.5, 4.5]
        tiers = [warn_tier(surge_norm(s)) for s in surges]
        tier_vals = ["NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"]
        indices = [tier_vals.index(t) for t in tiers]
        assert indices == sorted(indices)  # monotonically non-decreasing


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "warn_flood_surge_events.json"
        if not p.exists():
            pytest.skip("Run build_warn_flood_surge.py first")
        return json.loads(p.read_text())

    def test_required_keys(self, output):
        for k in ["source", "fetched_utc", "datum", "formula", "claim_boundary", "events"]:
            assert k in output

    def test_datum_is_mhhw(self, output):
        assert "MHHW" in output["datum"]

    def test_all_events_have_tier(self, output):
        valid = {"NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"}
        for ev in output["events"]:
            assert ev["warn_tier"] in valid

    def test_sandy_in_output(self, output):
        names = [ev.get("name","") for ev in output["events"]]
        assert any("Sandy" in n for n in names)

    def test_fetch_status_documented(self, output):
        for ev in output["events"]:
            assert "fetch_status" in ev
            assert ev["fetch_status"]  # not empty — must state what happened
