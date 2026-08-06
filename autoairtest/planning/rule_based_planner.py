"""规则型执行计划生成器。

本模块以确定性规则替代 LLM 规划，覆盖当前证券 App 测试样例中的高频语义模式。
这种实现便于离线验证，也为后续接入 LLM Planner 提供稳定输出合同。
"""

from __future__ import annotations

import re

from dataclasses import replace
from pathlib import Path

from autoairtest.execution.risk_policy import RiskPolicy
from autoairtest.models import (
    ExecutionPlan,
    InterpretationRationale,
    NaturalLanguageTestCase,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)
from autoairtest.planning.skill_registry import NavigationNode, SkillRegistry


# 以下顺序常量来自需求文档中的业务预期，用于生成顺序类验证目标。
DEFAULT_DOMESTIC_ORDER = ["上证指数", "深证成指", "北证50", "科创综指"]
DETAIL_WITH_INDUSTRY_ORDER = ["行业板块", "上证指数", "深证成指", "科创综指", "北证50", "创业板指"]
DETAIL_WITHOUT_INDUSTRY_ORDER = ["上证指数", "深证成指", "科创综指", "北证50", "创业板指"]


class RuleBasedPlanner:
    """把自然语言测试用例转换为结构化执行计划的规则型规划器。"""

    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        skills_root: str | Path = "skills",
    ) -> None:
        self.skill_registry = skill_registry or SkillRegistry(skills_root)

    def plan(self, case: NaturalLanguageTestCase) -> ExecutionPlan:
        """生成执行计划。

        当前版本只做语义拆解，不生成 Python 脚本，也不承诺行情数据自动最终正确。
        """

        navigation_context = self._navigation_context_for(case)
        navigation_path = self.skill_registry.resolve_navigation_path(navigation_context)
        actions = self._actions_for(case, navigation_path)
        goals = self._goals_for(case)
        return ExecutionPlan(
            case_id=case.internal_id,
            understanding=f"根据操作描述生成 {len(actions)} 个动作，并从预期结果拆出 {len(goals)} 个可验证目标。",
            preconditions=[
                {
                    "type": "app_state",
                    "description": case.precondition or "App 已登录并位于可进入行情页的状态",
                    "mvp_handling": "manual_prepare_or_precheck",
                }
            ],
            actions=actions,
            verification_goals=goals,
            manual_review_notes=["Rule-based offline plan; no Python code generated."],
            interpretation_rationales=self._rationales_for(case, navigation_path),
            llm_used=False,
        )

    def _actions_for(self, case: NaturalLanguageTestCase, navigation_path: list[NavigationNode]) -> list[PlanAction]:
        """从操作描述中抽取导航、点击或观察动作。"""

        operation = case.operation_description
        stock_detail_context = self._navigation_context_for(case)
        stock_detail_element = self.skill_registry.match_stock_detail_element(stock_detail_context)
        targets: list[tuple[str, str, str, list[str]]] = []
        navigation_targets = {node.text for node in navigation_path}
        targets.extend(
            (
                "navigate",
                f"进入{node.text}",
                node.text,
                [f"ir_navigation_{node.node_id}"],
            )
            for node in navigation_path
        )

        def add_legacy_target(
            intent: str,
            description: str,
            target: str,
            rationale_ids: list[str],
        ) -> None:
            if target in navigation_targets:
                return
            targets.append((intent, description, target, rationale_ids))

        if "行情" in operation:
            add_legacy_target("navigate", "进入行情页", "行情", ["ir_market"])
        if "股指" in operation:
            add_legacy_target("navigate", "进入股指区域", "股指", ["ir_stock_index"])
        if "A股" in operation or "沪深京" in operation:
            add_legacy_target("navigate", "进入A股沪深京区域", "沪深京", ["ir_a_share"])
        if operation.startswith("自选") or "自选：" in operation or "自选-" in operation:
            add_legacy_target("navigate", "进入我的自选区域", "我的自选", ["ir_self_selected"])
        if "国内指数" in operation:
            add_legacy_target("navigate", "进入国内指数区域", "国内指数", ["ir_domestic_index"])
        if "更多" in operation:
            targets.append(("tap", "点击右侧更多按钮", "更多", ["ir_more"]))
        if "科创综指" in operation and "点击" in operation:
            targets.append(("tap", "点击科创综指", "科创综指", ["ir_sse_star_index"]))
        if "底部指数" in operation:
            targets.append(("tap", "点击底部指数入口", "底部指数", ["ir_bottom_index"]))
        if "自选顶部指数" in operation:
            targets.append(("tap", "点击自选顶部指数", "自选顶部指数", ["ir_self_selected_top_index"]))
        if "顶部指数" in operation and "自选顶部指数" not in operation:
            targets.append(("tap", "点击顶部指数", "顶部指数", ["ir_top_index"]))
        if stock_detail_element is not None and stock_detail_element.locators and any(
            verb in operation for verb in ["点击", "选择", "查看", "展开", "关闭", "设置"]
        ) and not any(target == stock_detail_element.text for _, _, target, _ in targets):
            rationale_id = f"ir_stock_detail_{stock_detail_element.element_id}"
            targets.append(
                (
                    "tap",
                    f"点击{stock_detail_element.text}",
                    stock_detail_element.text,
                    [rationale_id],
                )
            )
        swipe_direction = _extract_swipe_direction(operation)
        if swipe_direction:
            targets.append(("swipe", "滑动当前页面", swipe_direction, ["ir_swipe"]))
        input_text = _extract_input_text(operation)
        if input_text:
            targets.append(("text", "输入文本", input_text, ["ir_text_input"]))
        if "返回" in operation and not (
            stock_detail_element is not None and stock_detail_element.text == "返回"
        ):
            targets.append(("keyevent", "返回上一页", "BACK", ["ir_back"]))
        if not targets:
            targets.append(("observe", "观察当前页面", "当前页面", ["ir_current_page"]))

        policy = RiskPolicy()
        actions = []
        for index, (intent, description, target, rationale_ids) in enumerate(targets, start=1):
            matched_element = next(
                (
                    node
                    for node in navigation_path
                    if f"ir_navigation_{node.node_id}" in rationale_ids
                ),
                None,
            )
            if matched_element is None and intent != "navigate":
                matched_element = self.skill_registry.match_stock_detail_element(
                    f"{stock_detail_context} {target}"
                )
            if matched_element is None and intent != "navigate":
                matched_element = self.skill_registry.match_non_text_control(f"{stock_detail_context} {target}")
            actions.append(PlanAction(
                action_id=f"a{index}",
                intent=intent,
                description=description,
                target=target,
                target_context=operation,
                preferred_locator=(
                    matched_element.preferred_locator
                    if matched_element is not None and matched_element.locators
                    else "poco_semantic"
                ),
                locators=list(matched_element.locators) if matched_element is not None else [],
                interpretation_rationale_ids=rationale_ids,
            ))
        return [replace(action, action_risk_level=policy.classify(action)) for action in actions]

    def _navigation_context_for(self, case: NaturalLanguageTestCase) -> str:
        """拼接用例上下文，供导航节点匹配使用。"""

        parts = [
            case.business_module,
            case.feature_module,
            case.feature_item,
            case.step_name,
            case.operation_description,
        ]
        return " ".join(str(part).strip() for part in parts if str(part).strip())

    def _rationales_for(
        self,
        case: NaturalLanguageTestCase,
        navigation_path: list[NavigationNode],
    ) -> list[InterpretationRationale]:
        """生成当前规则 planner 能解释的结构化依据。"""

        operation = case.operation_description
        navigation_context = self._navigation_context_for(case)
        rationales: list[InterpretationRationale] = []
        stock_detail_element = self.skill_registry.match_stock_detail_element(navigation_context)
        for node in navigation_path:
            rationales.append(
                InterpretationRationale(
                    rationale_id=f"ir_navigation_{node.node_id}",
                    original_expression=navigation_context,
                    normalized_meaning=node.text,
                    interpretation_type="navigation_path",
                    confidence=0.88,
                    matched_skill_rules=[f"navigation_node.{node.node_id}"],
                    basis=f"命中 navigation skill 节点 {node.node_id}，按父节点回溯生成菜单路径。",
                    human_review_required=False,
                )
            )
        if operation.startswith("自选") or "自选：" in operation or "自选-" in operation:
            rationales.append(
                InterpretationRationale(
                    rationale_id="ir_self_selected",
                    original_expression="自选",
                    normalized_meaning="我的自选",
                    interpretation_type="navigation_alias",
                    confidence=0.92,
                    matched_skill_rules=["navigation_alias.self_selected"],
                    basis="命中证券 App 导航别名规则：自选在当前 UI 中展示为我的自选。",
                    human_review_required=False,
                )
            )

        if stock_detail_element is not None and stock_detail_element.locators:
            rationales.append(
                InterpretationRationale(
                    rationale_id=f"ir_stock_detail_{stock_detail_element.element_id}",
                    original_expression=navigation_context,
                    normalized_meaning=stock_detail_element.text,
                    interpretation_type="stock_detail_element",
                    confidence=0.95,
                    matched_skill_rules=[f"stock_detail_element.{stock_detail_element.element_id}"],
                    basis=(
                        f"命中 stock_detail skill 元素 {stock_detail_element.element_id}，"
                        "使用其有序定位器。"
                    ),
                    human_review_required=False,
                )
            )

        for rationale_id, original, normalized in [
            ("ir_market", "行情", "行情"),
            ("ir_stock_index", "股指", "股指"),
            ("ir_a_share", "A股/沪深京", "沪深京"),
            ("ir_domestic_index", "国内指数", "国内指数"),
            ("ir_more", "右侧更多按钮", "当前模块右侧更多入口"),
            ("ir_sse_star_index", "科创综指", "科创综指"),
            ("ir_bottom_index", "底部指数", "底部指数入口"),
            ("ir_self_selected_top_index", "自选顶部指数", "自选顶部指数"),
            ("ir_top_index", "顶部指数", "顶部指数"),
            ("ir_swipe", "滑动", "滑动当前页面"),
            ("ir_text_input", "输入", "输入文本"),
            ("ir_back", "返回", "返回上一页"),
            ("ir_current_page", "当前页面", "当前页面"),
        ]:
            if original.replace("/沪深京", "") in operation or normalized in operation:
                rationales.append(
                    InterpretationRationale(
                        rationale_id=rationale_id,
                        original_expression=original,
                        normalized_meaning=normalized,
                        interpretation_type="target_normalization",
                        confidence=0.86,
                        matched_skill_rules=[f"planner_rule.{rationale_id.removeprefix('ir_')}"],
                        basis=f"规则型 planner 从操作描述中识别到目标：{normalized}。",
                        human_review_required=False,
                    )
                )
        return rationales

    def _goals_for(self, case: NaturalLanguageTestCase) -> list[VerificationGoal]:
        """从预期结果和操作描述中抽取验证目标。

        验证目标生成策略参考 skills/expected_result_rules/SKILL.md 中的
        预期结果解读规则：跳转成功、交易成功、排序、市场代码。
        """
        text = f"{case.expected_result} {case.operation_description}"
        goals: list[VerificationGoal] = []

        if "跳转" in text:
            goals.append(self._goal("页面跳转符合预期", VerificationGoalCategory.PAGE_NAVIGATION))
        if "弹框" in text or "弹窗" in text:
            goals.append(self._goal("指数分时图弹框展示", VerificationGoalCategory.POPUP_DISPLAY))
        if "交易" in text or "委托" in text:
            # 交易/委托成功：弹窗中应包含订单标识关键词
            goals.append(
                self._goal(
                    "交易或委托成功后弹窗存在订单标识",
                    VerificationGoalCategory.POPUP_DISPLAY,
                    expected_entities=["订单号", "订单编号", "委托编号"],
                )
            )
        if order_entities := self._detect_order_entities(text):
            goals.append(
                self._goal(
                    f"指数/项目顺序正确",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=order_entities,
                )
            )
        if "排第四" in text or "第四位" in text:
            goals.append(
                self._goal(
                    "科创综指排在第四位",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DEFAULT_DOMESTIC_ORDER,
                )
            )
        data_existence_expected = self._is_data_existence_expectation(case.expected_result, goals)
        if not data_existence_expected and self.skill_registry and self.skill_registry.market_codes:
            matched_markets = [m for m in self.skill_registry.market_names() if m in text]
            if matched_markets:
                goals.append(
                    self._goal(
                        f"页面股票代码属于预期市场: {', '.join(matched_markets)}",
                        VerificationGoalCategory.DATA_CORRECTNESS,
                        expected_entities=matched_markets,
                    )
                )
        if data_existence_expected:
            # 项目只验证数据是否存在，不校验数值正确性或一致性，也不因此转人工复核。
            goals.append(
                self._goal(
                    "目标实体及相关数据字段存在",
                    VerificationGoalCategory.DATA_CORRECTNESS,
                    expected_entities=self._data_display_entities(case),
                    human_review_required=False,
                    review_reason="data_display_completeness",
                )
            )
        if "红涨绿跌黑平" in text or "颜色" in text:
            # 颜色规则依赖视觉证据和业务口径，离线核心不作最终裁决。
            goals.append(
                self._goal(
                    "颜色规则需要人工复核",
                    VerificationGoalCategory.COLOR_RULE,
                    human_review_required=True,
                    review_reason="color rule requires human review",
                )
            )
        if not goals:
            goals.append(self._goal("预期结果需要人工确认", VerificationGoalCategory.TEXT_PRESENT))

        return [
            VerificationGoal(
                goal_id=f"v{index}",
                claim=goal.claim,
                category=goal.category,
                expected_entities=goal.expected_entities,
                evidence_priority=goal.evidence_priority,
                human_review_required=goal.human_review_required,
                review_reason=goal.review_reason,
            )
            for index, goal in enumerate(goals, start=1)
        ]

    def _detect_order_entities(self, text: str) -> list[str]:
        """从预期结果文本中检测需要验证顺序的实体列表。

        支持两种模式：
        1. 明确枚举：如“展示指数及顺序为：上证指数、深证成指、北证50”
        2. 预设模板：行业板块/无行业板块的指数顺序
        """
        if "行业板块" in text:
            return list(DETAIL_WITH_INDUSTRY_ORDER)
        order_match = re.search(r"顺序[为是：:]\s*(.+)", text)
        if order_match:
            raw = order_match.group(1)
            entities = re.split(r"[、，,\s]+", raw.strip())
            return [e for e in entities if e]
        if "上证指数、深证成指、科创综指、北证50、创业板指" in text:
            return list(DETAIL_WITHOUT_INDUSTRY_ORDER)
        return []

    def _is_data_existence_expectation(
        self,
        expected_result: str,
        goals: list[VerificationGoal],
    ) -> bool:
        """把数据相关的“正确/一致”等表述降级为存在性检查。"""

        expected = str(expected_result or "")
        if not any(keyword in expected for keyword in ("数据", "一致", "正确", "准确", "正常")):
            return False
        has_explicit_data_semantics = "数据" in expected or "一致" in expected
        if ("颜色" in expected or "红涨绿跌黑平" in expected) and not has_explicit_data_semantics:
            return False
        has_specific_goal = any(
            goal.category
            in {
                VerificationGoalCategory.PAGE_NAVIGATION,
                VerificationGoalCategory.POPUP_DISPLAY,
                VerificationGoalCategory.ELEMENT_ORDER,
                VerificationGoalCategory.COLOR_RULE,
            }
            for goal in goals
        )
        return has_explicit_data_semantics or not has_specific_goal

    def _data_display_entities(self, case: NaturalLanguageTestCase) -> list[str]:
        """选择最具体的业务实体，避免要求多个层级标题附近都必须出现数值。"""

        for value in (case.feature_item, case.feature_module, case.business_module):
            entity = str(value or "").strip()
            if entity:
                return [entity]
        return []

    def _goal(
        self,
        claim: str,
        category: VerificationGoalCategory,
        expected_entities: list[str] | None = None,
        human_review_required: bool = False,
        review_reason: str = "",
    ) -> VerificationGoal:
        """构造验证目标的内部辅助函数。"""

        return VerificationGoal(
            goal_id="v0",
            claim=claim,
            category=category,
            expected_entities=expected_entities or [],
            evidence_priority=["poco_tree", "ocr_text", "screenshot"],
            human_review_required=human_review_required,
            review_reason=review_reason,
        )


def _extract_swipe_direction(operation: str) -> str:
    if any(item in operation for item in ["向上滑动", "上滑"]):
        return "up"
    if any(item in operation for item in ["向下滑动", "下滑"]):
        return "down"
    if any(item in operation for item in ["向左滑动", "左滑"]):
        return "left"
    if any(item in operation for item in ["向右滑动", "右滑"]):
        return "right"
    return ""


def _extract_input_text(operation: str) -> str:
    match = re.search(r"输入[“\"']?([^”\"'，,。；;\s]+)", operation)
    return match.group(1) if match else ""
