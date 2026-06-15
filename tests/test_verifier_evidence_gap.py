from autoairtest.agents.verifier import verify_goals
from autoairtest.models import PreliminaryStatus, VerificationGoal, VerificationGoalCategory


def test_order_gap_requires_manual_review_with_structured_details():
    goal = VerificationGoal(
        goal_id="v1",
        claim="A-B-C-D order is shown",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C", "D"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals([goal], {"visible_texts": ["A", "B", "C"], "evidence_files": ["elements.json"]})

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "verification_evidence_gap"
    assert judgment.structured_details == {
        "expected": ["A", "B", "C", "D"],
        "observed": ["A", "B", "C"],
        "missing": ["D"],
        "unexpected": [],
    }
    assert "elements.json" in judgment.evidence_files


def test_order_unexpected_entity_requires_manual_review_with_structured_details():
    goal = VerificationGoal(
        goal_id="v1",
        claim="A-B-C-D order is shown",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C", "D"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    [judgment] = verify_goals([goal], {"visible_texts": ["A", "B", "C", "E"], "evidence_files": []})

    assert judgment.preliminary_status == PreliminaryStatus.MANUAL_REQUIRED
    assert judgment.manual_review_reason == "verification_evidence_gap"
    assert judgment.structured_details["missing"] == ["D"]
    assert judgment.structured_details["unexpected"] == ["E"]
