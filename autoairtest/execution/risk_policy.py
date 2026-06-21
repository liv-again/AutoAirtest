"""执行动作风险策略。"""

from __future__ import annotations

from typing import Any

from autoairtest.models import ActionRiskLevel, PlanAction


HIGH_RISK_KEYWORDS = ["买入", "卖出", "撤单", "确认", "提交", "支付", "转账"]
MEDIUM_RISK_KEYWORDS = ["登录", "输入", "搜索", "切换账号"]


class RiskPolicy:
    """集中处理动作风险分级和对应纠错预算。"""

    def __init__(self, correction_budget: dict[str, int] | None = None) -> None:
        self.correction_budget_config = {"low": 3, "medium": 1, "high": 0} | (correction_budget or {})

    def classify(self, action: PlanAction) -> ActionRiskLevel:
        text = _action_text(action)
        if any(keyword in text for keyword in HIGH_RISK_KEYWORDS):
            return ActionRiskLevel.HIGH
        if any(keyword in text for keyword in MEDIUM_RISK_KEYWORDS):
            return ActionRiskLevel.MEDIUM
        return ActionRiskLevel.LOW

    def correction_budget(self, risk_level: ActionRiskLevel | str) -> int:
        key = risk_level.value if isinstance(risk_level, ActionRiskLevel) else str(risk_level)
        return int(self.correction_budget_config.get(key, 0) or 0)


def _action_text(action: PlanAction) -> str:
    parts: list[Any] = [action.intent, action.target, action.description, action.target_context]
    return " ".join(str(part) for part in parts if str(part))
