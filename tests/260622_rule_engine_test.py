"""Rule engine tests — expected result interpretation rules.

Reflects skills/expected_result_rules/SKILL.md:
  - 排序：相对顺序匹配，无需相邻。预期实体之间允许夹有其他字段。
"""

from autoairtest.models import VerificationGoal, VerificationGoalCategory
from autoairtest.verification.rule_engine import RuleEngine


def test_rule_engine_order_relative_match_allows_extra_items():
    """Extra items between expected entities should not cause manual review."""
    goal = VerificationGoal(
        goal_id="v1",
        claim="顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = RuleEngine().verify(goal, {"visible_texts": ["A", "X", "B", "Y", "C"], "evidence_files": []})

    # Extra items ("X", "Y") between expected items are allowed per the
    # "相对顺序匹配" rule — should PASS, not manual_required.
    assert judgment.preliminary_status.value == "pass"
    assert judgment.human_review_required is False


def test_rule_engine_order_missing_items_triggers_manual_review():
    """Missing expected entities should still require manual review."""
    goal = VerificationGoal(
        goal_id="v2",
        claim="顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = RuleEngine().verify(goal, {"visible_texts": ["A", "C"], "evidence_files": []})

    assert judgment.preliminary_status.value == "manual_required"
    assert judgment.manual_review_reason == "verification_evidence_gap"


def test_rule_engine_order_wrong_relative_order_fails():
    """Correct relative order passes, wrong order fails."""
    goal = VerificationGoal(
        goal_id="v3",
        claim="顺序正确",
        category=VerificationGoalCategory.ELEMENT_ORDER,
        expected_entities=["A", "B", "C"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    # Wrong order: A, C, B
    judgment = RuleEngine().verify(goal, {"visible_texts": ["A", "C", "B"], "evidence_files": []})
    assert judgment.preliminary_status.value == "fail"


def test_rule_engine_text_presence_substring_match():
    """Substring match in visible texts should pass."""
    goal = VerificationGoal(
        goal_id="v4",
        claim="检测到订单号",
        category=VerificationGoalCategory.TEXT_PRESENT,
        expected_entities=["订单号"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["委托成功", "订单号: 202607220001", "查看详情"],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "pass"


def test_rule_engine_market_code_prefix_match():
    """Stock codes matching expected market prefixes should pass."""
    engine = RuleEngine(
        market_code_prefixes={
            "上证A股": ["600", "601"],
            "创业板": ["300"],
        }
    )

    goal = VerificationGoal(
        goal_id="v5",
        claim="股票代码属于上证A股",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["上证A股"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = engine.verify(
        goal,
        {
            "visible_texts": ["上证A股", "600519", "行情", "601318", "价格"],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "pass"


# ── 规则5: 数据展示完整性 ──

def test_rule_engine_data_display_completeness_pass():
    """所有预期实体附近均有数值 → pass。"""
    goal = VerificationGoal(
        goal_id="v_display_1",
        claim="国内指数模块数据展示正确",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["上证指数", "深证成指", "北证50"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="data_display_completeness",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": [
                "上证指数", "3867.03", "+2.66", "+0.07%",
                "深证成指", "14061.44", "-202.85", "-1.42%",
                "北证50", "1074.45", "-4.59", "-0.43%",
            ],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "pass"
    assert judgment.structured_details["missing_entities"] == []
    assert judgment.structured_details["entities_without_numbers"] == []


def test_rule_engine_data_display_completeness_entity_without_numbers_fails():
    """任一实体附近无数值 → fail。"""
    goal = VerificationGoal(
        goal_id="v_display_2",
        claim="数据展示正确",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["上证A股", "科创板"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="data_display_completeness",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["上证A股", "600519", "+2.5%", "科创板"],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "fail"
    assert judgment.structured_details["entities_without_numbers"] == ["科创板"]


# ── 规则6: 数据格式校验 ──

def test_rule_engine_data_format_all_valid():
    """所有数值字段匹配已知格式 → pass。"""
    goal = VerificationGoal(
        goal_id="v_format_1",
        claim="数值格式正确",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["price", "change_rate"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["3867.03", "+2.66", "-1.42%", "3.2亿", "600519"],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "pass"


def test_rule_engine_data_format_malformed():
    """OCR 误识别导致格式异常 → fail。"""
    goal = VerificationGoal(
        goal_id="v_format_2",
        claim="数值格式正确",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["price"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["3867.O3", "+2.66", "-1.42%"],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "fail"
    assert "3867.O3" in str(judgment.structured_details.get("malformed", {}))


# ── 规则7: 跨页面实体一致性 ──

def test_rule_engine_cross_page_both_sides_pass():
    """同名实体在两个页面均存在 → pass。"""
    goal = VerificationGoal(
        goal_id="v_cross_1",
        claim="模块数据与个股行情页数据一致",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="cross_page_consistency",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["上证指数", "科创综指", "3867.03"],
            "evidence_files": [],
            "cross_page_evidence": {
                "visible_texts": ["科创综指", "+2.66", "+0.07%"],
            },
        },
    )

    assert judgment.preliminary_status.value == "pass"


def test_rule_engine_cross_page_missing_in_cross():
    """实体在当前页存在但在交叉页缺失 → fail。"""
    goal = VerificationGoal(
        goal_id="v_cross_2",
        claim="数据一致",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="cross_page_consistency",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["科创综指", "3867.03"],
            "evidence_files": [],
            "cross_page_evidence": {
                "visible_texts": ["上证指数", "深证成指"],
            },
        },
    )

    assert judgment.preliminary_status.value == "fail"


def test_rule_engine_cross_page_no_cross_evidence_uncertain():
    """交叉页证据未采集 → uncertain。"""
    goal = VerificationGoal(
        goal_id="v_cross_3",
        claim="数据一致",
        category=VerificationGoalCategory.DATA_CORRECTNESS,
        expected_entities=["科创综指"],
        evidence_priority=["poco_tree"],
        human_review_required=False,
        review_reason="cross_page_consistency",
    )

    judgment = RuleEngine().verify(
        goal,
        {
            "visible_texts": ["科创综指"],
            "evidence_files": [],
        },
    )

    assert judgment.preliminary_status.value == "uncertain"
