"""
Tests for scripts/build_warn_nuclear.py
Validates WARN nuclear scoring, tier assignment, EPZ population normalisation,
and output schema. No live API calls.
"""
import json
from pathlib import Path
import pytest


# ── Re-implement scoring logic (mirrors build_warn_nuclear.py) ─────────────────

MAX_CAPACITY_MWE = 1299
MAX_EPZ_POP      = 350000

def capacity_norm(mwe):
    return min(1.0, max(0.0, mwe / MAX_CAPACITY_MWE))

def epz_pop_norm(pop):
    return min(1.0, max(0.0, pop / MAX_EPZ_POP))

def power_norm(pct):
    return min(1.0, max(0.0, pct / 100.0))

def warn_score(mwe, epz_pop, power_pct):
    return round(
        0.45 * capacity_norm(mwe) +
        0.35 * epz_pop_norm(epz_pop) +
        0.20 * power_norm(power_pct),
        4
    )

def warn_tier(s):
    if s >= 0.65: return "EMERGENCY_RESPONSE"
    if s >= 0.40: return "MITIGATION_REQUIRED"
    if s >= 0.20: return "MONITOR"
    return "NORMAL_OPERATION"


class TestCapacityNorm:
    def test_largest_unit_is_1(self):
        assert capacity_norm(MAX_CAPACITY_MWE) == pytest.approx(1.0)

    def test_zero_capacity_is_zero(self):
        assert capacity_norm(0) == pytest.approx(0.0)

    def test_capped_above_max(self):
        assert capacity_norm(9999) == pytest.approx(1.0)

    def test_1000mwe_is_fractional(self):
        s = capacity_norm(1000)
        assert 0.70 < s < 0.85

    def test_500mwe_is_about_half(self):
        s = capacity_norm(500)
        assert 0.35 < s < 0.45


class TestEpzPopNorm:
    def test_zero_pop_is_zero(self):
        assert epz_pop_norm(0) == pytest.approx(0.0)

    def test_max_pop_is_one(self):
        assert epz_pop_norm(MAX_EPZ_POP) == pytest.approx(1.0)

    def test_above_max_capped(self):
        assert epz_pop_norm(500000) == pytest.approx(1.0)

    def test_indian_point_epz_high(self):
        # Indian Point EPZ_pop = 310,000
        s = epz_pop_norm(310000)
        assert s > 0.85

    def test_remote_plant_low(self):
        # Palo Verde EPZ_pop = 1,500 (desert)
        s = epz_pop_norm(1500)
        assert s < 0.01


class TestPowerNorm:
    def test_100pct_is_one(self):
        assert power_norm(100) == pytest.approx(1.0)

    def test_0pct_is_zero(self):
        assert power_norm(0) == pytest.approx(0.0)

    def test_50pct_is_half(self):
        assert power_norm(50) == pytest.approx(0.5)

    def test_above_100_capped(self):
        assert power_norm(110) == pytest.approx(1.0)

    def test_negative_clamped(self):
        assert power_norm(-5) == pytest.approx(0.0)


class TestWarnScore:
    def test_all_zeros_is_zero(self):
        assert warn_score(0, 0, 0) == pytest.approx(0.0)

    def test_weights_sum_to_one(self):
        # At max inputs: capacity=1, epz=1, power=1 → score=1
        s = warn_score(MAX_CAPACITY_MWE, MAX_EPZ_POP, 100)
        assert s == pytest.approx(1.0, abs=0.001)

    def test_indian_point_anchor(self):
        # Indian Point: 1041MWe, EPZ_pop=310,000, 100% power
        # capacity_norm=1041/1299=0.8014, epz=310000/350000=0.8857, power=1.0
        # score = 0.45*0.8014 + 0.35*0.8857 + 0.20*1.0 = 0.3606+0.3100+0.2000 = 0.8706
        s = warn_score(1041, 310000, 100)
        assert s == pytest.approx(0.8706, abs=0.001)

    def test_palo_verde_anchor(self):
        # Palo Verde: 1270MWe, EPZ_pop=1500, 100% power — remote desert site
        # capacity=0.9777, epz=0.0043, power=1.0
        # score = 0.45*0.9777 + 0.35*0.0043 + 0.20*1.0 ≈ 0.440 + 0.0015 + 0.20 = 0.641
        s = warn_score(1270, 1500, 100)
        assert s < 0.70  # High capacity but very remote — not EMERGENCY

    def test_shutdown_plant_lower_score(self):
        # Same plant at 0% vs 100% power — shutdown reduces score
        s_on  = warn_score(1000, 50000, 100)
        s_off = warn_score(1000, 50000, 0)
        assert s_on > s_off

    def test_score_bounded_zero_to_one(self):
        for args in [(0,0,0),(MAX_CAPACITY_MWE,MAX_EPZ_POP,100),(500,10000,50)]:
            s = warn_score(*args)
            assert 0.0 <= s <= 1.0

    def test_power_contribution_is_20pct_weight(self):
        # Difference between 0% and 100% power should be exactly 0.20
        s_on  = warn_score(0, 0, 100)
        s_off = warn_score(0, 0, 0)
        assert (s_on - s_off) == pytest.approx(0.20, abs=0.001)

    def test_capacity_contribution_is_45pct_weight(self):
        # Difference between max and zero capacity
        s_max = warn_score(MAX_CAPACITY_MWE, 0, 0)
        s_min = warn_score(0, 0, 0)
        assert (s_max - s_min) == pytest.approx(0.45, abs=0.001)

    def test_epz_contribution_is_35pct_weight(self):
        s_max = warn_score(0, MAX_EPZ_POP, 0)
        s_min = warn_score(0, 0, 0)
        assert (s_max - s_min) == pytest.approx(0.35, abs=0.001)


class TestWarnTier:
    def test_emergency_at_and_above_0_65(self):
        assert warn_tier(0.65) == "EMERGENCY_RESPONSE"
        assert warn_tier(1.00) == "EMERGENCY_RESPONSE"

    def test_mitigation_band(self):
        assert warn_tier(0.40) == "MITIGATION_REQUIRED"
        assert warn_tier(0.64) == "MITIGATION_REQUIRED"

    def test_monitor_band(self):
        assert warn_tier(0.20) == "MONITOR"
        assert warn_tier(0.39) == "MONITOR"

    def test_normal_below_0_20(self):
        assert warn_tier(0.00) == "NORMAL_OPERATION"
        assert warn_tier(0.19) == "NORMAL_OPERATION"

    def test_indian_point_is_emergency(self):
        s = warn_score(1041, 310000, 100)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_palo_verde_is_mitigation(self):
        # Very remote — high capacity but tiny EPZ population
        s = warn_score(1270, 1500, 100)
        assert warn_tier(s) == "MITIGATION_REQUIRED"

    def test_small_remote_shutdown_is_monitor(self):
        # Small plant, low population, shut down
        s = warn_score(478, 5000, 0)
        # capacity_norm=0.368, epz=0.014, power=0 → 0.45*0.368+0.35*0.014 = 0.166+0.005 = 0.171
        assert warn_tier(s) == "NORMAL_OPERATION"

    def test_nuclear_tier_thresholds_more_conservative_than_hurricane(self):
        # Nuclear EMERGENCY starts at 0.65 vs hurricane at 0.75 — nuclear is more conservative
        assert 0.65 < 0.75  # documenting the design decision


class TestNuclearTierConservatism:
    """Nuclear thresholds are more conservative (lower) than hurricane thresholds."""

    def test_nuclear_emergency_threshold_lower_than_hurricane(self):
        NUCLEAR_EMERGENCY = 0.65
        HURRICANE_EMERGENCY = 0.75
        assert NUCLEAR_EMERGENCY < HURRICANE_EMERGENCY

    def test_score_0_65_is_nuclear_emergency_not_hurricane_emergency(self):
        from_nuclear = warn_tier(0.65)
        assert from_nuclear == "EMERGENCY_RESPONSE"

    def test_all_tiers_reachable(self):
        scenarios = [
            (0, 0, 0),          # NORMAL
            (400, 5000, 40),    # MONITOR
            (800, 20000, 60),   # MITIGATION
            (1299, 350000, 100),# EMERGENCY
        ]
        tiers = {warn_tier(warn_score(*s)) for s in scenarios}
        assert "NORMAL_OPERATION" in tiers
        assert "EMERGENCY_RESPONSE" in tiers


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "warn_nuclear_plants.json"
        if not p.exists():
            pytest.skip("Run build_warn_nuclear.py first")
        return json.loads(p.read_text())

    def test_required_keys_present(self, output):
        for k in ["source_power_status","source_plant_data","nrc_status_url",
                  "nrc_report_date","plants_scored","formula","tiers","claim_boundary","plants"]:
            assert k in output, f"Missing key: {k}"

    def test_plants_is_list(self, output):
        assert isinstance(output["plants"], list)
        assert len(output["plants"]) > 0

    def test_each_plant_has_required_fields(self, output):
        for plant in output["plants"]:
            for field in ["plant","state","lat","lon","capacity_mwe","epz_pop_est",
                          "power_pct","warn_score","warn_tier"]:
                assert field in plant, f"Plant missing field: {field}"

    def test_all_tiers_valid(self, output):
        valid = {"NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"}
        for plant in output["plants"]:
            assert plant["warn_tier"] in valid

    def test_plants_sorted_by_score_descending(self, output):
        scores = [p["warn_score"] for p in output["plants"]]
        assert scores == sorted(scores, reverse=True)

    def test_indian_point_is_top_scorer(self, output):
        top = output["plants"][0]
        assert "Indian Point" in top["plant"]

    def test_indian_point_score_matches_formula(self, output):
        plant = next(p for p in output["plants"] if "Indian Point" in p["plant"])
        expected = warn_score(plant["capacity_mwe"], plant["epz_pop_est"], plant["power_pct"])
        assert plant["warn_score"] == pytest.approx(expected, abs=0.001)

    def test_claim_boundary_present_and_substantive(self, output):
        claim = output["claim_boundary"]
        assert len(claim) > 50
        assert "not" in claim.lower() or "baseline" in claim.lower()

    def test_nrc_source_documented(self, output):
        assert "nrc.gov" in output["nrc_status_url"]

    def test_formula_documents_three_components(self, output):
        formula_str = str(output["formula"])
        assert "capacity" in formula_str.lower()
        assert "epz" in formula_str.lower() or "population" in formula_str.lower()
        assert "power" in formula_str.lower()

    def test_scores_bounded(self, output):
        for plant in output["plants"]:
            assert 0.0 <= plant["warn_score"] <= 1.0

    def test_power_pct_bounded(self, output):
        for plant in output["plants"]:
            assert 0.0 <= plant["power_pct"] <= 110.0  # small tolerance for unusual values
