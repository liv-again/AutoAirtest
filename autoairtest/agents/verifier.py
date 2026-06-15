"""离线验证器。

验证器基于结构化界面证据给出初步判断。它优先处理可离线判断的文本顺序和文本存在性，
并对行情数据正确性等业务判断保持人工复核边界。
"""

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
    """逐一验证执行计划中的验证目标。"""

    return [_verify_goal(goal, evidence) for goal in goals]


def _verify_goal(goal: VerificationGoal, evidence: dict[str, object]) -> PreliminaryJudgment:
    """根据目标类别选择具体的离线验证策略。"""

    if goal.human_review_required:
        # 人工复核目标不被自动判定为通过，避免把初判误写成最终结论。
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
    """验证期望文本序列是否按给定顺序出现在界面证据中。"""

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
    """验证页面跳转、弹框或普通文本目标是否具有文本证据支持。"""

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
