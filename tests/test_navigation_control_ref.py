from dataclasses import replace

from autoairtest.models import NaturalLanguageTestCase
from autoairtest.planning.planning_agent import PlanningAgent
from autoairtest.planning.skill_registry import SkillRegistry


def _write_skills(tmp_path):
    navigation_dir = tmp_path / "skills" / "navigation"
    navigation_dir.mkdir(parents=True)
    navigation_dir.joinpath("nodes.yaml").write_text(
        """
roots: [market]
nodes:
  market:
    text: 行情
    parent: null
    aliases: []
    children: [market_search]
  market_search:
    text: 搜索
    parent: market
    aliases: [行情搜索]
    control_ref: market_search_button
    children: []
""".strip(),
        encoding="utf-8",
    )

    controls_dir = tmp_path / "skills" / "non_text_controls"
    controls_dir.mkdir(parents=True)
    controls_dir.joinpath("market_elements.yaml").write_text(
        """
page_id: market
elements:
  market_search_button:
    text: 搜索按钮
    aliases: [行情搜索, 股票搜索]
    locators:
      - type: resource_id
        value: id/new_title_search
""".strip(),
        encoding="utf-8",
    )

    rules_dir = tmp_path / "skills" / "expected_result_rules"
    rules_dir.mkdir(parents=True)
    rules_dir.joinpath("SKILL.md").write_text(
        "# Expected Result Rules\n\nReturn structured verification goals.",
        encoding="utf-8",
    )


def _case():
    return NaturalLanguageTestCase(
        case_id="TC_SEARCH",
        internal_id="TC_SEARCH",
        row_number=1,
        business_module="行情",
        feature_module="搜索",
        feature_item="搜索",
        test_purpose="验证搜索跳转",
        priority="high",
        step_name="",
        precondition="",
        operation_description="进入行情页面，点击右上角搜索按钮",
        parameters="",
        expected_result="进入搜索页面",
        original_fields={},
    )


def test_navigation_node_inherits_control_aliases_and_locators(tmp_path):
    _write_skills(tmp_path)

    node = SkillRegistry(tmp_path / "skills").navigation_nodes["market_search"]

    assert node.control_ref == "market_search_button"
    assert node.aliases == ("行情搜索", "搜索按钮", "股票搜索")
    assert node.preferred_locator == "poco_resource_id"
    assert [(item.type, item.value) for item in node.locators] == [
        ("resource_id", "id/new_title_search")
    ]


def test_planner_uses_control_ref_locator_and_removes_duplicate_llm_tap(tmp_path):
    _write_skills(tmp_path)

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            return {
                "status": "success",
                "data": {
                    "case_id": "TC_SEARCH",
                    "understanding": "进入行情搜索页面",
                    "preconditions": [],
                    "actions": [
                        {
                            "action_id": "raw1",
                            "intent": "tap",
                            "description": "点击搜索按钮",
                            "target": "搜索按钮",
                            "target_context": "行情页面右上角",
                            "preferred_locator": "poco_semantic",
                        },
                        {
                            "action_id": "raw2",
                            "intent": "observe",
                            "description": "观察搜索页面",
                            "target": "搜索页面",
                            "target_context": "搜索页面",
                            "preferred_locator": "",
                        },
                    ],
                    "verification_goals": [],
                    "manual_review_notes": [],
                    "interpretation_rationales": [],
                },
            }

    plan = PlanningAgent(
        llm_client=FakeLLMClient(),
        skill_registry=SkillRegistry(tmp_path / "skills"),
    ).plan(_case())

    search_action = next(
        action for action in plan.actions
        if action.intent == "navigate" and action.target == "搜索"
    )
    assert search_action.preferred_locator == "poco_resource_id"
    assert search_action.locators[0].value == "id/new_title_search"
    assert not any(
        action.intent == "tap" and action.target == "搜索按钮"
        for action in plan.actions
    )
