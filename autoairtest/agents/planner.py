"""规则型执行计划生成器。

本模块以确定性规则替代 LLM 规划，覆盖当前证券 App 测试样例中的高频语义模式。
这种实现便于离线验证，也为后续接入 LLM Planner 提供稳定输出合同。
"""

from __future__ import annotations

import re

from autoairtest.models import (
    ActionRiskLevel,
    ExecutionPlan,
    InterpretationRationale,
    NaturalLanguageTestCase,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)


# 以下顺序常量来自需求文档中的业务预期，用于生成顺序类验证目标。
DEFAULT_DOMESTIC_ORDER = ["上证指数", "深证成指", "北证50", "科创综指"]
DETAIL_WITH_INDUSTRY_ORDER = ["行业板块", "上证指数", "深证成指", "科创综指", "北证50", "创业板指"]
DETAIL_WITHOUT_INDUSTRY_ORDER = ["上证指数", "深证成指", "科创综指", "北证50", "创业板指"]


class RuleBasedPlanner:
    """把自然语言测试用例转换为结构化执行计划的规则型规划器。"""

    def plan(self, case: NaturalLanguageTestCase) -> ExecutionPlan:
        """生成执行计划。

        当前版本只做语义拆解，不生成 Python 脚本，也不承诺行情数据自动最终正确。
        """

        return ExecutionPlan(
            case_id=case.internal_id,
            preconditions=[
                {
                    "type": "app_state",
                    "description": case.precondition or "App 已登录并位于可进入行情页的状态",
                    "mvp_handling": "manual_prepare_or_precheck",
                }
            ],
            actions=self._actions_for(case.operation_description),
            verification_goals=self._goals_for(case),
            notes=["Rule-based offline plan; no Python code generated."],
            interpretation_rationales=self._rationales_for(case.operation_description),
        )

    def _actions_for(self, operation: str) -> list[PlanAction]:
        """从操作描述中抽取导航、点击或观察动作。"""

        targets: list[tuple[str, str, str, list[str]]] = []
        if "行情" in operation:
            targets.append(("navigate", "进入行情页", "行情", ["ir_market"]))
        if "股指" in operation:
            targets.append(("navigate", "进入股指区域", "股指", ["ir_stock_index"]))
        if "A股" in operation or "沪深京" in operation:
            targets.append(("navigate", "进入A股沪深京区域", "沪深京", ["ir_a_share"]))
        if operation.startswith("自选") or "自选：" in operation or "自选-" in operation:
            targets.append(("navigate", "进入我的自选区域", "我的自选", ["ir_self_selected"]))
        if "国内指数" in operation:
            targets.append(("navigate", "进入国内指数区域", "国内指数", ["ir_domestic_index"]))
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
        swipe_direction = _extract_swipe_direction(operation)
        if swipe_direction:
            targets.append(("swipe", "滑动当前页面", swipe_direction, ["ir_swipe"]))
        input_text = _extract_input_text(operation)
        if input_text:
            targets.append(("text", "输入文本", input_text, ["ir_text_input"]))
        if "返回" in operation:
            targets.append(("keyevent", "返回上一页", "BACK", ["ir_back"]))
        if not targets:
            targets.append(("observe", "观察当前页面", "当前页面", ["ir_current_page"]))

        return [
            PlanAction(
                action_id=f"a{index}",
                intent=intent,
                description=description,
                target=target,
                target_context=operation,
                preferred_locator="poco_semantic",
                action_risk_level=ActionRiskLevel.LOW,
                interpretation_rationale_ids=rationale_ids,
            )
            for index, (intent, description, target, rationale_ids) in enumerate(targets, start=1)
        ]

    def _rationales_for(self, operation: str) -> list[InterpretationRationale]:
        """生成当前规则 planner 能解释的结构化依据。"""

        rationales: list[InterpretationRationale] = []
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
        """从预期结果和操作描述中抽取验证目标。"""

        text = f"{case.expected_result} {case.operation_description}"
        goals: list[VerificationGoal] = []

        if "跳转" in text:
            goals.append(self._goal("页面跳转符合预期", VerificationGoalCategory.PAGE_NAVIGATION))
        if "弹框" in text:
            goals.append(self._goal("指数分时图弹框展示", VerificationGoalCategory.POPUP_DISPLAY))
        if "排第四" in text or "第四位" in text:
            goals.append(
                self._goal(
                    "科创综指排在第四位",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DEFAULT_DOMESTIC_ORDER,
                )
            )
        if "行业板块" in text:
            goals.append(
                self._goal(
                    "有行业板块时指数顺序正确",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DETAIL_WITH_INDUSTRY_ORDER,
                )
            )
        elif "上证指数、深证成指、科创综指、北证50、创业板指" in text:
            goals.append(
                self._goal(
                    "无行业板块时指数顺序正确",
                    VerificationGoalCategory.ELEMENT_ORDER,
                    expected_entities=DETAIL_WITHOUT_INDUSTRY_ORDER,
                )
            )
        if "数据" in text or "一致" in text:
            # 行情数据正确性缺少外部 Oracle，MVP 中必须进入人工复核。
            goals.append(
                self._goal(
                    "行情数据正确性或两端一致性需要人工复核",
                    VerificationGoalCategory.DATA_CORRECTNESS,
                    human_review_required=True,
                    review_reason="market data correctness requires human review",
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
