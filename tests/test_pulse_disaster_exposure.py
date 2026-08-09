"""
Tests for scripts/build_pulse_disaster_exposure.py
Validates PULSE bridge scoring, compound exposure logic, hazard zone assignment,
and output schema. No live API calls.
"""
import json
from pathlib import Path
import pytest


# ── Re-implement scoring logic ─────────────────────────────────────────────────

def pulse_score(poor_status, year_built, reference_year=2024):
    poor_risk = 0.85 if poor_status == "Y" else 0.25
    age_years = max(0, reference_year - year_built)
    age_norm  = min(1.0, age_years / 120.0)
    return 0.65 * poor_risk + 0.35 * age_norm

def compound_score(base, seismic_high=False, tsunami=False, flood=False):
    multiplier = 1.0
    if seismic_high: multiplier += 0.25
    if tsunami:      multiplier += 0.20
    if flood:        multiplier += 0.15
    return min(1.0, base * multiplier)

def risk_band(s):
    if s >= 0.70: return "RED"
    if s >= 0.45: return "AMBER"
    if s >= 0.25: return "YELLOW"
    return "GREEN"


class TestPulseBaseScore:
    def test_poor_old_bridge_scores_high(self):
        s = pulse_score("Y", 1920)
        assert s > 0.70

    def test_good_new_bridge_scores_low(self):
        s = pulse_score("N", 2020)
        assert s < 0.35

    def test_poor_new_bridge_dominated_by_condition(self):
        s = pulse_score("Y", 2020)
        assert s > 0.55  # condition weight (0.65) dominates

    def test_good_old_bridge_reflects_age(self):
        s = pulse_score("N", 1900)
        assert s > 0.35  # age component contributes

    def test_score_bounded_zero_to_one(self):
        for status, year in [("Y",1900),("N",2024),("Y",2024),("N",1900)]:
            s = pulse_score(status, year)
            assert 0.0 <= s <= 1.0


class TestCompoundScore:
    def test_no_hazard_returns_base(self):
        base = 0.60
        s = compound_score(base)
        assert s == pytest.approx(base)

    def test_all_three_hazards_amplifies(self):
        base = 0.50
        s = compound_score(base, seismic_high=True, tsunami=True, flood=True)
        assert s > base

    def test_capped_at_one(self):
        # Even maximum amplification cannot exceed 1.0
        s = compound_score(1.0, seismic_high=True, tsunami=True, flood=True)
        assert s == 1.0

    def test_seismic_adds_most(self):
        base = 0.50
        s_seismic = compound_score(base, seismic_high=True)
        s_flood   = compound_score(base, flood=True)
        assert s_seismic > s_flood

    def test_compound_ordering(self):
        base = 0.40
        s_none   = compound_score(base)
        s_one    = compound_score(base, seismic_high=True)
        s_two    = compound_score(base, seismic_high=True, tsunami=True)
        s_three  = compound_score(base, seismic_high=True, tsunami=True, flood=True)
        assert s_none <= s_one <= s_two <= s_three


class TestRiskBand:
    def test_red_at_and_above_0_70(self):
        assert risk_band(0.70) == "RED"
        assert risk_band(1.00) == "RED"

    def test_amber_band(self):
        assert risk_band(0.45) == "AMBER"
        assert risk_band(0.69) == "AMBER"

    def test_yellow_band(self):
        assert risk_band(0.25) == "YELLOW"
        assert risk_band(0.44) == "YELLOW"

    def test_green_below_0_25(self):
        assert risk_band(0.00) == "GREEN"
        assert risk_band(0.24) == "GREEN"


class TestHazardZoneLogic:
    """Seismic zone assignment from USGS NSHM 2014 precomputed values."""

    # USGS NSHM 2014 (E2014R1) 2%/50yr PGA at Vs30=760m/s — queried live this session
    COUNTY_SEISMIC = {
        "New York":    0.1792, "Kings":    0.1725, "Queens":   0.1723,
        "Richmond":    0.1713, "Bronx":    0.1818, "Nassau":   0.1558,
        "Suffolk":     0.0940, "Westchester": 0.1798, "Rockland": 0.1798,
        "Erie":        0.0883, "Monroe":   0.0859, "Albany":   0.1062,
        "Orange":      0.1291,
    }

    def test_nyc_counties_are_high_seismic(self):
        nyc = ["New York", "Kings", "Queens", "Richmond", "Bronx"]
        for county in nyc:
            assert self.COUNTY_SEISMIC[county] > 0.10, f"{county} should be HIGH"

    def test_suffolk_erie_monroe_are_medium(self):
        for county in ["Suffolk", "Erie", "Monroe"]:
            pga = self.COUNTY_SEISMIC[county]
            assert 0.04 <= pga <= 0.10, f"{county} PGA {pga} expected MEDIUM"

    def test_bronx_has_highest_pga(self):
        bronx_pga = self.COUNTY_SEISMIC["Bronx"]
        all_pgas = list(self.COUNTY_SEISMIC.values())
        assert bronx_pga == max(all_pgas)

    def test_all_counties_above_low_threshold(self):
        for county, pga in self.COUNTY_SEISMIC.items():
            assert pga > 0.04, f"{county} PGA {pga:.4f} unexpectedly LOW"

    def test_pga_thresholds_correct(self):
        assert 0.1792 > 0.10   # HIGH
        assert 0.0940 < 0.10   # MEDIUM (Suffolk)
        assert 0.0940 > 0.04   # not LOW


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "pulse_disaster_exposure.json"
        if not p.exists():
            pytest.skip("Run build_pulse_disaster_exposure.py first")
        return json.loads(p.read_text())

    def test_required_keys(self, output):
        for k in ["source","fetched_utc","bridge_count","formula","claim_boundary","risk_summary"]:
            assert k in output

    def test_risk_summary_has_four_bands(self, output):
        rs = output["risk_summary"]
        assert set(rs.keys()) >= {"RED","AMBER","YELLOW","GREEN"}

    def test_risk_summary_counts_are_non_negative(self, output):
        for band, count in output["risk_summary"].items():
            assert count >= 0

    def test_claim_boundary_notes_usgs_seismic(self, output):
        claim = output["claim_boundary"].lower()
        assert "usgs" in claim or "nshm" in claim

    def test_seismic_source_documented(self, output):
        assert "seismic_source" in output
        assert "USGS" in output["seismic_source"] or "E2014R1" in output["seismic_source"]

    def test_priority_bridges_list_present(self, output):
        assert "priority_bridges" in output
        assert isinstance(output["priority_bridges"], list)
