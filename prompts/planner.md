# Planner Prompt

Return one JSON object with these required keys:

- `case_id` (string)
- `understanding` (string)
- `preconditions` (array of objects, each with `type`, `description`, `mvp_handling`)
- `actions` (array of action objects)
- `verification_goals` (array of goal objects)
- `manual_review_notes` (array of strings)
- `interpretation_rationales` (array of rationale objects)

Each action must include `action_id` (string), `intent` (string), `description` (string), `target` (string), `target_context` (string), `preferred_locator` (string), `action_risk_level` (one of: `low`, `medium`, `high`), and `interpretation_rationale_ids` (array of strings).

Each verification goal must include `goal_id` (string), `claim` (string), `category` (one of the values listed below), `expected_entities` (array of strings), `evidence_priority` (array of strings, e.g. `["poco_tree", "ocr_text", "screenshot"]`), `human_review_required` (boolean), and `review_reason` (string).

Each interpretation rationale must include `rationale_id` (string), `original_expression` (string), `normalized_meaning` (string), `interpretation_type` (string), `confidence` (number), `matched_skill_rules` (array of strings), `basis` (string), and `human_review_required` (boolean).

Valid `category` values (use EXACTLY one of these):
- `page_navigation`
- `element_order`
- `popup_display`
- `data_correctness`
- `color_rule`
- `text_present`

Do not make final-judgment claims for market data correctness. Market data values, cross-terminal consistency, and color rules require human review unless an external oracle is explicitly provided.

Sensitive evidence may be redacted. Do not infer hidden account, asset, or position values from redacted evidence.
