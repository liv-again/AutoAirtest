from __future__ import annotations

from autoairtest.models import (
    PreliminaryJudgment,
    PreliminaryStatus,
    VerificationGoal,
    VerificationGoalCategory,
)


def verify_goals(
    goals: list[VerificationGoal],
    evidence: dict[str, object],
) -> list[PreliminaryJudgment]:
    return [_verify_goal(goal, evidence) for goal in goals]


def _verify_goal(goal: VerificationGoal, evidence: dict[str, object]) -> PreliminaryJudgment:
    if goal.human_review_required:
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
            confidence=0.0,
            basis=f"{goal.claim} cannot be finalized automatically in MVP.",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=True,
            review_reason=goal.review_reason,
        )

    visible_texts = [str(item) for item in evidence.get("visible_texts", [])]
    if goal.category == VerificationGoalCategory.ELEMENT_ORDER:
        return _verify_order(goal, visible_texts, evidence)
    if goal.category in {
        VerificationGoalCategory.PAGE_NAVIGATION,
        VerificationGoalCategory.POPUP_DISPLAY,
        VerificationGoalCategory.TEXT_PRESENT,
    }:
        return _verify_text_presence(goal, visible_texts, evidence)

    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=PreliminaryStatus.UNCERTAIN,
        confidence=0.0,
        basis="No offline verifier exists for this goal category.",
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
    )


def _verify_order(
    goal: VerificationGoal,
    visible_texts: list[str],
    evidence: dict[str, object],
) -> PreliminaryJudgment:
    positions: list[int] = []
    for expected in goal.expected_entities:
        try:
            positions.append(visible_texts.index(expected))
        except ValueError:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis=f"Missing expected text: {expected}",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
            )

    passed = positions == sorted(positions)
    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=PreliminaryStatus.PASS if passed else PreliminaryStatus.FAIL,
        confidence=0.82 if passed else 0.88,
        basis=f"Observed order positions: {positions}",
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
    )


def _verify_text_presence(
    goal: VerificationGoal,
    visible_texts: list[str],
    evidence: dict[str, object],
) -> PreliminaryJudgment:
    haystack = " ".join(visible_texts)
    expected = goal.expected_entities or [goal.claim]
    if any(item and item in haystack for item in expected):
        status = PreliminaryStatus.PASS
        confidence = 0.78
        basis = "Expected text was found in interface evidence."
    else:
        status = PreliminaryStatus.UNCERTAIN
        confidence = 0.0
        basis = "No matching text evidence was available offline."
    return PreliminaryJudgment(
        goal_id=goal.goal_id,
        preliminary_status=status,
        confidence=confidence,
        basis=basis,
        evidence_files=list(evidence.get("evidence_files", [])),
        human_review_required=False,
        review_reason="",
    )
