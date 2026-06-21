from autoairtest.agents.planner import RuleBasedPlanner
from autoairtest.models import ActionRiskLevel, NaturalLanguageTestCase


def _case(operation_description: str) -> NaturalLanguageTestCase:
    return NaturalLanguageTestCase(
        case_id="TC_alias",
        internal_id="TC_alias__row_1",
        row_number=1,
        business_module="自选",
        feature_module="顶部指数",
        feature_item="",
        test_purpose="跳转校验",
        priority="high",
        step_name="",
        precondition="",
        operation_description=operation_description,
        parameters="",
        expected_result="弹出指数分时图弹框",
        original_fields={},
    )


def test_planner_normalizes_self_selected_alias_with_rationale():
    plan = RuleBasedPlanner().plan(_case("自选：点击顶部指数"))

    assert any(action.target == "我的自选" for action in plan.actions)
    [rationale] = [
        item
        for item in plan.interpretation_rationales
        if item.interpretation_type == "navigation_alias"
    ]
    assert rationale.original_expression == "自选"
    assert rationale.normalized_meaning == "我的自选"
    assert rationale.matched_skill_rules == ["navigation_alias.self_selected"]
    assert rationale.confidence >= 0.9


def test_planner_marks_actions_with_risk_level_and_rationale_ids():
    plan = RuleBasedPlanner().plan(_case("行情-股指-国内指数：点击右侧更多按钮"))

    assert plan.actions
    for action in plan.actions:
        assert action.action_risk_level == ActionRiskLevel.LOW
        assert action.interpretation_rationale_ids


def test_planner_extracts_swipe_input_and_back_actions():
    swipe_plan = RuleBasedPlanner().plan(_case("国内指数列表：向上滑动查看更多指数"))
    input_plan = RuleBasedPlanner().plan(_case("搜索页：输入600519"))
    back_plan = RuleBasedPlanner().plan(_case("指数详情页：返回上一页"))

    assert any(action.intent == "swipe" and action.target == "up" for action in swipe_plan.actions)
    assert any(action.intent == "text" and action.target == "600519" for action in input_plan.actions)
    assert any(action.intent == "keyevent" and action.target == "BACK" for action in back_plan.actions)
