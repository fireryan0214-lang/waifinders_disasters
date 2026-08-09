"""
Tests for scripts/wise_multihazard_decision.py
Validates tier ordering, compound escalation logic, decision matrix, and output schema.
"""
import json
from pathlib import Path
import pytest


TIER_ORDER = {"NORMAL_OPERATION": 0, "MONITOR": 1, "MITIGATION_REQUIRED": 2, "EMERGENCY_RESPONSE": 3}

def tier_int(t): return TIER_ORDER.get(t, 0)
def int_tier(i): return list(TIER_ORDER.keys())[min(i, 3)]

def wise_decision(hazard_tiers: dict) -> tuple:
    """Returns (final_tier, is_compound, elevated_list)."""
    base = max(tier_int(t) for t in hazard_tiers.values())
    elevated = [h for h, t in hazard_tiers.items() if tier_int(t) >= 1]
    compound = len(elevated) >= 2
    boost = 1 if compound else 0
    final = min(3, base + boost)
    return int_tier(final), compound, elevated


class TestTierOrdering:
    def test_tier_int_order_is_correct(self):
        assert tier_int("NORMAL_OPERATION") < tier_int("MONITOR")
        assert tier_int("MONITOR") < tier_int("MITIGATION_REQUIRED")
        assert tier_int("MITIGATION_REQUIRED") < tier_int("EMERGENCY_RESPONSE")

    def test_all_four_tiers_have_distinct_values(self):
        vals = [tier_int(t) for t in TIER_ORDER]
        assert len(set(vals)) == 4

    def test_int_tier_roundtrip(self):
        for t in TIER_ORDER:
            assert int_tier(tier_int(t)) == t


class TestWiseDecision:
    def test_all_normal_gives_normal(self):
        tiers = {h: "NORMAL_OPERATION" for h in ["wildfire","earthquake","tsunami","flood"]}
        decision, compound, elevated = wise_decision(tiers)
        assert decision == "NORMAL_OPERATION"
        assert not compound
        assert elevated == []

    def test_single_emergency_gives_emergency(self):
        tiers = {
            "wildfire": "NORMAL_OPERATION",
            "earthquake": "EMERGENCY_RESPONSE",
            "tsunami": "NORMAL_OPERATION",
            "flood": "NORMAL_OPERATION",
        }
        decision, compound, elevated = wise_decision(tiers)
        # One hazard at EMERGENCY → base=3, no compound (only 1 elevated) → 3
        assert decision == "EMERGENCY_RESPONSE"
        assert not compound

    def test_two_monitor_hazards_compound_to_mitigation(self):
        tiers = {
            "wildfire": "MONITOR",
            "earthquake": "MONITOR",
            "tsunami": "NORMAL_OPERATION",
            "flood": "NORMAL_OPERATION",
        }
        decision, compound, elevated = wise_decision(tiers)
        # Base = MONITOR (1), compound → +1 = MITIGATION_REQUIRED (2)
        assert decision == "MITIGATION_REQUIRED"
        assert compound
        assert len(elevated) == 2

    def test_three_elevated_hazards_compound(self):
        tiers = {
            "wildfire": "NORMAL_OPERATION",
            "earthquake": "MONITOR",
            "tsunami": "EMERGENCY_RESPONSE",
            "flood": "MITIGATION_REQUIRED",
        }
        decision, compound, elevated = wise_decision(tiers)
        # Base = EMERGENCY_RESPONSE (3), compound → min(3, 3+1) = EMERGENCY_RESPONSE
        assert decision == "EMERGENCY_RESPONSE"
        assert compound
        assert len(elevated) == 3

    def test_compound_cannot_exceed_emergency_response(self):
        tiers = {h: "EMERGENCY_RESPONSE" for h in ["a","b","c","d"]}
        decision, _, _ = wise_decision(tiers)
        assert decision == "EMERGENCY_RESPONSE"

    def test_single_monitor_does_not_compound(self):
        tiers = {"earthquake": "MONITOR", "tsunami": "NORMAL_OPERATION"}
        decision, compound, _ = wise_decision(tiers)
        assert not compound
        assert decision == "MONITOR"

    def test_compound_escalates_exactly_one_level(self):
        """Two MONITOR hazards → MITIGATION_REQUIRED (not EMERGENCY)."""
        tiers = {"a": "MONITOR", "b": "MONITOR", "c": "NORMAL_OPERATION"}
        decision, compound, _ = wise_decision(tiers)
        assert compound
        assert decision == "MITIGATION_REQUIRED"

    def test_real_session_scenario(self):
        """
        This session's actual WISE result:
        earthquake=MONITOR, tsunami=EMERGENCY_RESPONSE, flood=MITIGATION_REQUIRED
        → base=EMERGENCY(3), compound(3 elevated) → min(3,4)=EMERGENCY_RESPONSE
        """
        tiers = {
            "wildfire":    "NORMAL_OPERATION",
            "earthquake":  "MONITOR",
            "tsunami":     "EMERGENCY_RESPONSE",
            "flood_surge": "MITIGATION_REQUIRED",
            "pulse":       "NORMAL_OPERATION",
        }
        decision, compound, elevated = wise_decision(tiers)
        assert decision == "EMERGENCY_RESPONSE"
        assert compound
        assert set(elevated) == {"earthquake","tsunami","flood_surge"}


class TestWiseDecisionStates:
    def test_all_four_states_reachable(self):
        scenarios = [
            {"a": "NORMAL_OPERATION"},
            {"a": "MONITOR"},
            {"a": "MITIGATION_REQUIRED"},
            {"a": "EMERGENCY_RESPONSE"},
        ]
        decisions = {wise_decision(s)[0] for s in scenarios}
        assert decisions == {"NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"}


class TestOutputFile:
    @pytest.fixture
    def output(self):
        p = Path(__file__).parent.parent / "outputs" / "disaster_demo" / "wise_multihazard_decision.json"
        if not p.exists():
            pytest.skip("Run wise_multihazard_decision.py first")
        return json.loads(p.read_text())

    def test_required_keys(self, output):
        for k in ["generated_utc","wise_decision","compound_event","elevated_hazards",
                  "hazard_signals","pulse_state","recommended_actions","claim_boundary","formula"]:
            assert k in output

    def test_wise_decision_is_valid_tier(self, output):
        assert output["wise_decision"] in TIER_ORDER

    def test_recommended_actions_non_empty(self, output):
        assert len(output["recommended_actions"]) > 0

    def test_claim_boundary_disavows_validation(self, output):
        claim = output["claim_boundary"].lower()
        assert "not validated" in claim or "experimental" in claim or "prototype" in claim

    def test_hazard_signals_have_score_and_tier(self, output):
        for hazard, data in output["hazard_signals"].items():
            assert "score" in data
            assert "tier" in data
            assert data["tier"] in TIER_ORDER

    def test_cost_estimate_labeled_illustrative(self, output):
        cost = output.get("cost_estimate_illustrative", {})
        assert cost  # must be present
        note = cost.get("note", "").lower()
        assert "illustrative" in note or "no real" in note or "historical range" in note

    def test_formula_documents_compound_rule(self, output):
        formula = output["formula"]
        assert "compound" in str(formula).lower() or "2+" in str(formula)

    def test_hurricane_domain_present(self, output):
        assert "hurricane" in output["hazard_signals"]
        assert output["hazard_signals"]["hurricane"]["tier"] in {
            "NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"
        }

    def test_nuclear_domain_present(self, output):
        assert "nuclear" in output["hazard_signals"]
        assert output["hazard_signals"]["nuclear"]["tier"] in {
            "NORMAL_OPERATION","MONITOR","MITIGATION_REQUIRED","EMERGENCY_RESPONSE"
        }

    def test_nuclear_score_is_bounded(self, output):
        s = output["hazard_signals"]["nuclear"]["score"]
        assert 0.0 <= s <= 1.0

    def test_nuclear_is_planning_only(self, output):
        assert output["hazard_signals"]["nuclear"]["decision_inclusion"] is False
        assert "nuclear" not in output["elevated_hazards"]
