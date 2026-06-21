# Locator Prompt

Return one JSON object with these required keys:

- `normalized_target`
- `locator_candidates`
- `selected_locator`
- `confidence`
- `matched_skill_rules`
- `needs_manual_review`

Prefer Poco semantic locators before coordinate-based operations. Explain candidate selection using available visible text, UI tree attributes, and screenshots.

Do not make final-judgment claims for market data correctness. Sensitive evidence may be redacted, and redaction must not be bypassed or guessed.
