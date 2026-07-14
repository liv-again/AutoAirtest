# Verifier Prompt

Return one JSON object with the required key:

- `observation_summary` (string) — factual summary of what was observed in the evidence
- `manual_review_reason` (string) — reason manual review is required, or empty string if not

Do NOT include `evidence_gaps` or `confidence` as top-level keys.

Only summarize observed evidence. Do not produce final pass/fail claims for market data correctness, quote values, cross-terminal consistency, or color-rule correctness.

Sensitive evidence may be redacted. Treat redacted values as unavailable evidence and request human review when they are needed.
