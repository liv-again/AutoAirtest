"""Planning Agent。"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from autoairtest.models import (
    ActionRiskLevel,
    ExecutionPlan,
    InterpretationRationale,
    LocatorCandidate,
    NaturalLanguageTestCase,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)
from autoairtest.planning.rule_based_planner import RuleBasedPlanner
from autoairtest.planning.skill_registry import NavigationNode, SkillRegistry

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PLANNER_PROMPT = _PROJECT_ROOT / "prompts" / "planner.md"


class PlanningAgent:
    """优先使用可注入 LLM 规划，失败时回退到规则型 planner。"""

    def __init__(
        self,
        llm_client: Any | None = None,
        rule_based_planner: RuleBasedPlanner | None = None,
        skill_registry: SkillRegistry | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.rule_based_planner = rule_based_planner or RuleBasedPlanner(skill_registry=skill_registry)
        self.skill_registry = skill_registry
        self.prompt_path = Path(prompt_path) if prompt_path else _DEFAULT_PLANNER_PROMPT

    def plan(self, case: NaturalLanguageTestCase) -> ExecutionPlan:
        if self.llm_client is not None and hasattr(self.llm_client, "json_call"):
            llm_plan = self._plan_with_llm(case)
            if llm_plan is not None:
                return llm_plan
        return self.rule_based_planner.plan(case)

    def _plan_with_llm(self, case: NaturalLanguageTestCase) -> ExecutionPlan | None:
        navigation_path = self._navigation_path_for(case)
        try:
            prompt = self._planner_prompt(case, navigation_path)
        except (OSError, ValueError):
            return None
        result = self.llm_client.json_call(
            prompt,
            self._schema(),
            context={"stage": "planning", "case_id": case.internal_id},
        )
        if not isinstance(result, dict) or result.get("status") != "success":
            return None
        data = result.get("data")
        if not isinstance(data, dict):
            return None
        try:
            plan = self._apply_navigation_path(self._execution_plan_from_dict(data), case, navigation_path)
            return self._apply_stock_detail_locators(plan, case)
        except (KeyError, TypeError, ValueError):
            return None

    def _planner_prompt(self, case: NaturalLanguageTestCase, navigation_path: list[NavigationNode] | None = None) -> str:
        base_prompt = self._base_prompt()
        stock_detail_section = self._stock_detail_prompt_section(case)
        expected_result_section = self._expected_result_rules_section()
        nav_constraint = self._nav_context_section(navigation_path or [])
        return (
            f"{base_prompt}\n\n"
            f"{expected_result_section}\n\n"
            f"{self._navigation_rules_section()}\n\n"
            f"{nav_constraint}\n\n"
            f"{stock_detail_section}\n\n"
            "请将以下自然语言测试用例转换为 ExecutionPlan JSON。\n"
            f"case_id: {case.internal_id}\n"
            f"business_module: {case.business_module}\n"
            f"feature_module: {case.feature_module}\n"
            f"operation_description: {case.operation_description}\n"
            f"expected_result: {case.expected_result}\n"
            f"parameters: {case.parameters}"
        ).strip()

    def _base_prompt(self) -> str:
        if not self.prompt_path.is_file():
            raise FileNotFoundError(f"Planner prompt not found: {self.prompt_path}")
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def _navigation_rules_section(self) -> str:
        return (
            "Navigation actions are resolved by the system via skills/navigation/nodes.yaml.\n"
            "Rules:\n"
            "1. Do not generate intent='navigate'.\n"
            "2. Allowed intents: observe, tap, swipe, text, keyevent.\n"
            "3. Before leaving a key page, observe it, then tap, then observe the new page.\n"
            "4. If the case only verifies the current page, observe without leaving it.\n"
            "5. Tap targets must be visible, real UI text."
        )

    def _nav_context_section(self, navigation_path: list[NavigationNode]) -> str:
        """构建导航上下文提示，告知 LLM 当前页面和执行规则。"""
        if not navigation_path:
            return "Navigation context: no deterministic path matched."
        path_text = " -> ".join(node.text for node in navigation_path)
        return (
            "Navigation skill matched path.\n"
            f"current_page: {navigation_path[-1].text}\n"
            f"path: {path_text}"
        )

    def _stock_detail_prompt_section(self, case: NaturalLanguageTestCase) -> str:
        context = self._navigation_context_for(case)
        if self.skill_registry is None or not self.skill_registry.is_stock_detail_context(context):
            return (
                "Stock detail skill: not applicable. Only use this skill for page-local actions on "
                "an individual stock detail/fenshi page."
            )
        element = self.skill_registry.match_stock_detail_element(context)
        if element is None:
            return (
                "Stock detail skill applies to this individual stock detail/fenshi page case, but no exact "
                "page-local element matched. Do not invent a resource_id."
            )
        locator_text = ", ".join(f"{item.type}={item.value}" for item in element.locators) or "none"
        return (
            "Stock detail skill applies to page-local actions on the individual stock detail/fenshi page. "
            "Use stable element IDs and emit the ordered locators supplied by the skill; resource_id is "
            "preferred for icon-only controls.\n"
            f"- {element.element_id}: text={element.text}, aliases={list(element.aliases)}, "
            f"locators=[{locator_text}]"
        )

    def _expected_result_rules_section(self) -> str:
        """加载并注入预期结果解读规则到 LLM prompt。

        让 LLM 在生成 VerificationGoal 时遵循项目约定的验证规则：
        - 跳转成功 → expected_entities 填入目标页面名（如"上证A股"）
        - 交易成功 → expected_entities 填入订单标识关键词
        - 排序 → 使用 ELEMENT_ORDER 类别，expected_entities 填入顺序实体
        - 市场代码 → 使用 DATA_CORRECTNESS 类别，expected_entities 填入市场名
        """
        if self.skill_registry is None:
            return ""
        rules_path = self.skill_registry.skills_root / "expected_result_rules" / "SKILL.md"
        if not rules_path.exists():
            raise FileNotFoundError(f"Expected-result rules not found: {rules_path}")
        rules_text = rules_path.read_text(encoding="utf-8").strip()
        if not rules_text:
            raise ValueError(f"Expected-result rules are empty: {rules_path}")
        return (
            "以下是预期结果的解读规则（来自 skills/expected_result_rules），"
            "请严格遵循这些规则来生成 verification_goals：\n\n"
            f"{rules_text}\n\n"
            "在生成 VerificationGoal 时：\n"
            '- 跳转验证：category="page_navigation"，expected_entities 填入预期跳转到的页面名称（如"上证A股"）\n'
            '- 交易/委托验证：category="popup_display"，expected_entities 填入 ["订单号", "订单编号", "委托编号"]\n'
            '- 排序验证：category="element_order"，expected_entities 填入预期顺序的实体列表\n'
            '- 市场代码验证：category="data_correctness"，expected_entities 填入市场名称（如"上证A股"）\n'
            '- 数据展示完整性：category="data_correctness"，expected_entities 填入页面标识实体'
            '（如页面标题"上证A股"、指数名称如"上证指数"、或股票代码如"600000"）。'
            '不要填列名/表头（"代码""名称""最新""涨幅"）。'
            'review_reason="data_display_completeness"，human_review_required=false\n'
            '- 跨页面实体一致性：category="data_correctness"，expected_entities 填入要对比的实体，'
            '在 review_reason 中注明 "cross_page_consistency"\n'
            '- 通用文本存在验证：category="text_present"，expected_entities 填入要检测的文本\n'
            "所有 verification_goals 的 evidence_priority 统一为 "
            '["poco_tree", "ocr_text", "screenshot"]'
        )

    def _navigation_path_for(self, case: NaturalLanguageTestCase) -> list[NavigationNode]:
        if self.skill_registry is None:
            return []
        return self.skill_registry.resolve_navigation_path(self._navigation_context_for(case))

    def _navigation_context_for(self, case: NaturalLanguageTestCase) -> str:
        parts = [
            case.business_module,
            case.feature_module,
            case.feature_item,
            case.step_name,
            case.operation_description,
        ]
        return " ".join(str(part).strip() for part in parts if str(part).strip())

    def _navigation_prompt_section(self, navigation_path: list[NavigationNode]) -> str:
        if not navigation_path:
            return (
                "Navigation skill: no deterministic navigation path matched this case. "
                "If navigation actions are needed, use visible UI text and keep actions low risk."
            )
        path_text = " -> ".join(node.text for node in navigation_path)
        node_rules = "\n".join(
            f"- {node.node_id}: text={node.text}, aliases={list(node.aliases)}"
            for node in navigation_path
        )
        return (
            "Navigation skill matched path. Use this exact path for leading navigation actions; "
            "do not invent menu names outside these nodes.\n"
            f"path: {path_text}\n"
            f"nodes:\n{node_rules}"
        )

    def _apply_navigation_path(
        self,
        plan: ExecutionPlan,
        case: NaturalLanguageTestCase,
        navigation_path: list[NavigationNode],
    ) -> ExecutionPlan:
        if not navigation_path:
            return plan

        navigation_actions = [
            PlanAction(
                action_id=f"a{index}",
                intent="navigate",
                description=f"进入{node.text}",
                target=node.text,
                target_context=case.operation_description,
                preferred_locator="poco_semantic",
                action_risk_level=ActionRiskLevel.LOW,
                interpretation_rationale_ids=[f"ir_navigation_{node.node_id}"],
            )
            for index, node in enumerate(navigation_path, start=1)
        ]
        remaining_actions = [
            action for action in plan.actions if action.intent != "navigate"
        ]
        renumbered_actions = _renumber_actions([*navigation_actions, *remaining_actions])
        rationales = _merge_rationales(
            plan.interpretation_rationales,
            self._navigation_rationales_for(case, navigation_path),
        )
        notes = list(plan.manual_review_notes)
        note = "LLM plan navigation actions normalized by skills/navigation nodes.yaml."
        if note not in notes:
            notes.append(note)
        return replace(
            plan,
            actions=renumbered_actions,
            manual_review_notes=notes,
            interpretation_rationales=rationales,
        )

    def _apply_stock_detail_locators(
        self,
        plan: ExecutionPlan,
        case: NaturalLanguageTestCase,
    ) -> ExecutionPlan:
        if self.skill_registry is None:
            return plan
        case_context = self._navigation_context_for(case)
        if not self.skill_registry.is_stock_detail_context(case_context):
            return plan

        actions: list[PlanAction] = []
        matched_elements: dict[str, Any] = {}
        for action in plan.actions:
            if action.intent == "navigate":
                actions.append(action)
                continue
            element = self.skill_registry.match_stock_detail_element(
                f"{case_context} {action.target_context} {action.target}"
            )
            if element is None or not element.locators:
                actions.append(action)
                continue
            rationale_id = f"ir_stock_detail_{element.element_id}"
            actions.append(
                replace(
                    action,
                    preferred_locator=element.preferred_locator,
                    locators=list(element.locators),
                    interpretation_rationale_ids=_append_unique(
                        action.interpretation_rationale_ids,
                        rationale_id,
                    ),
                )
            )
            matched_elements[element.element_id] = element

        if not matched_elements:
            return plan
        rationales = list(plan.interpretation_rationales)
        for element in matched_elements.values():
            rationale_id = f"ir_stock_detail_{element.element_id}"
            if any(item.rationale_id == rationale_id for item in rationales):
                continue
            rationales.append(
                InterpretationRationale(
                    rationale_id=rationale_id,
                    original_expression=case_context,
                    normalized_meaning=element.text,
                    interpretation_type="stock_detail_element",
                    confidence=0.95,
                    matched_skill_rules=[f"stock_detail_element.{element.element_id}"],
                    basis=f"命中 stock_detail skill 元素 {element.element_id} 的有序定位器。",
                    human_review_required=False,
                )
            )
        notes = _append_unique(
            plan.manual_review_notes,
            "Stock-detail actions enriched from skills/stock_detail/fenshi_elements_1.yaml.",
        )
        return replace(plan, actions=actions, interpretation_rationales=rationales, manual_review_notes=notes)

    def _navigation_rationales_for(
        self,
        case: NaturalLanguageTestCase,
        navigation_path: list[NavigationNode],
    ) -> list[InterpretationRationale]:
        context = self._navigation_context_for(case)
        return [
            InterpretationRationale(
                rationale_id=f"ir_navigation_{node.node_id}",
                original_expression=context,
                normalized_meaning=node.text,
                interpretation_type="navigation_path",
                confidence=0.9,
                matched_skill_rules=[f"navigation_node.{node.node_id}"],
                basis=f"LLM planning constrained by navigation skill node {node.node_id}.",
                human_review_required=False,
            )
            for node in navigation_path
        ]

    def _schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": [
                "case_id",
                "understanding",
                "preconditions",
                "actions",
                "verification_goals",
                "manual_review_notes",
            ],
        }

    def _execution_plan_from_dict(self, data: dict[str, Any]) -> ExecutionPlan:
        self._require_keys(data, self._schema()["required"])
        actions = [self._action_from_dict(item) for item in self._list(data["actions"])]
        goals = [self._goal_from_dict(item) for item in self._list(data["verification_goals"])]
        rationales = [
            self._rationale_from_dict(item)
            for item in self._list(data.get("interpretation_rationales", []))
        ]
        return ExecutionPlan(
            case_id=str(data["case_id"]),
            understanding=str(data["understanding"]),
            preconditions=[self._dict(item) for item in self._list(data["preconditions"])],
            actions=actions,
            verification_goals=goals,
            manual_review_notes=[str(item) for item in self._list(data["manual_review_notes"])],
            interpretation_rationales=rationales,
            llm_used=True,
        )

    def _action_from_dict(self, data: Any) -> PlanAction:
        item = self._dict(data)
        required = ["action_id", "intent", "description", "target", "target_context", "preferred_locator"]
        self._require_keys(item, required)
        risk = item.get("action_risk_level", ActionRiskLevel.LOW)
        return PlanAction(
            action_id=str(item["action_id"]),
            intent=str(item["intent"]),
            description=str(item["description"]),
            target=str(item["target"]),
            target_context=str(item["target_context"]),
            preferred_locator=str(item["preferred_locator"]),
            locators=[
                LocatorCandidate(
                    type=str(locator.get("type", "")),
                    value=locator.get("value"),
                    coordinate_system=str(locator.get("coordinate_system", "")),
                )
                for locator in (self._dict(value) for value in self._list(item.get("locators", [])))
                if locator.get("type") and "value" in locator
            ],
            action_risk_level=ActionRiskLevel(str(risk)),
            interpretation_rationale_ids=[
                str(value) for value in self._list(item.get("interpretation_rationale_ids", []))
            ],
        )

    def _goal_from_dict(self, data: Any) -> VerificationGoal:
        item = self._dict(data)
        required = [
            "goal_id",
            "claim",
            "category",
            "expected_entities",
            "evidence_priority",
            "human_review_required",
            "review_reason",
        ]
        self._require_keys(item, required)
        return VerificationGoal(
            goal_id=str(item["goal_id"]),
            claim=str(item["claim"]),
            category=VerificationGoalCategory(str(item["category"])),
            expected_entities=[str(value) for value in self._list(item["expected_entities"])],
            evidence_priority=[str(value) for value in self._list(item["evidence_priority"])],
            human_review_required=bool(item["human_review_required"]),
            review_reason=str(item["review_reason"]),
        )

    def _rationale_from_dict(self, data: Any) -> InterpretationRationale:
        item = self._dict(data)
        required = [field.name for field in fields(InterpretationRationale)]
        self._require_keys(item, required)
        return InterpretationRationale(
            rationale_id=str(item["rationale_id"]),
            original_expression=str(item["original_expression"]),
            normalized_meaning=str(item["normalized_meaning"]),
            interpretation_type=str(item["interpretation_type"]),
            confidence=float(item["confidence"]),
            matched_skill_rules=[str(value) for value in self._list(item["matched_skill_rules"])],
            basis=str(item["basis"]),
            human_review_required=bool(item["human_review_required"]),
        )

    def _require_keys(self, data: dict[str, Any], keys: list[str]) -> None:
        missing = [key for key in keys if key not in data]
        if missing:
            raise KeyError(f"Missing planning keys: {missing}")

    def _dict(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("Expected object")
        return value

    def _list(self, value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise TypeError("Expected list")
        return value


def _node_texts(nodes: list[NavigationNode]) -> set[str]:
    return {node.text for node in nodes}


def _append_unique(values: list[str], value: str) -> list[str]:
    return values if value in values else [*values, value]


def _renumber_actions(actions: list[PlanAction]) -> list[PlanAction]:
    return [replace(action, action_id=f"a{index}") for index, action in enumerate(actions, start=1)]


def _merge_rationales(
    original: list[InterpretationRationale],
    additions: list[InterpretationRationale],
) -> list[InterpretationRationale]:
    merged = list(original)
    existing_ids = {item.rationale_id for item in merged}
    for item in additions:
        if item.rationale_id not in existing_ids:
            merged.append(item)
            existing_ids.add(item.rationale_id)
    return merged
