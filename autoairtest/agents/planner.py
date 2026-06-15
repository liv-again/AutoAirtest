from __future__ import annotations

from autoairtest.models import (
    ExecutionPlan,
    NaturalLanguageTestCase,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)


DEFAULT_DOMESTIC_ORDER = ["上证指数", "深证成指", "北证50", "科创综指"]
DETAIL_WITH_INDUSTRY_ORDER = ["行业板块", "上证指数", "深证成指", "科创综指", "北证50", "创业板指"]
DETAIL_WITHOUT_INDUSTRY_ORDER = ["上证指数", "深证成指", "科创综指", "北证50", "创业板指"]


class RuleBasedPlanner:
    def plan(self, case: NaturalLanguageTestCase) -> ExecutionPlan:
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
        )

    def _actions_for(self, operation: str) -> list[PlanAction]:
        targets: list[tuple[str, str, str]] = []
        if "行情" in operation:
            targets.append(("navigate", "进入行情页", "行情"))
        if "股指" in operation:
            targets.append(("navigate", "进入股指区域", "股指"))
        if "A股" in operation or "沪深京" in operation:
            targets.append(("navigate", "进入A股沪深京区域", "沪深京"))
        if "国内指数" in operation:
            targets.append(("navigate", "进入国内指数区域", "国内指数"))
        if "更多" in operation:
            targets.append(("tap", "点击右侧更多按钮", "更多"))
        if "科创综指" in operation and "点击" in operation:
            targets.append(("tap", "点击科创综指", "科创综指"))
        if "底部指数" in operation:
            targets.append(("tap", "点击底部指数入口", "底部指数"))
        if "自选顶部指数" in operation:
            targets.append(("tap", "点击自选顶部指数", "自选顶部指数"))
        if not targets:
            targets.append(("observe", "观察当前页面", "当前页面"))

        return [
            PlanAction(
                action_id=f"a{index}",
                intent=intent,
                description=description,
                target=target,
                target_context=operation,
                preferred_locator="poco_semantic",
            )
            for index, (intent, description, target) in enumerate(targets, start=1)
        ]

    def _goals_for(self, case: NaturalLanguageTestCase) -> list[VerificationGoal]:
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
            goals.append(
                self._goal(
                    "行情数据正确性或两端一致性需要人工复核",
                    VerificationGoalCategory.DATA_CORRECTNESS,
                    human_review_required=True,
                    review_reason="market data correctness requires human review",
                )
            )
        if "红涨绿跌黑平" in text or "颜色" in text:
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
        return VerificationGoal(
            goal_id="v0",
            claim=claim,
            category=category,
            expected_entities=expected_entities or [],
            evidence_priority=["poco_tree", "ocr_text", "screenshot"],
            human_review_required=human_review_required,
            review_reason=review_reason,
        )
