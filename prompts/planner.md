# Planner Prompt

Return one JSON object with these required keys:

- `case_id`
- `understanding`
- `preconditions`
- `actions`
- `verification_goals`
- `manual_review_notes`
- `interpretation_rationales`

Each action must include `action_id`, `intent`, `description`, `target`, `target_context`, `preferred_locator`, `action_risk_level`, and `interpretation_rationale_ids`.

Each verification goal must include `goal_id`, `claim`, `category`, `expected_entities`, `evidence_priority`, `human_review_required`, and `review_reason`.

Do not make final-judgment claims for market data correctness. Market data values, cross-terminal consistency, and color rules require human review unless an external oracle is explicitly provided.

Sensitive evidence may be redacted. Do not infer hidden account, asset, or position values from redacted evidence.
