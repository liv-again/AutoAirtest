from dataclasses import replace
from pathlib import Path

from autoairtest.excel_loader import load_test_cases
from autoairtest.models import NaturalLanguageTestCase
from autoairtest.planning.planning_agent import PlanningAgent
from autoairtest.planning.rule_based_planner import RuleBasedPlanner
from autoairtest.planning.skill_registry import SkillRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingLLMClient:
    def __init__(self):
        self.calls = []

    def json_call(self, prompt, schema, **kwargs):
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
        return {"status": "unavailable"}


def _common_prefix(values):
    prefix = values[0]
    for value in values[1:]:
        index = 0
        while index < min(len(prefix), len(value)) and prefix[index] == value[index]:
            index += 1
        prefix = prefix[:index]
    return prefix


def _write_expected_result_rules(tmp_path):
    rules_dir = tmp_path / "skills" / "expected_result_rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_dir.joinpath("SKILL.md").write_text(
        "# Expected Result Rules\n\nReturn structured verification goals.",
        encoding="utf-8",
    )


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


def test_planner_places_all_stable_rules_before_case_specific_context():
    cases = load_test_cases(PROJECT_ROOT / "test-cases.xlsx", "需求测试报告")
    agent = PlanningAgent(skill_registry=SkillRegistry(PROJECT_ROOT / "skills"))

    prompts = [
        agent._planner_prompt(case, agent._navigation_path_for(case))
        for case in cases
    ]
    expected_rules = agent._expected_result_rules_section()
    common_prefix = _common_prefix(prompts)

    assert expected_rules in common_prefix
    assert common_prefix.index(expected_rules) > common_prefix.index("# Planner Prompt")
    assert all(
        prompt.index(expected_rules) < prompt.index(f"case_id: {case.internal_id}")
        for prompt, case in zip(prompts, cases)
    )


def test_planner_default_prompt_path_does_not_depend_on_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = PlanningAgent(skill_registry=SkillRegistry(PROJECT_ROOT / "skills"))

    prompt = agent._planner_prompt(_case(), [])

    assert prompt.startswith("# Planner Prompt")


def test_planner_passes_non_sensitive_call_context():
    llm = CapturingLLMClient()

    PlanningAgent(
        llm_client=llm,
        skill_registry=SkillRegistry(PROJECT_ROOT / "skills"),
    ).plan(_case())

    assert llm.calls[0]["context"] == {"stage": "planning", "case_id": "TC_1"}


def test_planner_missing_stable_rules_falls_back_without_calling_llm(tmp_path):
    llm = CapturingLLMClient()
    agent = PlanningAgent(
        llm_client=llm,
        skill_registry=SkillRegistry(tmp_path / "skills"),
    )

    plan = agent.plan(_case())

    assert llm.calls == []
    assert plan.llm_used is False


def test_planning_agent_constrains_llm_plan_with_navigation_skill(tmp_path):
    _write_expected_result_rules(tmp_path)
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

        def json_call(self, prompt, schema, **kwargs):
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


def test_planning_agent_removes_llm_navigation_taps_already_covered_by_skill(tmp_path):
    _write_expected_result_rules(tmp_path)
    skill_dir = tmp_path / "skills" / "navigation"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("nodes.yaml").write_text(
        """
roots: [market]
nodes:
  market:
    text: 行情
    parent: null
    aliases: []
    locators:
      - type: content_desc
        value: 行情
    children: [market_quotes]
  market_quotes:
    text: 行情
    parent: market
    aliases: [行情分类]
    locators:
      - type: resource_id
        value: id/right_radio
    children: [market_global]
  market_global:
    text: 全球
    parent: market_quotes
    aliases: [股指]
    children: []
""".strip(),
        encoding="utf-8",
    )

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            return {
                "status": "success",
                "data": {
                    "case_id": "TC_1",
                    "understanding": "检查国内指数并进入科创综指详情",
                    "preconditions": [],
                    "actions": [
                        {
                            "action_id": "raw1", "intent": "observe",
                            "description": "观察当前页面（全球），确认页面状态", "target": "",
                            "target_context": "全球", "preferred_locator": "",
                        },
                        {
                            "action_id": "raw2", "intent": "tap",
                            "description": "点击行情", "target": "行情",
                            "target_context": "底部导航", "preferred_locator": "poco_semantic",
                        },
                        {
                            "action_id": "raw3", "intent": "observe",
                            "description": "观察行情页，确认已成功进入", "target": "",
                            "target_context": "行情页", "preferred_locator": "",
                        },
                        {
                            "action_id": "raw4", "intent": "tap",
                            "description": "点击股指", "target": "股指",
                            "target_context": "行情页", "preferred_locator": "poco_semantic",
                        },
                        {
                            "action_id": "raw5", "intent": "observe",
                            "description": "观察国内指数模块并获取顺序和数据", "target": "国内指数",
                            "target_context": "全球页", "preferred_locator": "",
                        },
                        {
                            "action_id": "raw6", "intent": "tap",
                            "description": "点击科创综指", "target": "科创综指",
                            "target_context": "国内指数", "preferred_locator": "poco_semantic",
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

    assert [(action.intent, action.target) for action in plan.actions] == [
        ("navigate", "行情"),
        ("navigate", "行情"),
        ("navigate", "全球"),
        ("observe", ""),
        ("observe", "国内指数"),
        ("tap", "科创综指"),
    ]
    assert [action.action_id for action in plan.actions] == ["a1", "a2", "a3", "a4", "a5", "a6"]
    assert plan.actions[0].preferred_locator == "poco_content_desc"
    assert plan.actions[0].locators[0].value == "行情"
    assert plan.actions[1].preferred_locator == "poco_resource_id"
    assert plan.actions[1].locators[0].value == "id/right_radio"


def _write_stock_detail_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "stock_detail"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("fenshi_elements_1.yaml").write_text(
        """
page_id: stock_fenshi
roots: [title_bar, bottom_navigation]
elements:
  title_bar:
    text: 标题栏
    parent: null
    aliases: []
    children: [title_back, title_search]
    locators: []
  title_back:
    text: 返回
    parent: title_bar
    aliases: [返回按钮]
    children: []
    locators:
      - type: resource_id
        value: id/backButton
    description: 标题栏返回图标
  title_search:
    text: 搜索
    parent: title_bar
    aliases: [个股搜索]
    children: []
    locators:
      - type: resource_id
        value: id/navi_title_right
    description: 标题栏搜索图标
  bottom_navigation:
    text: 底部导航栏
    parent: null
    aliases: [底部操作栏]
    children: [bottom_more]
    locators: []
  bottom_more:
    text: 更多
    parent: bottom_navigation
    aliases: [底部更多]
    children: []
    locators:
      - type: resource_id
        value: id/ll_more
    description: 底部更多图标
""".strip(),
        encoding="utf-8",
    )


def test_planning_agent_injects_stock_detail_usage_and_enriches_llm_action(tmp_path):
    _write_expected_result_rules(tmp_path)
    _write_stock_detail_skill(tmp_path)

    class FakeLLMClient:
        def __init__(self):
            self.prompt = ""

        def json_call(self, prompt, schema, **kwargs):
            self.prompt = prompt
            return {
                "status": "success",
                "data": {
                    "case_id": "TC_1",
                    "understanding": "点击个股分时页返回图标",
                    "preconditions": [],
                    "actions": [
                        {
                            "action_id": "a1",
                            "intent": "tap",
                            "description": "点击返回",
                            "target": "返回",
                            "target_context": "个股分时页标题栏",
                            "preferred_locator": "poco_semantic",
                            "action_risk_level": "low",
                            "interpretation_rationale_ids": [],
                        }
                    ],
                    "verification_goals": [],
                    "manual_review_notes": [],
                    "interpretation_rationales": [],
                },
            }

    llm = FakeLLMClient()
    case = replace(
        _case(),
        business_module="个股详情",
        feature_module="分时页",
        operation_description="在个股分时页点击返回",
    )

    plan = PlanningAgent(
        llm_client=llm,
        skill_registry=SkillRegistry(tmp_path / "skills"),
    ).plan(case)

    assert "Stock detail skill applies" in llm.prompt
    assert "title_back" in llm.prompt
    assert "resource_id=id/backButton" in llm.prompt
    assert plan.actions[0].preferred_locator == "poco_resource_id"
    assert plan.actions[0].locators[0].type == "resource_id"
    assert plan.actions[0].locators[0].value == "id/backButton"
    assert any(
        rationale.matched_skill_rules == ["stock_detail_element.title_back"]
        for rationale in plan.interpretation_rationales
    )


def test_rule_based_planner_enriches_stock_detail_icon_action(tmp_path):
    _write_stock_detail_skill(tmp_path)
    case = replace(
        _case(),
        business_module="个股详情",
        feature_module="分时页",
        operation_description="在个股分时页点击返回",
    )

    plan = RuleBasedPlanner(skill_registry=SkillRegistry(tmp_path / "skills")).plan(case)

    action = next(action for action in plan.actions if action.target == "返回")
    assert action.intent == "tap"
    assert action.preferred_locator == "poco_resource_id"
    assert action.locators[0].type == "resource_id"
    assert action.locators[0].value == "id/backButton"


def test_rule_based_planner_deduplicates_legacy_and_stock_detail_more_action(tmp_path):
    _write_stock_detail_skill(tmp_path)
    case = replace(
        _case(),
        business_module="个股详情",
        feature_module="分时页",
        operation_description="在个股分时页点击底部导航栏更多",
    )

    plan = RuleBasedPlanner(skill_registry=SkillRegistry(tmp_path / "skills")).plan(case)

    more_actions = [action for action in plan.actions if action.target == "更多"]
    assert len(more_actions) == 1
    assert more_actions[0].locators[0].value == "id/ll_more"


def _write_navigation_search_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "navigation"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("nodes.yaml").write_text(
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
    children: []
""".strip(),
        encoding="utf-8",
    )


def test_llm_planner_does_not_apply_page_local_locator_to_navigation_action(tmp_path):
    _write_expected_result_rules(tmp_path)
    _write_stock_detail_skill(tmp_path)
    _write_navigation_search_skill(tmp_path)

    class FakeLLMClient:
        def json_call(self, prompt, schema, **kwargs):
            return {
                "status": "success",
                "data": {
                    "case_id": "TC_1",
                    "understanding": "从行情搜索进入个股分时页",
                    "preconditions": [],
                    "actions": [
                        {
                            "action_id": "a1",
                            "intent": "observe",
                            "description": "观察详情页",
                            "target": "当前页面",
                            "target_context": "个股分时页",
                            "preferred_locator": "poco_semantic",
                            "action_risk_level": "low",
                            "interpretation_rationale_ids": [],
                        }
                    ],
                    "verification_goals": [],
                    "manual_review_notes": [],
                    "interpretation_rationales": [],
                },
            }

    case = replace(
        _case(),
        business_module="个股详情",
        feature_module="分时页",
        operation_description="从行情搜索进入个股分时页",
    )
    plan = PlanningAgent(
        llm_client=FakeLLMClient(),
        skill_registry=SkillRegistry(tmp_path / "skills"),
    ).plan(case)

    search_action = next(action for action in plan.actions if action.intent == "navigate" and action.target == "搜索")
    assert search_action.locators == []
    assert search_action.preferred_locator == "poco_semantic"


def test_rule_planner_does_not_apply_page_local_locator_to_navigation_action(tmp_path):
    _write_stock_detail_skill(tmp_path)
    _write_navigation_search_skill(tmp_path)
    case = replace(
        _case(),
        business_module="个股详情",
        feature_module="分时页",
        operation_description="从行情搜索进入个股分时页",
    )

    plan = RuleBasedPlanner(skill_registry=SkillRegistry(tmp_path / "skills")).plan(case)

    search_action = next(action for action in plan.actions if action.intent == "navigate" and action.target == "搜索")
    assert search_action.locators == []
    assert search_action.preferred_locator == "poco_semantic"
