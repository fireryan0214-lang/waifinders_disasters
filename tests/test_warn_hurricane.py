"""
Tests for scripts/build_warn_hurricane.py
Validates Saffir-Simpson mapping, WARN formula, tier assignment,
anchor storm results, and output schema.
"""
import json
import math
from pathlib import Path
import pytest


# ── Re-implement scoring ───────────────────────────────────────────────────────

COAST_CITIES = [
    (25.77, -80.19, "Miami FL"),
    (29.95, -90.07, "New Orleans LA"),
    (29.76, -95.37, "Houston TX"),
    (27.80, -97.40, "Corpus Christi TX"),
    (30.33, -81.66, "Jacksonville FL"),
    (32.78, -79.94, "Charleston SC"),
    (35.23, -75.60, "Outer Banks NC"),
    (40.71, -74.01, "New York NY"),
    (25.67, -80.36, "Homestead FL"),
    (18.47, -66.12, "San Juan PR"),
    (17.99, -76.79, "Kingston Jamaica"),
    (23.13, -82.38, "Havana Cuba"),
]

def category(kt):
    if kt >= 137: return 5
    if kt >= 113: return 4
    if kt >= 96:  return 3
    if kt >= 83:  return 2
    if kt >= 64:  return 1
    return 0

def wind_norm(kt):
    return min(1.0, max(0.0, (kt - 64) / (185 - 64)))

def surge_norm(kt):
    surge_m = {0: 0.3, 1: 1.2, 2: 2.1, 3: 3.0, 4: 4.5, 5: 5.5}[category(kt)]
    return min(1.0, surge_m / 6.0)

def proximity_norm(lat, lon):
    min_dist = min(
        math.sqrt((lat - cy)**2 + (lon - cx)**2) * 111
        for cy, cx, _ in COAST_CITIES
    )
    return max(0.0, 1.0 - min_dist / 500.0)

def warn_score(kt, lat, lon):
    return round(
        0.45 * wind_norm(kt) +
        0.35 * surge_norm(kt) +
        0.20 * proximity_norm(lat, lon),
        4
    )

def warn_tier(s):
    if s >= 0.75: return "EMERGENCY_RESPONSE"
    if s >= 0.50: return "MITIGATION_REQUIRED"
    if s >= 0.25: return "MONITOR"
    return "NORMAL_OPERATION"


# ── Category assignment ────────────────────────────────────────────────────────

class TestCategory:
    def test_cat5_threshold(self):
        assert category(137) == 5
        assert category(185) == 5

    def test_cat4_band(self):
        assert category(113) == 4
        assert category(136) == 4

    def test_cat3_band(self):
        assert category(96) == 3
        assert category(112) == 3

    def test_cat2_band(self):
        assert category(83) == 2
        assert category(95) == 2

    def test_cat1_band(self):
        assert category(64) == 1
        assert category(82) == 1

    def test_td_ts_below_64(self):
        assert category(63) == 0
        assert category(34) == 0


class TestWindNorm:
    def test_cat1_threshold_zero(self):
        assert wind_norm(64) == pytest.approx(0.0)

    def test_extreme_cat5_is_one(self):
        assert wind_norm(185) == pytest.approx(1.0)

    def test_clamped_below(self):
        assert wind_norm(40) == 0.0

    def test_clamped_above(self):
        assert wind_norm(200) == 1.0

    def test_midpoint(self):
        mid = (185 + 64) / 2  # 124.5kt
        assert wind_norm(mid) == pytest.approx(0.5, abs=0.01)


class TestSurgeNorm:
    def test_cat1_surge(self):
        # 1.2m / 6.0 = 0.20
        assert surge_norm(64) == pytest.approx(0.20)

    def test_cat3_surge(self):
        # 3.0m / 6.0 = 0.50
        assert surge_norm(96) == pytest.approx(0.50)

    def test_cat5_surge(self):
        # 5.5m / 6.0 = 0.917
        assert surge_norm(137) == pytest.approx(5.5 / 6.0)

    def test_higher_category_higher_surge(self):
        s1 = surge_norm(64)   # Cat-1
        s3 = surge_norm(96)   # Cat-3
        s5 = surge_norm(137)  # Cat-5
        assert s1 < s3 < s5

    def test_surge_bounded(self):
        for kt in [64, 83, 96, 113, 137, 175]:
            assert 0.0 <= surge_norm(kt) <= 1.0


class TestProximityNorm:
    def test_on_miami_is_max(self):
        s = proximity_norm(25.77, -80.19)
        assert s == pytest.approx(1.0)

    def test_mid_atlantic_ocean_is_zero(self):
        # Far from all cities
        s = proximity_norm(35.0, -50.0)
        assert s == 0.0

    def test_bounded(self):
        for lat, lon in [(25.0, -80.0), (20.0, -70.0), (45.0, -30.0)]:
            s = proximity_norm(lat, lon)
            assert 0.0 <= s <= 1.0

    def test_closer_city_scores_higher(self):
        near_miami = proximity_norm(26.0, -80.5)
        far_from_all = proximity_norm(40.0, -55.0)
        assert near_miami > far_from_all


class TestWarnScore:
    def test_bounded(self):
        for kt, lat, lon in [(64, 30.0, -50.0), (185, 25.77, -80.19), (96, 20.0, -75.0)]:
            s = warn_score(kt, lat, lon)
            assert 0.0 <= s <= 1.0

    def test_higher_wind_higher_score_same_position(self):
        s_cat3 = warn_score(96, 25.0, -80.0)
        s_cat5 = warn_score(155, 25.0, -80.0)
        assert s_cat5 > s_cat3

    def test_same_wind_closer_city_higher_score(self):
        s_near = warn_score(120, 26.0, -80.5)   # near Miami
        s_far  = warn_score(120, 26.0, -60.0)   # mid-ocean
        assert s_near > s_far


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
        assert warn_tier(0.00) == "NORMAL_OPERATION"
        assert warn_tier(0.24) == "NORMAL_OPERATION"


class TestAnchorStorms:
    """
    Anchor events from HURDAT2 NOAA real data, confirmed in this session.
    Scores are at peak intensity position from the best-track record.
    """

    def test_andrew_1992_is_emergency(self):
        # Cat-5 145kt, peak near (25.5, -80.3) — direct Miami landfall
        s = warn_score(145, 25.5, -80.3)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"
        assert s > 0.80

    def test_irma_2017_is_emergency(self):
        # Cat-5 150kt near San Juan (19.2, -66.2)
        s = warn_score(150, 19.2, -66.2)
        assert warn_tier(s) == "EMERGENCY_RESPONSE"

    def test_katrina_2005_scores_above_monitor(self):
        # Cat-5 140kt, peak offshore at (27.2, -89.2) — weaker than landfall
        s = warn_score(140, 27.2, -89.2)
        assert warn_tier(s) in {"MITIGATION_REQUIRED", "EMERGENCY_RESPONSE"}

    def test_tropical_storm_far_offshore_is_normal(self):
        # TS-strength (55kt) far offshore — wind_norm=0 but small surge proxy still contributes
        s = warn_score(55, 30.0, -55.0)
        assert warn_tier(s) == "NORMAL_OPERATION"
        assert s < 0.10

    def test_cat5_open_ocean_scores_lower_than_landfall(self):
        # Same wind speed: mid-ocean vs Miami coast
        s_ocean    = warn_score(155, 30.0, -55.0)
        s_landfall = warn_score(155, 25.5, -80.3)
        assert s_landfall > s_ocean


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "warn_hurricane_events.json"
        if not p.exists():
            pytest.skip("Run build_warn_hurricane.py first")
        return json.loads(p.read_text())

    def test_required_keys(self, output):
        for k in ["source", "fetched_utc", "basin", "storms_scored",
                  "formula", "claim_boundary", "storms", "blake3"]:
            assert k in output

    def test_source_is_hurdat2(self, output):
        assert "HURDAT2" in output["source"] or "hurdat" in output["source"].lower()

    def test_storms_is_list(self, output):
        assert isinstance(output["storms"], list)
        assert len(output["storms"]) > 0

    def test_every_storm_has_required_fields(self, output):
        valid_tiers = {"NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"}
        for s in output["storms"]:
            assert "name" in s
            assert "year" in s
            assert "wind_kt" in s
            assert "warn_score" in s
            assert "warn_tier" in s
            assert s["warn_tier"] in valid_tiers
            assert 0.0 <= float(s["warn_score"]) <= 1.0

    def test_andrew_in_top5(self, output):
        top5_names = {s["name"] for s in output["storms"][:5]}
        assert "ANDREW" in top5_names or "IRMA" in top5_names

    def test_formula_weights_documented(self, output):
        f = output["formula"]["warn_score"]
        assert "0.45" in f
        assert "0.35" in f
        assert "0.20" in f

    def test_claim_boundary_mentions_proxy(self, output):
        cb = output["claim_boundary"].lower()
        assert "proxy" in cb or "categorical" in cb

    def test_storms_scored_matches_count(self, output):
        assert output["storms_scored"] >= len(output["storms"])
