from dataclasses import replace

from autoairtest.models import NaturalLanguageTestCase
from autoairtest.planning.planning_agent import PlanningAgent
from autoairtest.planning.skill_registry import SkillRegistry


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


def test_planning_agent_constrains_llm_plan_with_navigation_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "navigation"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("nodes.yaml").write_text(
        """
roots:
  - market
nodes:
  market:
    text: 行情
    parent: null
    aliases: []
    children: [market_a_share]
  market_a_share:
    text: A股
    parent: market
    aliases: [A股行情]
    children: [cn_a_market]
  cn_a_market:
    text: 沪深京
    parent: market_a_share
    aliases: [沪深]
    children: []
""".strip(),
        encoding="utf-8",
    )

    class FakeLLMClient:
        def __init__(self):
            self.prompt = ""

        def json_call(self, prompt, schema):
            self.prompt = prompt
            return {
                "status": "success",
                "data": {
                    "case_id": "TC_1",
                    "understanding": "LLM plan",
                    "preconditions": [{"type": "app_state", "description": "ready"}],
                    "actions": [
                        {
                            "action_id": "a1",
                            "intent": "navigate",
                            "description": "进入错误菜单",
                            "target": "错误菜单",
                            "target_context": "进入行情-A股-沪深",
                            "preferred_locator": "poco_semantic",
                            "action_risk_level": "low",
                            "interpretation_rationale_ids": [],
                        },
                        {
                            "action_id": "a2",
                            "intent": "tap",
                            "description": "点击任意股票",
                            "target": "任意股票",
                            "target_context": "进入行情-A股-沪深",
                            "preferred_locator": "poco_semantic",
                            "action_risk_level": "low",
                            "interpretation_rationale_ids": [],
                        },
                    ],
                    "verification_goals": [
                        {
                            "goal_id": "v1",
                            "claim": "页面跳转符合预期",
                            "category": "page_navigation",
                            "expected_entities": [],
                            "evidence_priority": ["poco_tree"],
                            "human_review_required": False,
                            "review_reason": "",
                        }
                    ],
                    "manual_review_notes": [],
                    "interpretation_rationales": [],
                },
            }

    llm = FakeLLMClient()
    case = replace(
        _case(),
        feature_module="A股",
        feature_item="沪深京",
        operation_description="进入行情-A股-沪深",
    )

    plan = PlanningAgent(
        llm_client=llm,
        skill_registry=SkillRegistry(tmp_path / "skills"),
    ).plan(case)

    assert "Navigation skill matched path" in llm.prompt
    assert [action.target for action in plan.actions[:3]] == ["行情", "A股", "沪深京"]
    assert plan.actions[3].target == "任意股票"
    assert any(
        rationale.matched_skill_rules == ["navigation_node.cn_a_market"]
        for rationale in plan.interpretation_rationales
    )
