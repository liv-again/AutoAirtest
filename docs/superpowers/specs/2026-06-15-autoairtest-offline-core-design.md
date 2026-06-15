# AutoAirtest Offline Core Design

Date: 2026-06-15

Source design: `docs/260614-AI驱动自然语言测试用例执行系统-详细设计.md`

Approved implementation direction: offline core complete, real-device adapters as placeholders.

## 1. Scope

This implementation builds the offline core for the AI-assisted mobile securities app test execution system. The goal is to make the workflow testable in the `torch` conda environment without requiring an Android device, Airtest, Poco, OCR, or an LLM provider.

The first implementation must provide:

- A Python package named `autoairtest`.
- A CLI entry through `python -m autoairtest`.
- Configuration defaults and command-line overrides.
- Natural-language test case models.
- Excel test case loading with normalized empty values and duplicate case IDs.
- Rule-based planning for the seven documented securities app test cases.
- Evidence directory creation and JSON artifact writing.
- Verification logic for order checks, manual-review classification, and run status aggregation.
- HTML report generation.
- A development log that records missing runtime dependencies, skipped Airtest/Poco tests, and features that cannot be verified in the current environment.

The first implementation must not claim real-device execution is complete.

## 2. Runtime Boundary

All verification commands must run through the `torch` conda environment, for example:

```bash
conda run -n torch python -m pytest
conda run -n torch python -m autoairtest run --excel docs/test-cases.xlsx --sheet 需求测试报告 --output-dir runs
```

The current `torch` environment has Python 3.13.2. Initial inspection found:

- Available: `pytest`, `jinja2`
- Missing: `openpyxl`, `PyYAML`, `pydantic`, `airtest`, `poco`

The implementation must avoid importing optional runtime integrations at module import time. Airtest and Poco adapters must degrade cleanly when packages are unavailable.

Airtest/Poco tests are skipped for now because the current environment does not have those packages installed. This must be recorded in `docs/development-log.md` during implementation.

## 3. Architecture

The package is organized around stable offline components and replaceable runtime adapters.

### 3.1 Core Components

- `config`: Built-in defaults, config loading, and CLI override merging. JSON config support is required. YAML support is optional and must fail with a clear message if `PyYAML` is unavailable.
- `models`: Standard-library `dataclasses` and `Enum` definitions for `NaturalLanguageTestCase`, `ExecutionPlan`, `ActionResult`, `VerificationGoal`, `PreliminaryJudgment`, and `RunResult`.
- `excel_loader`: Reads the source workbook, maps columns to `NaturalLanguageTestCase`, converts blank cells to empty strings, and generates stable internal IDs with `__row_N` for duplicate names.
- `agents.planner`: A deterministic rule-based planner for the seven documented cases. It must mark data correctness, two-side consistency, and color-rule checks as requiring human review.
- `agents.verifier`: Verifies ordered text sequences where evidence is available, marks business judgment goals as manual review, and calculates `RunResult` status.
- `tools.evidence_store`: Creates run and case evidence directories and writes JSON artifacts.
- `report.html_report`: Generates `report.html` and `run_summary.json`.
- `orchestrator`: Coordinates config, loading, planning, execution placeholder behavior, verification, evidence writing, and reporting.

### 3.2 Adapter Components

- `tools.airtest_adapter`: Defines the interface for connect, start app, snapshot, touch, swipe, text, and keyevent. If Airtest is unavailable, calls return a clear unavailable result.
- `tools.poco_adapter`: Defines dump, query, exists, click, text, bounds, and attributes. If Poco is unavailable, calls return a clear unavailable result.
- `tools.ocr_adapter`: Placeholder interface for future OCR evidence.
- `tools.llm_client`: Placeholder interface for future LLM JSON calls and validation.

Adapters must not be required for offline tests.

## 4. Data Flow

The CLI `run` command performs this flow:

1. Merge default config, optional config file, and command-line overrides.
2. Load natural-language test cases from Excel.
3. Create `runs/<timestamp>/`.
4. For each test case:
   1. Create `runs/<timestamp>/cases/<case_id>/`.
   2. Write `case.json`.
   3. Generate and write `execution_plan.json`.
   4. Attempt execution through the configured adapter.
   5. In offline mode or when Airtest/Poco are unavailable, record action results as blocked or device unavailable.
   6. Run verifier using available element summary fixtures or empty evidence.
   7. Write `action_results.json`, `verification_result.json`, and `logs.txt`.
5. Write `run_summary.json`.
6. Generate `report.html`.

The evidence structure follows the detailed design:

```text
runs/
└── <timestamp>/
    ├── run_summary.json
    ├── report.html
    └── cases/
        └── <case_id>/
            ├── case.json
            ├── execution_plan.json
            ├── action_results.json
            ├── verification_result.json
            ├── logs.txt
            ├── screenshots/
            ├── element_summaries/
            └── ocr/
```

## 5. Planning Rules

The rule-based planner must cover the seven current cases from the detailed design:

- Domestic index module data correctness
- Domestic index grid navigation
- Domestic index more-button navigation
- Market index data correctness
- Individual stock details bottom index popup with industry sector
- Individual stock details bottom index popup without industry sector
- Watchlist top index popup

The planner must output:

- Ordered actions with stable `action_id`
- `preferred_locator` values such as `poco_semantic`
- Verification goals with category and `human_review_required`
- Manual-review reasons for data correctness, two-side consistency, and color rules

The planner must not generate executable Python code and must not mark market data correctness as an automatic final pass.

## 6. Verification Rules

The verifier must support:

- Element order checks, including "科创综指排第四".
- Required sequence checks for documented index lists.
- Popup or page text checks when evidence text is available.
- Manual-review classification for data correctness, two-side consistency, color rules, and screenshot-only business judgment.
- Run status aggregation:
  - critical action failure -> `blocked`
  - any automatic verification failure -> `fail_preliminary`
  - any manual-review target -> `manual_required`
  - all automatic targets pass and no manual review -> `pass_preliminary`
  - insufficient evidence after execution -> `uncertain`

Preliminary judgments must not use final-verdict language.

## 7. Testing Strategy

Implementation must use TDD. Tests are written before implementation code for each behavior.

Required offline tests:

- Excel field mapping, blank normalization, and duplicate case ID generation.
- Planner contract for the seven documented cases.
- Manual-review classification for market data, two-side consistency, and color rules.
- Element order verification.
- Run status aggregation.
- CLI `init-config`.
- Offline CLI `run` artifact creation.
- HTML report generation.

Airtest and Poco tests must be skipped in the current environment because `airtest` and `poco` are not installed. The skip reason must be explicit in tests and recorded in `docs/development-log.md`.

## 8. Acceptance Criteria

The first implementation is acceptable when:

- `conda run -n torch python -m pytest` passes, excluding explicitly skipped Airtest/Poco integration tests.
- `conda run -n torch python -m autoairtest init-config --output config.template.json` generates a config template.
- Offline `run` creates a run directory with JSON artifacts and an HTML report.
- Data correctness, two-side consistency, and color-rule goals are marked for human review.
- Missing Airtest/Poco dependencies produce clear blocked or unavailable results instead of import crashes.
- `docs/development-log.md` records skipped Airtest/Poco tests and all current implementation gaps.

## 9. Out Of Scope For This Pass

- Installing dependencies into any conda environment.
- Touching or modifying the `base` environment.
- Real Android device execution.
- Real Airtest/Poco integration verification.
- OCR implementation.
- LLM provider integration.
- Excel result write-back.
- Screenshot redaction.
- MCP server exposure.

## 10. Spec Self-Review

Placeholder scan: no unresolved placeholder markers remain.

Internal consistency: the architecture, data flow, testing strategy, and acceptance criteria all describe the same offline-core-first implementation.

Scope check: the design is limited to a single implementation pass and keeps real-device execution out of scope until dependencies and hardware are available.

Ambiguity check: Airtest/Poco behavior is explicit: adapters are implemented as interfaces/placeholders, integration tests are skipped in the current environment, and the gap is recorded in the development log.
