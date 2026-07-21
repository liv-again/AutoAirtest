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
