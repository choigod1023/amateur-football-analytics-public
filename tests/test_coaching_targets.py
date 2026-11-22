import pytest
from app.coaching_fields import fields
from app.live_feedback import LiveAnalyzer


@pytest.mark.parametrize("kind", ["gap_wide", "box_attack", "isolated", "line_drop", "run", "conceded_run"])
def test_directive_names_group_action_evidence_without_invented_identity(kind):
    result = fields(kind, {"n": 3, "retreat_supported": True, "leader_ids": [998]}, "")
    directive = result["directive"]
    assert directive["target"]["scope"] == "group"
    assert directive["target"]["track_ids"] == []
    assert directive["individual_assignment_verified"] is False
    assert directive["target"]["selection_basis"]
    assert directive["condition"]
    assert directive["rationale"] == result["observation"]
    for value in (directive["target"]["label"], directive["action"], directive["rationale"]):
        assert value in result["suggestion"]
    assert "998" not in result["suggestion"]


@pytest.mark.parametrize("kind", ["line_drop", "unrecognized"])
def test_missing_support_targets_staff_not_players(kind):
    result = fields(kind, {}, "")
    assert result["directive"]["status"] == "review_required"
    assert result["directive"]["target"]["scope"] == "staff"


def test_attack_and_conceded_run_address_different_groups():
    own = fields("run", {}, "")["directive"]
    other = fields("conceded_run", {}, "")["directive"]
    assert own["target"] != other["target"]
    assert own["action"] != other["action"]


def test_emitted_legacy_rules_do_not_bypass_conditional_directive():
    wide = [(i, x, 0) for i, x in enumerate([-25,-24,-23,23,24,25])]
    opponent = [(i+100,x,y) for i,x,y in wide]
    analyzer = LiveAnalyzer(1, disabled=())          # gap_wide is off by default (DISABLED_KINDS); the rule itself is tested here
    alerts = [a for i in range(31) for a in analyzer.update(i/5,wide,opponent) if a["kind"] == "gap_wide"]
    assert len(alerts) == 1
    assert alerts[0]["rules"] == [alerts[0]["suggestion"]]
    assert alerts[0]["drill"] is None
