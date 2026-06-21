from autoairtest.models import VerificationGoal, VerificationGoalCategory
from autoairtest.verification.rule_engine import RuleEngine


def test_rule_engine_reports_extra_order_evidence_gap():
    goal = VerificationGoal(
        goal_id="v1",
        claim="顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = RuleEngine().verify(goal, {"visible_texts": ["A", "B", "C", "E"], "evidence_files": []})

    assert judgment.preliminary_status.value == "manual_required"
    assert judgment.manual_review_reason == "verification_evidence_gap"
    assert judgment.structured_details["unexpected"] == ["E"]
