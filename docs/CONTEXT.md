# AutoAirtest

This context defines the language for an AI-assisted mobile securities app test execution system. It keeps test case, execution, evidence, and result terms precise while avoiding implementation-level decisions.

## Language

**Natural-Language Test Case**:
A row from the source test workbook that describes a mobile app verification scenario in business language, including module metadata, an operation description, and an expected result.
_Avoid_: Script, automation code

**Operation Description**:
The user-facing action narrative in a Natural-Language Test Case. It combines the target page path, operation method, and operation object, such as "行情-股指-国内指数：点击右侧更多按钮".
_Avoid_: Step code, locator

**Module Path**:
The business path implied by module metadata in a Natural-Language Test Case, especially Business Module and Feature Module. The Module Path can be cross-checked against the Operation Description before an Execution Plan is accepted.
_Avoid_: Report grouping, menu label

**Navigation Alias**:
A business term or shorthand in a Natural-Language Test Case that refers to a UI entry or page whose visible label may differ, such as "自选" referring to a UI label like "我的自选".
_Avoid_: Exact locator, typo

**Expected Result**:
The observable condition that must hold after the Operation Description is completed, such as page navigation, index ordering, data consistency, color rules, or popup contents.
_Avoid_: Assertion script, screenshot comparison

**Execution Plan**:
A structured interpretation of one Natural-Language Test Case into ordered actions and verification goals. One test case has one Execution Plan; one Execution Plan may contain multiple actions and multiple verification goals.
_Avoid_: Prompt output, generated code

**Execution Trace**:
The append-only record of what actually happened during execution, including selected elements, tool calls, observations, deviations, corrections, and evidence references.
_Avoid_: Updated plan, debug log only

**Plan Amendment**:
An explicit execution-time supplement to an Execution Plan that records how a planned target or action was resolved against real interface evidence without overwriting the original Execution Plan.
_Avoid_: Silent plan mutation, prompt rewrite

**Verification Goal**:
One checkable claim derived from an Expected Result. A single Expected Result can produce multiple Verification Goals, such as "科创综指 is fourth" and "red means rising".
_Avoid_: Assertion line, check item

**Verification Evidence Gap**:
A mismatch between the evidence available for a Verification Goal and the evidence needed to judge it automatically, such as an expected element being missing, an unexpected element appearing in an ordered list, or only a partial ordered sequence being captured.
_Avoid_: Execution failure, automatic fail

**Evidence Recollection**:
A limited verification-stage attempt to collect more Interface Evidence for the same screen or same verification context, such as re-dumping the interface tree, re-running OCR, taking another screenshot, or performing a low-risk scroll to reveal more content.
_Avoid_: Execution correction, new navigation

**Visibility Adjustment**:
A low-risk, reversible action within the same verification context that changes what evidence is visible without changing the business query, target page, or verification object, such as scrolling the current list, horizontally swiping the current region, expanding the current area, collapsing a blocking overlay, or returning to the current verification region.
_Avoid_: Navigation, filtering, object selection

**Interface Evidence**:
Captured information about the current mobile screen used to judge a Verification Goal. Interface Evidence may describe visible text, element hierarchy, element bounds, element state, or visual appearance.
_Avoid_: Raw dump, proof blob

**Screenshot Evidence**:
The mandatory screen image saved during a test run for human review and audit. Every Natural-Language Test Case must have Screenshot Evidence whether automated judgment succeeds or fails.
_Avoid_: Optional screenshot, debug image

**Preliminary Judgment**:
The system-generated judgment produced before human review. It can summarize whether available Interface Evidence appears to satisfy a Verification Goal, but it is not the final authority for data correctness.
_Avoid_: Final verdict, ground truth

**Manual Review Reason**:
The reason category explaining why a Preliminary Judgment requires Human Review, such as data correctness, color rule, verification evidence gap, ambiguous business rule, conflicting evidence, low-confidence interpretation, or high-risk action confirmation.
_Avoid_: Generic needs review, unclear failure note

**Structured Judgment Detail**:
Machine-readable judgment data that explains a Preliminary Judgment beyond the human-readable basis text, such as manual review reason, expected evidence, observed evidence, missing elements, unexpected elements, conflicting evidence, and confidence inputs.
_Avoid_: Report prose, log message

**Human Review**:
The manual review of Screenshot Evidence and Run Result, especially for data correctness and business judgment. Human Review is the authority when a Verification Goal depends on whether market data is correct.
_Avoid_: Manual fallback, visual spot check

**Run Result**:
The final outcome of executing one Natural-Language Test Case, including pass/fail status, failure reason, and evidence references.
_Avoid_: Test result cell, report row

**Test Device**:
The physical Android phone on which Natural-Language Test Cases are executed for the first product version. One test run targets one connected Test Device.
_Avoid_: Emulator, iOS device

**Workflow**:
A controlled sequence of steps that executes a Natural-Language Test Case with predictable ordering, explicit checkpoints, and bounded decision points.
_Avoid_: Free-form agent autonomy, ad hoc loop

**Agent**:
A decision-capable execution subject that can pursue an independent goal, choose among available skills or tools, maintain task state, and take responsibility for an outcome. In this project, only components with that autonomy should be called Agents.
_Avoid_: Any LLM call, any helper module

**Skill**:
A reusable capability package that captures how to perform a class of test-related work, such as navigation knowledge, verification rules, prompt guidance, templates, or helper resources.
_Avoid_: Agent, tool call

**Skill Rule**:
A reusable, testable rule inside a Skill that can guide planning, execution, verification, risk classification, or correction behavior without requiring the system to infer the same knowledge from natural language every time.
_Avoid_: Prompt-only advice, hard-coded one-off condition

**Interpretation Rationale**:
The recorded reason for how a Natural-Language Test Case expression was interpreted, including the original expression, normalized meaning, confidence, evidence, matched Skill Rules, and whether Human Review is required.
_Avoid_: Hidden chain of thought, unexplained mapping

**Execution Rationale**:
The recorded reason for an execution-time decision, including the planned target, normalized target, candidate elements, selected element, confidence, matched Skill Rules, current Interface Evidence, Action Risk Level, and whether a Correction Step was triggered.
_Avoid_: Silent click, unexplained retry

**Tool**:
A callable interface that performs a concrete action or query, such as taking a screenshot, dumping interface evidence, locating an element, or writing evidence files.
_Avoid_: Skill, workflow step

**Guardrail**:
A rule or check that limits unsafe, ambiguous, or low-confidence automation behavior before an action or judgment is accepted.
_Avoid_: Prompt hint, best effort

**Execution Ambiguity**:
Uncertainty discovered during action execution after real interface evidence is collected, such as multiple matching UI elements, changed visible labels, unexpected page state, or a mismatch between the planned target and current screen.
_Avoid_: Planner error, test failure

**Recoverable Misoperation**:
A wrong or unintended action during test execution that can be detected, evidenced, and corrected without causing unacceptable business risk or invalidating the whole run.
_Avoid_: Catastrophic failure, silent success

**Correction Step**:
An explicit recovery action taken after a Recoverable Misoperation or Execution Ambiguity is detected, such as going back, re-locating an element, refreshing interface evidence, or switching to an alternate navigation alias.
_Avoid_: Blind retry, random exploration

**Action Risk Level**:
The business risk classification of a planned or corrective UI action. Low-risk actions may be retried or corrected automatically; medium-risk actions require tighter limits and evidence; high-risk actions require blocking or explicit human confirmation.
_Avoid_: Locator confidence, priority

**Low-Risk Action**:
A UI action that is unlikely to change business data or account state, such as page navigation, tab switching, scrolling, opening a popup, closing a popup, or returning to the previous page.
_Avoid_: Safe action

**Medium-Risk Action**:
A UI action that can change local UI state or query context but is not expected to perform irreversible business operations, such as entering a search term, changing filters, switching markets, or opening a detail page.
_Avoid_: Dangerous action

**High-Risk Action**:
A UI action that may affect account, trading, security, or persistent user data, such as placing an order, cancelling an order, logging out, changing account settings, adding or deleting self-selected items, or confirming a financial operation.
_Avoid_: Normal test step

## Flagged Ambiguities

**Validation**:
In this project, "validation" means judging whether a Verification Goal is satisfied after execution, not locating an element to operate on. Element location belongs to action execution; validation belongs to result judgment.

**Data Correctness**:
In this project, data correctness is not treated as fully automated ground truth in the MVP. The system may provide a Preliminary Judgment, but Human Review of Screenshot Evidence decides whether market data is correct.

**Agent Naming**:
In this project, not every LLM-assisted component is an Agent. A fixed, high-control mobile test execution path is a Workflow; reusable domain knowledge is a Skill; device and evidence operations are Tools; only autonomous goal-directed components should be named Agents.

**Execution-Time Ambiguity**:
Ambiguity can be discovered during execution, not only during planning. The system should use Skills and current Interface Evidence to resolve recoverable ambiguity, while recording the decision and evidence. Low-risk misoperations may be tolerated if they are detected and corrected; silent incorrect progress is not acceptable.

**Risk-Based Execution**:
Execution behavior depends on the Action Risk Level. Low-Risk Actions can use automatic correction; Medium-Risk Actions can use limited correction with stronger evidence; High-Risk Actions must be blocked or require explicit Human Review before proceeding.

**Correction Budget**:
Automatic correction is limited by Action Risk Level. Low-Risk Actions allow up to three Correction Steps; Medium-Risk Actions allow up to one Correction Step; High-Risk Actions allow no automatic Correction Steps and must be blocked or explicitly confirmed by a human.

**Planning Explainability**:
Key planning interpretations must include an Interpretation Rationale. This is required for navigation aliases, target normalization, risk classification, verification goal classification, and any decision that affects whether execution may proceed automatically.

**Execution Explainability**:
Key execution decisions must include an Execution Rationale. This is required for element selection, low-confidence disambiguation, misoperation detection, Correction Steps, and any decision that allows execution to continue after ambiguity or deviation.

**Append-Only Execution Record**:
Execution must not overwrite the original Execution Plan. Execution-time resolution, correction, or deviation must be recorded as Execution Trace entries, Correction Steps, or Plan Amendments so the original test intent remains auditable.

**Order Verification Gap**:
When an ordered Verification Goal expects a sequence such as A-B-C-D but Interface Evidence contains only A-B-C, or contains A-B-C-E, the result should be treated as a Verification Evidence Gap requiring Human Review unless a Skill Rule explicitly defines it as pass or fail. This is a verification-stage judgment, not an execution-stage correction.

**Verification Responsibility Split**:
Verification uses a rule-first, agent-assisted, human-final split. The Rule Engine handles deterministic checks such as complete order matches, explicit order mismatches, text presence, and popup presence. The Verification Agent explains evidence gaps, conflicting evidence, UI wording differences, and Human Review reasons. Human Review remains the final authority for data correctness and domain gray areas.

**Structured Manual Review Data**:
When a Preliminary Judgment requires Human Review, the reason and evidence gap must be recorded as Structured Judgment Detail, not only as basis text. The basis explains the judgment for humans; structured fields support filtering, reporting, statistics, and verifier evaluation.

**Bounded Evidence Recollection**:
Verification may perform Evidence Recollection before returning a Verification Evidence Gap. Evidence Recollection must stay within the same screen or verification context and must not click business actions, navigate to a new page, change filters, or perform medium/high-risk actions.

**Evidence Recollection Budget**:
Evidence Recollection allows up to two attempts by default. The first attempt may refresh current-screen evidence such as interface tree, OCR, and screenshot. The second attempt may use a Visibility Adjustment within the same verification context. If evidence is still incomplete or abnormal after the budget is exhausted, the judgment should require Human Review with a Manual Review Reason such as verification evidence gap.

**Evidence Recollection Trace**:
Every Evidence Recollection action that changes or refreshes Interface Evidence must be recorded in the Execution Trace with its trigger, related Verification Goal, Action Risk Level, before/after evidence references, and whether the evidence gap was resolved.

## Example Dialogue

Developer: "This Natural-Language Test Case says to click 科创综指 and expects a jump to the index time-sharing page. Is that one Verification Goal?"

Domain expert: "Yes, the Operation Description is the click flow. The Expected Result becomes a Verification Goal that the destination page is the 科创综指 time-sharing page."

Developer: "If the Expected Result also says 科创综指 must be fourth in the list, should that be separate?"

Domain expert: "Yes. One Natural-Language Test Case can produce multiple Verification Goals, and the Run Result should identify which goal failed."

Developer: "The Business Module is 股指 and the Feature Module is 国内指数, but the Operation Description says 行情-A股-沪深京. Are those compatible?"

Domain expert: "No. The Module Path and Operation Description point to different target page paths, so the Execution Plan should treat that as a path conflict before running the case."
