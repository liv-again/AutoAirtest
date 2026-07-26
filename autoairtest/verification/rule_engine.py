"""离线验证规则引擎。

验证规则参考 skills/expected_result_rules/SKILL.md 中的预期结果解读规则：
  - 跳转成功：标题栏文本子串匹配
  - 交易成功/委托成功：弹窗中存在订单标识关键词
  - 排序：相对顺序匹配（无需相邻）
  - 市场代码：股票代码前缀归属验证
  - 数据展示完整性：实体附近是否存在数值字段
  - 数据格式校验：数值字段是否匹配预期格式
  - 跨页面实体一致性：同名实体是否在两个页面均存在
"""

from __future__ import annotations

import re
from typing import Any

from autoairtest.models import (
    PreliminaryJudgment,
    PreliminaryStatus,
    VerificationGoal,
    VerificationGoalCategory,
)
from autoairtest.verification.judgment_policy import JudgmentPolicy

# 交易/委托成功时的订单标识关键词
TRADE_SUCCESS_KEYWORDS: tuple[str, ...] = ("订单号", "订单编号", "委托编号")

# 数据格式校验的正则模式
_FORMAT_PATTERNS: list[tuple[str, str]] = [
    ("price", r"^\d{1,6}\.\d{2}$"),
    ("change_amount", r"^[+-]\d{1,6}\.\d{2}$"),
    ("change_rate", r"^[+-]\d{1,6}\.\d{2}%$"),
    ("volume", r"^\d+(\.\d+)?[万亿]$"),
    ("stock_code", r"^\d{6}$"),
]

# 格式校验的候选值收集模式：匹配任何可能为数值的字符串（含 OCR 误识别）
# OCR 可能把 "0" 识别为 "O"、"o"，"." 识别为 "O"
_FORMAT_CANDIDATE_PATTERN = re.compile(
    r"^[+-]?\d+[.O0o][0-9O0o]*%?$"   # 价格/涨跌额/涨跌幅（含 OCR 误识别）
    r"|^\d{6}$"                         # 股票代码
    r"|^\d+(\.\d+)?[万亿]$"              # 成交额
)

# 数值检测正则（宽松匹配，用于数据展示完整性检查）
_NUMERIC_PATTERN = re.compile(r"[+-]?\d+\.?\d*[%万亿]?")

# DATA_CORRECTNESS 子类型的 review_reason 标识
_REVIEW_REASON_DISPLAY = "data_display_completeness"
_REVIEW_REASON_CROSS_PAGE = "cross_page_consistency"


class RuleEngine:
    """基于结构化界面证据对单个验证目标给出初判。

    可通过 market_code_prefixes 参数注入市场代码前缀映射，
    用于验证股票代码所属市场是否与预期一致。
    """

    def __init__(
        self,
        policy: JudgmentPolicy | None = None,
        market_code_prefixes: dict[str, list[str]] | None = None,
    ) -> None:
        self.policy = policy or JudgmentPolicy()
        self.market_code_prefixes = market_code_prefixes or {}

    def register_market_codes(self, prefixes: dict[str, list[str]]) -> None:
        """注册或更新市场代码前缀映射。"""
        self.market_code_prefixes = {**self.market_code_prefixes, **prefixes}

    def verify(self, goal: VerificationGoal, evidence: dict[str, object]) -> PreliminaryJudgment:
        if goal.human_review_required:
            return self._manual_goal_judgment(goal, evidence)

        visible_texts, evidence_source = self._text_evidence(evidence)
        if goal.category == VerificationGoalCategory.ELEMENT_ORDER:
            conflict = self._conflicting_order_evidence(goal, evidence)
            if conflict:
                return self._conflicting_evidence_judgment(goal, evidence, conflict)
            return self._verify_order(goal, visible_texts, evidence, evidence_source)
        if goal.category in {
            VerificationGoalCategory.PAGE_NAVIGATION,
            VerificationGoalCategory.POPUP_DISPLAY,
            VerificationGoalCategory.TEXT_PRESENT,
        }:
            conflict = self._conflicting_text_presence_evidence(goal, evidence)
            if conflict:
                return self._conflicting_evidence_judgment(goal, evidence, conflict)
            return self._verify_text_presence(goal, visible_texts, evidence, evidence_source)
        if goal.category == VerificationGoalCategory.DATA_CORRECTNESS:
            # 按优先级尝试各自动规则：市场代码 → 数据格式 → 跨页面一致性 → 数据展示完整性
            if self._is_market_code_goal(goal):
                return self._verify_market_code(goal, visible_texts, evidence, evidence_source)
            if self._is_data_format_goal(goal):
                return self._verify_data_format(goal, visible_texts, evidence, evidence_source)
            if self._is_cross_page_goal(goal):
                return self._verify_cross_page_consistency(goal, evidence)
            if self._is_data_display_goal(goal):
                return self._verify_data_display_completeness(goal, visible_texts, evidence, evidence_source)

        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.UNCERTAIN,
            confidence=0.0,
            basis="No offline verifier exists for this goal category.",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
        )

    def _manual_goal_judgment(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
    ) -> PreliminaryJudgment:
        manual_review_reason = self.policy.manual_review_reason_for_goal(goal)
        structured_details = {"category": manual_review_reason} if manual_review_reason else {}
        structured_details |= self._llm_observation_details(goal, evidence, manual_review_reason)
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.MANUAL_REQUIRED,
            confidence=0.0,
            basis=f"{goal.claim} cannot be finalized automatically in MVP.",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=True,
            review_reason=goal.review_reason,
            manual_review_reason=manual_review_reason,
            structured_details=structured_details,
        )

    def _verify_order(
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
    ) -> PreliminaryJudgment:
        """验证相对顺序：预期实体在可见文本中的出现顺序必须一致，但无需相邻。

        根据 expected_result_rules 中的排序规则：只要预期结果中的相对顺序能对
        上就行，无需相邻。预期实体之间可以夹有其他字段。
        """
        missing = [expected for expected in goal.expected_entities if expected not in visible_texts]
        # Filter visible_texts to only expected entities for order comparison.
        # Extra items between expected entities are allowed — per the "相对顺序匹配" rule.
        filtered = [text for text in visible_texts if text in goal.expected_entities]
        structured_details = {
            "expected": goal.expected_entities,
            "observed": visible_texts,
            "filtered_for_order": filtered,
            "missing": missing,
            "evidence_source": evidence_source,
        }
        if missing:
            structured_details |= self._llm_observation_details(goal, evidence, "verification_evidence_gap")
            return self.policy.manual_required(
                goal,
                evidence,
                reason="verification_evidence_gap",
                basis=(
                    "Expected entities are partially missing from the observed evidence; "
                    f"missing={missing}."
                ),
                structured_details=structured_details,
            )

        if not filtered:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="No expected entities found in visible texts for order comparison.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details=structured_details,
            )

        # Check relative order: each expected item's position in filtered list
        # must be strictly increasing.
        positions = [filtered.index(expected) for expected in goal.expected_entities if expected in filtered]
        passed = positions == sorted(positions)
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.PASS if passed else PreliminaryStatus.FAIL,
            confidence=0.82 if passed else 0.88,
            basis=f"Filtered order positions: {positions} (observed total: {len(visible_texts)})",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
            structured_details=structured_details | {"positions": positions},
        )

    def _verify_text_presence(
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
    ) -> PreliminaryJudgment:
        haystack = " ".join(visible_texts)
        expected = goal.expected_entities or [goal.claim]
        if any(item and item in haystack for item in expected):
            status = PreliminaryStatus.PASS
            confidence = 0.78
            basis = "Expected text was found in interface evidence."
        else:
            status = PreliminaryStatus.UNCERTAIN
            confidence = 0.0
            basis = "No matching text evidence was available offline."
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=status,
            confidence=confidence,
            basis=basis,
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
            structured_details={"evidence_source": evidence_source} if status == PreliminaryStatus.PASS else {},
        )

    def _is_market_code_goal(self, goal: VerificationGoal) -> bool:
        """判断验证目标是否属于市场代码验证场景。"""
        if not self.market_code_prefixes:
            return False
        return any(market in goal.claim for market in self.market_code_prefixes)

    def _verify_market_code(
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
    ) -> PreliminaryJudgment:
        """验证页面中出现的股票代码是否属于预期的市场。

        遍历可见文本，提取数字字符串作为候选股票代码，按 market_code_prefixes
        的前缀规则判定所属市场，并与验证目标中声明的预期市场做比对。
        """
        candidate_codes = [t for t in visible_texts if re.fullmatch(r"\d{6}", str(t))]
        if not candidate_codes:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="No stock code candidates found in visible texts.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details={"evidence_source": evidence_source},
            )

        expected_markets = [
            market for market in self.market_code_prefixes
            if market in goal.claim or market in (goal.expected_entities or [])
        ]
        if not expected_markets:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="No market code prefix rules matched for the expected market.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
            )

        matched_markets: dict[str, list[str]] = {}
        for code in candidate_codes:
            for market_name, prefixes in self.market_code_prefixes.items():
                if any(code.startswith(prefix) for prefix in prefixes):
                    matched_markets.setdefault(market_name, []).append(code)
                    break

        all_expected_present = all(m in matched_markets for m in expected_markets)
        basis = (
            f"Matched markets: {list(matched_markets.keys())}, "
            f"expected: {expected_markets}, candidate codes: {candidate_codes}"
        )
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.PASS if all_expected_present else PreliminaryStatus.FAIL,
            confidence=0.75 if all_expected_present else 0.85,
            basis=basis,
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
            structured_details={
                "evidence_source": evidence_source,
                "markets_matched": matched_markets,
                "expected_markets": expected_markets,
            },
        )

    # ── 规则5: 数据展示完整性 ──

    def _is_data_display_goal(self, goal: VerificationGoal) -> bool:
        """通过 review_reason 或 claim 关键词判定是否为数据展示完整性场景。

        LLM planner 按照 expected_result_rules prompt 规范，在生成此类验证目标时
        会将 review_reason 设为 "data_display_completeness"。
        规则型 planner 也通过 claim 中的"展示/显示"关键词来触发。
        """
        if goal.review_reason == _REVIEW_REASON_DISPLAY:
            return True
        if any(kw in goal.claim for kw in ("展示", "显示", "数据展示")):
            return bool(goal.expected_entities)
        return False

    def _verify_data_display_completeness(
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
    ) -> PreliminaryJudgment:
        """验证每个预期实体附近是否存在数值字段。

        根据 expected_result_rules 规则5：在 visible_texts 中定位每个
        expected_entity，向后扫描 1~5 个相邻项，检测是否存在数值。
        全部实体附近均有数值 → pass；任一实体附近无数值 → fail。
        """
        entities = goal.expected_entities or []
        if not entities:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="No expected entities provided for data display check.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details={"evidence_source": evidence_source},
            )

        entity_results: dict[str, list[str]] = {}
        for entity in entities:
            if entity not in visible_texts:
                continue
            idx = visible_texts.index(entity)
            # 向后扫描最多 20 项，覆盖页面标题到数据行的距离
            window = visible_texts[idx + 1 : idx + 21]
            neighbor_numbers = [t for t in window if _NUMERIC_PATTERN.fullmatch(str(t))]
            entity_results[entity] = neighbor_numbers

        missing_entities = [e for e in entities if e not in entity_results]
        empty_entities = [e for e, nums in entity_results.items() if not nums]
        all_have_numbers = not missing_entities and not empty_entities

        structured_details = {
            "expected_entities": entities,
            "entity_neighbor_numbers": entity_results,
            "missing_entities": missing_entities,
            "entities_without_numbers": empty_entities,
            "observed_total": len(visible_texts),
            "evidence_source": evidence_source,
        }

        if all_have_numbers:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.PASS,
                confidence=0.78,
                basis=(
                    f"All {len(entities)} expected entities have numeric data nearby: "
                    f"{ {e: nums[:2] for e, nums in entity_results.items()} }"
                ),
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details=structured_details,
            )
        basis_parts = []
        if missing_entities:
            basis_parts.append(f"missing={missing_entities}")
        if empty_entities:
            basis_parts.append(f"no_numeric_near={empty_entities}")
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.FAIL,
            confidence=0.82,
            basis="; ".join(basis_parts),
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
            structured_details=structured_details,
        )

    # ── 规则6: 数据格式校验 ──

    def _is_data_format_goal(self, goal: VerificationGoal) -> bool:
        """通过 expected_entities 中的格式标识判定是否为数据格式校验场景。

        LLM planner 在生成此类验证目标时，expected_entities 会包含格式类型名
        （如 "price"、"change_rate"）。
        """
        format_names = {name for name, _ in _FORMAT_PATTERNS}
        return any(e in format_names for e in (goal.expected_entities or []))

    def _verify_data_format(
        self,
        goal: VerificationGoal,
        visible_texts: list[str],
        evidence: dict[str, object],
        evidence_source: str,
    ) -> PreliminaryJudgment:
        """校验界面数值字段是否匹配预期格式。

        根据 expected_result_rules 规则6：对可见文本中的数值字段进行格式检查，
        识别 OCR 误识别（如 3867.O3）。只标记不符合格式的异常项，
        不校验数值语义。
        """
        # 从 expected_entities 中提取要校验的格式名
        format_names = [e for e in (goal.expected_entities or [])
                        if e in {name for name, _ in _FORMAT_PATTERNS}]

        # 收集所有候选数值（含 OCR 误识别，如 3867.O3）
        candidates = [t for t in visible_texts if _FORMAT_CANDIDATE_PATTERN.fullmatch(str(t))]
        if not candidates:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="No numeric candidates found in visible texts.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details={"evidence_source": evidence_source},
            )

        # 对每个候选值尝试所有格式
        malformed: dict[str, list[str]] = {}
        for value in candidates:
            value_str = str(value)
            matched_any = False
            for fmt_name, pattern in _FORMAT_PATTERNS:
                if re.fullmatch(pattern, value_str):
                    matched_any = True
                    break
            if not matched_any:
                malformed.setdefault("unrecognized", []).append(value_str)

        structured_details = {
            "candidates": candidates,
            "malformed": malformed,
            "format_names_requested": format_names,
            "evidence_source": evidence_source,
        }

        if not malformed:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.PASS,
                confidence=0.80,
                basis=f"All {len(candidates)} numeric candidates match known data formats.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details=structured_details,
            )

        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.FAIL,
            confidence=0.85,
            basis=f"Malformed numeric values detected: {malformed}",
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
            structured_details=structured_details,
        )

    # ── 规则7: 跨页面实体一致性 ──

    def _is_cross_page_goal(self, goal: VerificationGoal) -> bool:
        """通过 review_reason 判定是否为跨页面实体一致性场景。"""
        return goal.review_reason == _REVIEW_REASON_CROSS_PAGE

    def _verify_cross_page_consistency(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
    ) -> PreliminaryJudgment:
        """验证同名实体在两个页面中均存在。

        根据 expected_result_rules 规则7：从 current_page_evidence 和
        cross_page_evidence 中分别定位 expected_entity。
        两侧均存在 → pass；一侧缺失 → fail；交叉页证据未采集 → uncertain。
        """
        entities = goal.expected_entities or []
        if not entities:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="No expected entities provided for cross-page check.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
            )

        # 当前页证据
        current_texts, current_source = self._text_evidence(evidence)

        # 交叉页证据
        cross_evidence = evidence.get("cross_page_evidence")
        if not isinstance(cross_evidence, dict):
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.UNCERTAIN,
                confidence=0.0,
                basis="Cross-page evidence not collected; cannot verify entity consistency.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details={"current_source": current_source},
            )

        cross_texts, cross_source = self._text_evidence(cross_evidence)

        results: dict[str, dict[str, bool]] = {}
        for entity in entities:
            current_present = entity in current_texts or entity in " ".join(current_texts)
            cross_present = entity in cross_texts or entity in " ".join(cross_texts)
            results[entity] = {
                "current_page": current_present,
                "cross_page": cross_present,
            }

        missing_current = [e for e, r in results.items() if not r["current_page"]]
        missing_cross = [e for e, r in results.items() if not r["cross_page"]]

        structured_details = {
            "entity_results": results,
            "current_source": current_source,
            "cross_source": cross_source,
        }

        if not missing_current and not missing_cross:
            return PreliminaryJudgment(
                goal_id=goal.goal_id,
                preliminary_status=PreliminaryStatus.PASS,
                confidence=0.75,
                basis=f"All {len(entities)} entities found in both current and cross-page evidence.",
                evidence_files=list(evidence.get("evidence_files", [])),
                human_review_required=False,
                review_reason="",
                structured_details=structured_details,
            )

        failed_reasons = []
        if missing_current:
            failed_reasons.append(f"missing_in_current={missing_current}")
        if missing_cross:
            failed_reasons.append(f"missing_in_cross={missing_cross}")
        return PreliminaryJudgment(
            goal_id=goal.goal_id,
            preliminary_status=PreliminaryStatus.FAIL,
            confidence=0.82,
            basis="; ".join(failed_reasons),
            evidence_files=list(evidence.get("evidence_files", [])),
            human_review_required=False,
            review_reason="",
            structured_details=structured_details,
        )

    def _text_evidence(self, evidence: dict[str, object]) -> tuple[list[str], str]:
        visible_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
        if visible_texts:
            return visible_texts, "poco_tree"
        ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
        if ocr_texts:
            return ocr_texts, "ocr_text"
        return [], "none"

    def _conflicting_order_evidence(self, goal: VerificationGoal, evidence: dict[str, object]) -> dict[str, Any]:
        poco_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
        ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
        if not poco_texts or not ocr_texts:
            return {}

        poco_status = self._order_status(goal.expected_entities, poco_texts)
        ocr_status = self._order_status(goal.expected_entities, ocr_texts)
        if poco_status == ocr_status:
            return {}
        return {
            "expected": goal.expected_entities,
            "poco_observed": poco_texts,
            "ocr_observed": ocr_texts,
            "poco_status": poco_status,
            "ocr_status": ocr_status,
        }

    def _conflicting_text_presence_evidence(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
    ) -> dict[str, Any]:
        poco_texts = [str(item) for item in evidence.get("visible_texts", []) if str(item)]
        ocr_texts = [str(item) for item in evidence.get("ocr_texts", []) if str(item)]
        if not poco_texts or not ocr_texts:
            return {}

        expected = goal.expected_entities or [goal.claim]
        poco_status = self._text_presence_status(expected, poco_texts)
        ocr_status = self._text_presence_status(expected, ocr_texts)
        if poco_status == ocr_status:
            return {}
        return {
            "expected": expected,
            "poco_observed": poco_texts,
            "ocr_observed": ocr_texts,
            "poco_status": poco_status,
            "ocr_status": ocr_status,
        }

    def _order_status(self, expected_entities: list[str], observed_texts: list[str]) -> str:
        missing = [expected for expected in expected_entities if expected not in observed_texts]
        unexpected = [text for text in observed_texts if text not in expected_entities]
        if missing or unexpected:
            return "gap"
        positions = [observed_texts.index(expected) for expected in expected_entities]
        return "pass" if positions == sorted(positions) else "fail"

    def _text_presence_status(self, expected_entities: list[str], observed_texts: list[str]) -> str:
        haystack = " ".join(observed_texts)
        return "pass" if any(item and item in haystack for item in expected_entities) else "uncertain"

    def _conflicting_evidence_judgment(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
        structured_details: dict[str, Any],
    ) -> PreliminaryJudgment:
        structured_details |= self._llm_observation_details(goal, evidence, "conflicting_evidence")
        return self.policy.manual_required(
            goal,
            evidence,
            reason="conflicting_evidence",
            basis="Poco and OCR evidence disagree; human review is required.",
            structured_details=structured_details,
        )

    def _llm_observation_details(
        self,
        goal: VerificationGoal,
        evidence: dict[str, object],
        manual_review_reason: str,
    ) -> dict[str, Any]:
        if not evidence.get("llm_preliminary_judgment", False):
            return {}
        client = evidence.get("llm_client")
        if client is None or not hasattr(client, "json_call"):
            return {}

        visible_texts, evidence_source = self._text_evidence(evidence)
        prompt = (
            "你是移动 App 测试结果初判器。只生成观察摘要，不要给最终通过结论。\n"
            "请返回包含以下字段的 JSON 对象：\n"
            f'  "observation_summary": "观察到的证据摘要",\n'
            f'  "manual_review_reason": "需要人工复核的原因，若无则为空字符串"\n'
            f"验证目标: {goal.claim}\n"
            f"目标类别: {goal.category.value}\n"
            f"人工复核原因: {manual_review_reason}\n"
            f"证据来源: {evidence_source}\n"
            f"可见文本: {visible_texts}\n"
            f"证据文件: {list(evidence.get('evidence_files', []))}"
        )
        schema = {"type": "object", "required": ["observation_summary", "manual_review_reason"]}
        result = client.json_call(prompt, schema)
        status = str(result.get("status", "unknown"))
        details: dict[str, Any] = {"llm_status": status}
        if status == "success":
            data = result.get("data", {})
            if isinstance(data, dict):
                details["llm_observation_summary"] = str(data.get("observation_summary", ""))
                details["llm_manual_review_reason"] = str(data.get("manual_review_reason", ""))
            details["llm_attempts"] = int(result.get("attempts", 0) or 0)
        elif status != "unavailable":
            details["llm_reason"] = str(result.get("reason", ""))
        return details
