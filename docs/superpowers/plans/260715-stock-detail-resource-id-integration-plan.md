# Stock Detail Resource-ID Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the stock-detail skill with both planners and carry its ordered locators into a Poco execution path that supports Android resource-id selectors.

**Architecture:** `SkillRegistry` loads `skills/stock_detail/fenshi_elements_1.yaml` into typed stock-detail elements and decides when a natural-language case is in stock-detail context. Planner actions carry typed locator candidates; deterministic enrichment attaches YAML locators even when an LLM omits them. `Locator` tries candidates in order, while `PocoAdapter` normalizes short Android IDs with `app.package` and executes resource-id or text selectors explicitly.

**Tech Stack:** Python dataclasses, PyYAML, Poco Android UIAutomation adapter, pytest-style tests with direct-call fallback.

---

### Task 1: Add the structured locator contract and stock-detail registry

**Files:**
- Modify: `autoairtest/models.py`
- Modify: `autoairtest/planning/skill_registry.py`
- Test: `tests/260622_skill_registry_test.py`

- [ ] **Step 1: Write failing registry tests**

Cover loading `stock_detail/fenshi_elements_1.yaml`, matching `返回` to `title_back`, preserving locator order, recognizing `个股分时` as the activation context, and disambiguating repeated text by parent context.

- [ ] **Step 2: Run tests and confirm RED**

Run:

```powershell
python -m pytest tests/260622_skill_registry_test.py -q
```

Expected: failure because stock-detail registry fields and matching methods do not exist.

- [ ] **Step 3: Implement the minimal model and loader**

Add immutable locator and stock-detail element data contracts. Load YAML from `skills/stock_detail/fenshi_elements_1.yaml`; expose context activation, element matching, and ordered locator retrieval without changing navigation behavior.

- [ ] **Step 4: Run registry tests and confirm GREEN**

Expected: existing navigation tests and new stock-detail tests pass.

### Task 2: Tell both planners when and how to use stock-detail locators

**Files:**
- Modify: `prompts/planner.md`
- Modify: `autoairtest/planning/planning_agent.py`
- Modify: `autoairtest/planning/rule_based_planner.py`
- Test: `tests/260622_planning_agent_test.py`
- Test: `tests/test_planner_rationales.py`

- [ ] **Step 1: Write failing planner tests**

Assert that a stock-detail case adds a prompt section explaining the skill's page-local scope and resource-id use. Assert that an action targeting `返回` receives the `id/backButton` locator even when the fake LLM omits `locators`. Assert that the rule planner enriches a page-local tap action in the same way.

- [ ] **Step 2: Run tests and confirm RED**

Expected: prompt has no stock-detail section and actions have no locator candidates.

- [ ] **Step 3: Implement deterministic planner enrichment**

Extend `PlanAction` with backward-compatible `locators`. Inject only relevant stock-detail elements into the LLM prompt when the case matches the page context. Parse optional LLM locators, then replace them with registry-owned locators for a matched stable element. Add a `stock_detail_element.<id>` rationale.

- [ ] **Step 4: Run planner tests and confirm GREEN**

Expected: navigation behavior remains unchanged and stock-detail actions carry resource-id candidates.

### Task 3: Add Poco resource-id lookup and ordered locator execution

**Files:**
- Modify: `autoairtest/tools/poco_adapter.py`
- Modify: `autoairtest/execution/locator.py`
- Test: `tests/260621_tool_adapters_test.py`
- Test: `tests/260621_locator_test.py`

- [ ] **Step 1: Write failing adapter and locator tests**

Cover these normalizations:

```text
com.example:id/backButton -> com.example:id/backButton
id/backButton             -> com.example:id/backButton
backButton                -> com.example:id/backButton
```

Verify that Poco receives the full resource-id as its name selector, that missing package is explicit for short IDs, and that ordered locator execution falls back from resource-id to text.

- [ ] **Step 2: Run tests and confirm RED**

Expected: `PocoAdapter` has no resource-id method and `Locator` accepts only text.

- [ ] **Step 3: Implement minimal adapter and locator behavior**

Give `PocoAdapter` the configured package, add explicit resource-id query/click methods, and retain current text methods. Update `Locator.locate_and_act` to accept optional ordered candidates while preserving the old text-only call signature.

- [ ] **Step 4: Run adapter and locator tests and confirm GREEN**

Expected: resource-id and text paths pass; existing callers remain compatible.

### Task 4: Connect device execution and verify regressions

**Files:**
- Modify: `autoairtest/execution/device_workflow.py`
- Test: `tests/test_device_workflow.py`
- Modify: `skills/stock_detail/SKILL.md`
- Modify: `docs/development-log.md`

- [ ] **Step 1: Write a failing device-workflow test**

Build a `PlanAction` with `id/backButton`; assert the workflow passes ordered locators to `Locator` and the Poco fake receives the normalized package-qualified ID.

- [ ] **Step 2: Run the test and confirm RED**

Expected: workflow ignores `PlanAction.locators`.

- [ ] **Step 3: Wire package and locators into execution**

Construct `PocoAdapter(app_package=...)`, pass action locator candidates into `Locator`, and record the actual locator type in the response and trace. Update nearby documentation with the activation and normalization contract.

- [ ] **Step 4: Run targeted and full verification**

Run targeted planner, registry, adapter, locator, and workflow tests. If pytest cannot start because of the known local `pluggy._hooks` issue, run the same test functions directly and report that limitation. Also run:

```powershell
python -m compileall autoairtest tests
git diff --check
```

Expected: all targeted direct tests pass, compilation succeeds, and diff check reports no errors.
