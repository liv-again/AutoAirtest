from autoairtest.models import NaturalLanguageTestCase
from autoairtest.planning.planning_agent import PlanningAgent


def _case():
    return NaturalLanguageTestCase(
        case_id="TC_1",
        internal_id="TC_1",
        row_number=1,
        business_module="行情",
        feature_module="股指",
        feature_item="国内指数",
        test_purpose="检查顺序",
        priority="high",
        step_name="",
        precondition="",
        operation_description="进入行情-股指-国内指数",
        parameters="",
        expected_result="科创综指排在第四位",
        original_fields={},
    )


def test_planning_agent_uses_rule_based_fallback_without_llm():
    plan = PlanningAgent(llm_client=None).plan(_case())

    assert plan.case_id == "TC_1"
    assert plan.actions
    assert plan.verification_goals
