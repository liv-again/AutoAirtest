from autoairtest.execution.risk_policy import RiskPolicy
from autoairtest.models import ActionRiskLevel, PlanAction


def _action(intent, target, description=None, context=None):
    return PlanAction(
        action_id="a1",
        intent=intent,
        description=description or target,
        target=target,
        target_context=context or target,
        preferred_locator="poco_text",
    )


def test_risk_policy_classifies_navigation_as_low():
    assert RiskPolicy().classify(_action("navigate", "行情")) == ActionRiskLevel.LOW


def test_risk_policy_classifies_order_or_trade_keywords_as_high():
    assert RiskPolicy().classify(_action("tap", "买入确认")) == ActionRiskLevel.HIGH


def test_risk_policy_classifies_input_as_medium():
    assert RiskPolicy().classify(_action("text", "600519", description="输入股票代码")) == ActionRiskLevel.MEDIUM


def test_risk_policy_budget_uses_config():
    policy = RiskPolicy({"low": 3, "medium": 1, "high": 0})

    assert policy.correction_budget(ActionRiskLevel.LOW) == 3
    assert policy.correction_budget(ActionRiskLevel.MEDIUM) == 1
    assert policy.correction_budget(ActionRiskLevel.HIGH) == 0
