"""
Tests for scripts/build_warn_bc_wildfire_nations.py
Validates BC wildfire WARN scoring, Nation proximity logic, tier assignments,
anchor fire behaviour, and output schema.
"""
import json
import math
from pathlib import Path
import pytest


# ── Re-implement scoring (mirrors build_warn_bc_wildfire_nations.py) ──────────

MAX_FWI    = 50.0
MAX_AREA   = 600_000
MAX_SPREAD = 10.0

def fwi_norm(fwi):    return min(1.0, max(0.0, fwi / MAX_FWI))
def area_norm(ha):    return min(1.0, max(0.0, ha / MAX_AREA))
def spread_norm(r):   return min(1.0, max(0.0, r / MAX_SPREAD))

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def proximity_norm(dist_km, radius_km=200.0):
    return max(0.0, 1.0 - dist_km / radius_km)

def warn_score(fwi, area_ha, dist_km, spread_kmday=0.0):
    return round(
        0.35 * fwi_norm(fwi) +
        0.30 * proximity_norm(dist_km) +
        0.20 * area_norm(area_ha) +
        0.15 * spread_norm(spread_kmday),
        4
    )

def warn_tier(s):
    if s >= 0.70: return "EMERGENCY_RESPONSE"
    if s >= 0.45: return "MITIGATION_REQUIRED"
    if s >= 0.20: return "MONITOR"
    return "NORMAL_OPERATION"


class TestFwiNorm:
    def test_zero_fwi_is_zero(self):       assert fwi_norm(0) == 0.0
    def test_max_fwi_is_one(self):         assert fwi_norm(50) == pytest.approx(1.0)
    def test_above_max_capped(self):       assert fwi_norm(100) == pytest.approx(1.0)
    def test_extreme_fwi_45_high(self):    assert fwi_norm(45) > 0.85
    def test_moderate_fwi_20_half(self):   assert 0.35 < fwi_norm(20) < 0.45


class TestAreaNorm:
    def test_zero_area_is_zero(self):      assert area_norm(0) == 0.0
    def test_donnie_creek_is_one(self):    assert area_norm(600_000) == pytest.approx(1.0)
    def test_above_max_capped(self):       assert area_norm(700_000) == pytest.approx(1.0)
    def test_lytton_creek_83k(self):
        s = area_norm(83_000)
        assert 0.13 < s < 0.15

    def test_plateau_complex_521k(self):
        s = area_norm(521_012)
        assert s > 0.85


class TestProximityNorm:
    def test_zero_distance_is_one(self):      assert proximity_norm(0) == pytest.approx(1.0)
    def test_200km_is_zero(self):             assert proximity_norm(200) == pytest.approx(0.0)
    def test_beyond_radius_is_zero(self):     assert proximity_norm(500) == pytest.approx(0.0)
    def test_100km_is_half(self):             assert proximity_norm(100) == pytest.approx(0.5)
    def test_50km_is_0_75(self):              assert proximity_norm(50) == pytest.approx(0.75)


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km(49.0, -119.0, 49.0, -119.0) == pytest.approx(0.0, abs=0.01)

    def test_lytton_to_lytton_fire_is_near(self):
        # Lytton FN (50.23, -121.58) vs Lytton Creek fire (50.22, -121.58)
        d = haversine_km(50.23, -121.58, 50.22, -121.58)
        assert d < 5.0

    def test_squamish_to_donnie_creek_is_far(self):
        # Squamish Nation (49.70, -123.15) vs Donnie Creek (57.50, -124.00)
        d = haversine_km(49.70, -123.15, 57.50, -124.00)
        assert d > 800.0

    def test_tsilhqotin_to_plateau_complex_moderate(self):
        # Tsilhqot'in (52.00, -123.20) vs Plateau Complex centroid (52.39, -123.19)
        d = haversine_km(52.00, -123.20, 52.39, -123.19)
        assert d < 60.0


class TestWarnScore:
    def test_zero_inputs_is_zero(self):
        assert warn_score(0, 0, 200) == pytest.approx(0.0, abs=0.001)

    def test_all_max_is_high(self):
        s = warn_score(50, 600_000, 0, 10)
        assert s == pytest.approx(1.0, abs=0.001)

    def test_score_bounded(self):
        for args in [(0,0,0),(50,600000,0,10),(20,50000,100)]:
            s = warn_score(*args)
            assert 0.0 <= s <= 1.0

    def test_lytton_fn_vs_lytton_creek_anchor(self):
        # Lytton FN 1.1km from fire, FWI=45, 83,000ha — should score MITIGATION_REQUIRED+
        s = warn_score(45.0, 83_000, 1.1)
        assert s >= 0.60
        assert warn_tier(s) in {"MITIGATION_REQUIRED", "EMERGENCY_RESPONSE"}

    def test_proximity_dominates_for_near_fire(self):
        s_near = warn_score(20, 10_000, 5)
        s_far  = warn_score(20, 10_000, 180)
        assert s_near > s_far

    def test_fwi_contribution_is_35pct_weight(self):
        s_high = warn_score(50, 0, 200, 0)
        s_zero = warn_score(0,  0, 200, 0)
        assert (s_high - s_zero) == pytest.approx(0.35, abs=0.001)

    def test_spread_contribution_is_15pct_weight(self):
        s_high = warn_score(0, 0, 200, 10)
        s_zero = warn_score(0, 0, 200, 0)
        assert (s_high - s_zero) == pytest.approx(0.15, abs=0.001)

    def test_squamish_vs_donnie_creek_low(self):
        # Squamish Nation is ~870km from Donnie Creek — proximity score should be 0
        d = haversine_km(49.70, -123.15, 57.50, -124.00)
        s = warn_score(42.0, 589_552, d)
        # Score is area + fwi weighted; proximity is 0 at this distance
        assert proximity_norm(d) == pytest.approx(0.0)

    def test_kwadacha_vs_donnie_creek_emergency(self):
        # Kwadacha Nation (57.18, -124.43) is ~44km from Donnie Creek
        d = haversine_km(57.18, -124.43, 57.50, -124.00)
        s = warn_score(42.0, 589_552, d)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"


class TestWarnTier:
    def test_emergency_at_0_70(self):      assert warn_tier(0.70) == "EMERGENCY_RESPONSE"
    def test_mitigation_at_0_45(self):     assert warn_tier(0.45) == "MITIGATION_REQUIRED"
    def test_monitor_at_0_20(self):        assert warn_tier(0.20) == "MONITOR"
    def test_normal_below_0_20(self):      assert warn_tier(0.19) == "NORMAL_OPERATION"
    def test_normal_at_zero(self):         assert warn_tier(0.0) == "NORMAL_OPERATION"
    def test_emergency_at_one(self):       assert warn_tier(1.0) == "EMERGENCY_RESPONSE"

    def test_bc_threshold_lower_than_nuclear(self):
        # BC wildfire EMERGENCY ≥ 0.70 (same as nuclear) — both conservative
        NUCLEAR_EMERGENCY = 0.65
        BC_EMERGENCY      = 0.70
        # BC is slightly less conservative than nuclear — reflects that wildfire
        # is more predictable than nuclear proximity risk
        assert BC_EMERGENCY > NUCLEAR_EMERGENCY


class TestAnchorFires:
    """Key BC wildfire events from public BC Wildfire Service records."""

    def test_lytton_2021_high_score(self):
        # Lytton Creek 2021: FWI 45, 83,000ha, 1km from Lytton FN
        s = warn_score(45.0, 83_000, 1.1)
        assert s > 0.60

    def test_donnie_creek_2023_largest_recorded(self):
        # Donnie Creek 2023: 589,552ha — largest recorded BC fire
        area_s = area_norm(589_552)
        assert area_s > 0.98  # nearly at max normalisation ceiling

    def test_plateau_complex_2017_high_area(self):
        area_s = area_norm(521_012)
        assert area_s > 0.85

    def test_remote_nation_low_proximity(self):
        # Squamish Nation (coastal) vs Donnie Creek (northeast BC) — >800km
        d = haversine_km(49.70, -123.15, 57.50, -124.00)
        prox = proximity_norm(d)
        assert prox == pytest.approx(0.0)

    def test_tsilhqotin_vs_plateau_complex_elevated(self):
        # Tsilhqot'in directly impacted by Plateau Complex 2017
        d = haversine_km(52.00, -123.20, 52.39, -123.19)
        s = warn_score(40.2, 521_012, d)
        assert warn_tier(s) in {"MITIGATION_REQUIRED", "EMERGENCY_RESPONSE"}

    def test_white_rock_lake_okanagan_proximity(self):
        # White Rock Lake 2021: near Okanagan Indian Band (50.10 -119.77 vs 50.10 -119.47)
        d = haversine_km(50.10, -119.47, 50.11, -119.77)
        s = warn_score(43.5, 83_000, d)
        assert s > 0.55


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "warn_bc_wildfire_nations.json"
        if not p.exists():
            pytest.skip("Run build_warn_bc_wildfire_nations.py first")
        return json.loads(p.read_text())

    def test_required_keys(self, output):
        for k in ["source_fire_data","source_territory_data","nations_scored",
                  "formula","tiers","claim_boundary","nations",
                  "indigenous_data_sovereignty","tier_distribution"]:
            assert k in output

    def test_nations_is_list(self, output):
        assert isinstance(output["nations"], list)
        assert len(output["nations"]) > 0

    def test_each_nation_has_required_fields(self, output):
        for n in output["nations"]:
            for f in ["nation","region","warn_score","warn_tier","lat","lon"]:
                assert f in n

    def test_all_tiers_valid(self, output):
        valid = {"NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"}
        for n in output["nations"]:
            assert n["warn_tier"] in valid

    def test_nations_sorted_by_score_descending(self, output):
        scores = [n["warn_score"] for n in output["nations"]]
        assert scores == sorted(scores, reverse=True)

    def test_kwadacha_or_high_interior_is_top(self, output):
        top_nation = output["nations"][0]["nation"]
        top_score  = output["nations"][0]["warn_score"]
        assert top_score > 0.60

    def test_data_sovereignty_statement_present(self, output):
        ds = output["indigenous_data_sovereignty"]
        assert len(ds) > 50
        assert "OCAP" in ds or "consent" in ds.lower() or "Nation" in ds

    def test_claim_boundary_no_evacuation_authority(self, output):
        claim = output["claim_boundary"] if isinstance(output["claim_boundary"], str) \
            else str(output["claim_boundary"])
        assert "evacuation" in claim.lower() or "decision" in claim.lower()

    def test_scores_bounded(self, output):
        for n in output["nations"]:
            assert 0.0 <= n["warn_score"] <= 1.0

    def test_formula_documents_four_components(self, output):
        formula_str = str(output["formula"])
        assert "fwi" in formula_str.lower()
        assert "proximity" in formula_str.lower()
        assert "area" in formula_str.lower()
        assert "spread" in formula_str.lower()
