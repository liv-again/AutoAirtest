"""离线验证器兼容入口。"""

from __future__ import annotations

from autoairtest.models import (
    PreliminaryJudgment,
    VerificationGoal,
)
from autoairtest.verification.verification_agent import VerificationAgent


def verify_goals(
    goals: list[VerificationGoal],
    evidence: dict[str, object],
) -> list[PreliminaryJudgment]:
    """逐一验证执行计划中的验证目标。"""

    return VerificationAgent().verify(goals, evidence, case_dir=None).judgments
