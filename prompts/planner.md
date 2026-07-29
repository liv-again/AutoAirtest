# Planner Prompt

## Multi-Step Cases

When the operation description contains lines prefixed with `步骤N:` (e.g. `步骤1: ...`, `步骤2: ...`), these are sequential steps of the same test case that should be executed in order on the device **without navigating back to the home page between steps**. Each `步骤N预期:` in the expected result corresponds to the verification goal for that step. The LLM should produce a single ExecutionPlan whose actions flow naturally from one step to the next — do NOT insert navigation-to-home or restart-from-top actions between steps.

## Output Schema

Return one JSON object with these required keys:

- `case_id` (string)
- `understanding` (string)
- `preconditions` (array of objects, each with `type`, `description`, `mvp_handling`)
- `actions` (array of action objects)
- `verification_goals` (array of goal objects)
- `manual_review_notes` (array of strings)
- `interpretation_rationales` (array of rationale objects)

Each action must include `action_id` (string), `intent` (string — MUST be one of: `observe`, `tap`, `swipe`, `text`, `keyevent`. Do NOT use any other value), `description` (string), `target` (string), `target_context` (string), `preferred_locator` (string — for observe use empty string `""`, for tap use `poco_semantic`), `locators` (ordered array of objects with `type`, `value`, and optional `coordinate_system`), `action_risk_level` (one of: `low`, `medium`, `high`), and `interpretation_rationale_ids` (array of strings).

When the prompt says the stock-detail skill applies, use it only for page-local actions on the individual stock detail/fenshi page. Copy the supplied ordered locators exactly. Prefer `resource_id` for icon-only controls and never invent a resource ID that is not supplied by the skill.

Each verification goal must include `goal_id` (string), `claim` (string), `category` (one of the values listed below), `expected_entities` (array of strings), `evidence_priority` (array of strings, e.g. `["poco_tree", "ocr_text", "screenshot"]`), `human_review_required` (boolean), and `review_reason` (string).

Each interpretation rationale must include `rationale_id` (string), `original_expression` (string), `normalized_meaning` (string), `interpretation_type` (string), `confidence` (number), `matched_skill_rules` (array of strings), `basis` (string), and `human_review_required` (boolean).

Valid `category` values (use EXACTLY one of these):

- `page_navigation`
- `element_order`
- `popup_display`
- `data_correctness`
- `color_rule`
- `text_present`

Do not make final-judgment claims for market data correctness. Market data values, cross-terminal consistency, and color rules require human review unless an external oracle is explicitly provided. However, data_display_completeness (checking whether entities have numeric data nearby) does NOT require human review — set human_review_required=false for these goals. For expected_entities in data_display_completeness goals, use page identity entities (e.g. page titles, index names, stock codes), NOT column headers like "代码", "名称", "最新", "涨幅".

Sensitive evidence may be redacted. Do not infer hidden account, asset, or position values from redacted evidence.
