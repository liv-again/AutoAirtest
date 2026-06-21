# Verifier Prompt

Return one JSON object with these required keys:

- `observation_summary`
- `manual_review_reason`
- `evidence_gaps`
- `confidence`

Only summarize observed evidence. Do not produce final pass/fail claims for market data correctness, quote values, cross-terminal consistency, or color-rule correctness.

Sensitive evidence may be redacted. Treat redacted values as unavailable evidence and request human review when they are needed.
