# Development Log

Date: 2026-06-15

## Implemented

- Initialized the repository and configured `origin` as `https://github.com/liv-again/AutoAirtest.git`.
- Added the approved offline-core design and implementation plan.
- Built the offline Python package skeleton for `autoairtest`.
- Added standard-library data models and JSON serialization.
- Added JSON configuration defaults and `init-config`.
- Added Excel loader helpers and optional `openpyxl` dependency handling.
- Added deterministic planner rules for the documented securities app cases.
- Added verifier logic for order checks and human-review classification.
- Added evidence directory and JSON artifact writing.
- Added optional adapter interfaces for Airtest, Poco, OCR, and LLM.
- Added static HTML report generation and offline CLI run command.

## Skipped In Current Environment

- Airtest integration tests are skipped because `airtest` is not installed in the `torch` conda environment.
- Poco integration tests are skipped because `poco` is not installed in the `torch` conda environment.
- Real Android device execution is not verified because no device and App package configuration were provided.

## Known Gaps

- `openpyxl` is not installed in `torch`, so real workbook loading reports a clear dependency error until the package is installed in that environment.
- YAML config loading requires `PyYAML`, which is not installed in `torch`; JSON config is supported.
- OCR recognition is an interface only.
- LLM planning and verification are interfaces only.
- Excel result write-back is not implemented.
- Screenshot capture and screenshot redaction are not implemented.
- MCP server exposure is not implemented.

## Verification Commands

- `conda run -n torch python -m pytest`
- `conda run -n torch python -m autoairtest init-config --output config.template.json`
- `conda run -n torch python -m autoairtest run --excel docs/test-cases.xlsx --sheet 需求测试报告 --output-dir runs`

---

Date: 2026-07-02

## Fixed

- **CLI config merge bug (`cli.py`)**: CLI overrides (`--app-package`, `--execution-mode`, `--adb-serial`, `--excel`, `--sheet`) no longer blindly override `config.yaml` values with empty defaults. Only non-empty CLI arguments are written into the overrides dict, so config.yaml values survive the merge when the user doesn't explicitly pass those flags.

- **`config.yaml` YAML syntax**: `device` section had JSON-style trailing commas and `True` (Python syntax); fixed to valid YAML (comma-less, lowercase `true`).

- **Activity name format**: Removed `activity` from config; Airtest's `start_app` mis-handled both fully-qualified and dot-prefixed activity names. Letting Airtest auto-discover the main launcher activity (via `monkey`) works correctly.

## Verified

- Real Android device mode (`execution.mode: device`) connects via ADB to serial `10AF6A0D7X0082P`.
- `config.yaml` is correctly auto-discovered and merged, with CLI args only overriding when explicitly provided.
- App `com.hexin.plat.android.WanlianSecurity` is successfully launched via `monkey -p ... LAUNCHER 1`.
- Airtest minicap fails on Android 15 (API 36, symbol mismatch), but automatically falls back to javacap for screenshots.
- Poco service (`com.netease.open.pocoservice`) is started and connected via instrument + port forwarding.
- Device setup, planning, offline execution, verification evidence recollection, and HTML report generation all complete without errors.
- Evidence output directory: `runs/<timestamp>_case/` with full artifact structure (case.json, execution_plan.json, action_results.json, verification_result.json, screenshots, element_summaries, OCR, logs, report.html).

## Known Issues

- **Activity name limitation**: AirtestAdapter passes `activity` to `airtest.core.api.start_app()`, but this version of Airtest concatenates the package name incorrectly when a non-empty activity is provided. Workaround: omit `activity` from config to use automatic launcher detection.
- **minicap incompatibility**: Device is Android 15 (SDK 36); minicap native binary doesn't support the new `SurfaceComposerClient::Transaction` symbol. javacap fallback works but may have performance implications. Requires upstream minicap update.
- **Poco connection retries**: Poco repeatedly connects and reconnects (multiple device object updates visible in log), suggesting UI detection or connection stability issues on this device/OS version. This may affect action execution reliability in device mode.

---

Date: 2026-07-15

## Added

- Registered `skills/stock_detail/fenshi_elements_1.yaml` in `SkillRegistry`, including page-context activation, alias matching, parent-region disambiguation, and ordered locator loading.
- Added stock-detail guidance to both LLM and rule-based planning. Matching page-local actions now carry typed locator candidates and structured rationale IDs.
- Added Android resource-id support to the Poco main locator path. Short IDs use `app.package`, while fully qualified IDs remain unchanged.
- Preserved the existing text-only Poco API and added ordered resource-id-to-text fallback in `Locator`.

## Verification Boundary

- Unit and direct-call tests cover skill registration, planner enrichment, package-qualified resource IDs, missing-package errors, locator fallback, and device-workflow propagation.
- Real resource-id lookup still requires verification against the target App's live Poco hierarchy because resource names can vary by App build.
