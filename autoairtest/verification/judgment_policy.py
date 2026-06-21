"""验证裁决策略。"""

from __future__ import annotations

from typing import Any

from autoairtest.models import PreliminaryJudgment, PreliminaryStatus, VerificationGoal, VerificationGoalCategory


class JudgmentPolicy:
    """集中管理人工复核原因与通用裁决构造。"""

    def manual_review_reason_for_goal(self, goal: VerificationGoal) -> str:
        if goal.category == VerificationGoalCategory.DATA_CORRECTNESS:
            return "data_correctness"
        if goal.category == VerificationGoalCategory.COLOR_RULE:
            return "color_rule"
        return goal.review_reason

    def manual_required(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
        reason: str,
        basis: str,
        structured_details: dict[str, Any] | None = None,
        review_reason: str | None = None,
    ) -> PreliminaryJudgment:
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
            confidence=0.0,
            basis=basis,
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=True,
            review_reason=review_reason if review_reason is not None else reason,
            manual_review_reason=reason,
            structured_details=structured_details or {},
        )
