# Verifier Prompt

Return one JSON object with the required key:

- `observation_summary` (string) — factual summary of what was observed in the evidence
- `manual_review_reason` (string) — reason manual review is required, or empty string if not

Do NOT include `evidence_gaps` or `confidence` as top-level keys.

Only summarize observed evidence. Do not produce final pass/fail claims for quote values or color-rule correctness.

For expected-result wording such as “正确”, “准确”, “一致”, or “正常”, this project checks only whether the target entity and related data fields are present. Do not compare numeric values, query an external oracle, or request manual review solely because value correctness or consistency cannot be established.

Sensitive evidence may be redacted. Treat redacted values as unavailable evidence and request human review when they are needed.
