import json

from autoairtest.execution.device_workflow import DeviceWorkflow
from autoairtest.models import (
    ActionRiskLevel,
    ActionStatus,
    ExecutionPlan,
    PlanAction,
    VerificationGoal,
    VerificationGoalCategory,
)


class FakeAirtest:
    def __init__(self, available=True, snapshot_results=None, connect_results=None, start_app_results=None):
        self.available = available
        self.snapshot_results = list(snapshot_results or [])
        self.connect_results = list(connect_results or [])
        self.start_app_results = list(start_app_results or [])
        self.connect_calls = 0
        self.start_app_calls = []
        self.snapshots = []
        self.touches = []
        self.swipes = []
        self.texts = []
        self.keyevents = []

    def connect(self):
        self.connect_calls += 1
        if self.connect_results:
            return self.connect_results.pop(0)
        return {"status": "connected" if self.available else "unavailable", "reason": ""}

    def start_app(self, package, activity=""):
        self.start_app_calls.append({"package": package, "activity": activity})
        if self.start_app_results:
            return self.start_app_results.pop(0) | {"package": package, "activity": activity}
        return {"status": "success" if self.available else "unavailable", "package": package, "activity": activity}

    def snapshot(self, filename):
        self.snapshots.append(filename)
        if self.snapshot_results:
            result = self.snapshot_results.pop(0)
            return result | {"filename": filename}
        return {"status": "success" if self.available else "unavailable", "filename": filename}

    def touch(self, target):
        self.touches.append(target)
        return {"status": "success" if self.available else "unavailable", "target": target}

    def swipe(self, start, end):
        self.swipes.append({"start": start, "end": end})
        return {"status": "success" if self.available else "unavailable", "start": start, "end": end}

    def text(self, value):
        self.texts.append(value)
        return {"status": "success" if self.available else "unavailable", "text": value}

    def keyevent(self, key):
        self.keyevents.append(key)
        return {"status": "success" if self.available else "unavailable", "key": key}


class FakePoco:
    def __init__(self, available=True, visible_texts=None, click_status_by_text=None, dump_results=None):
        self.available = available
        self.clicks = []
        self.visible_texts = visible_texts or ["行情", "更多"]
        self.click_status_by_text = click_status_by_text or {}
        self.dump_results = list(dump_results or [])
        self.dump_calls = 0

    def dump(self):
        self.dump_calls += 1
        if self.dump_results:
            return self.dump_results.pop(0)
        if not self.available:
            return {"status": "unavailable", "reason": "poco missing", "visible_texts": []}
        return {
            "status": "success",
            "visible_texts": self.visible_texts,
            "elements": [{"text": item} for item in self.visible_texts],
        }

    def click(self, text):
        self.clicks.append(text)
        if text in self.click_status_by_text:
            return {"status": self.click_status_by_text[text], "query": text}
        return {"status": "success" if self.available else "unavailable", "query": text}


class FakeOCR:
    def __init__(self, texts=None):
        self.texts = texts or []
        self.images = []

    def recognize(self, image_path):
        self.images.append(image_path)
        return {"status": "success", "texts": self.texts, "image_path": image_path}


def _plan():
    return ExecutionPlan(
        case_id="TC_device",
        preconditions=[],
        actions=[
            PlanAction(
                action_id="a1",
                intent="tap",
                description="点击更多",
                target="更多",
                target_context="行情-股指",
                preferred_locator="poco_text",
            )
        ],
        verification_goals=[
            VerificationGoal(
                goal_id="v1",
                claim="进入国内指数列表页",
                category=VerificationGoalCategory.PAGE_NAVIGATION,
                expected_entities=["国内指数"],
                evidence_priority=["poco"],
                human_review_required=False,
                review_reason="",
            )
        ],
        notes=[],
    )


def test_device_workflow_success_records_screenshots_and_element_summaries(tmp_path):
    waits = []
    workflow = DeviceWorkflow(
        airtest=FakeAirtest(),
        poco=FakePoco(
            dump_results=[
                {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
                {"status": "success", "visible_texts": ["国内指数"], "elements": [{"text": "国内指数"}]},
            ]
        ),
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: waits.append("waited") or {"stable": True, "attempts": 2}},
        )(),
    )

    results = workflow.execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert waits == ["waited"]
    assert results[0].before_screenshot == "screenshots/001_before_a1.png"
    assert results[0].after_screenshot == "screenshots/001_after_a1.png"
    assert (tmp_path / results[0].element_summary_before).exists()
    assert json.loads((tmp_path / results[0].element_summary_after).read_text(encoding="utf-8"))["visible_texts"] == [
        "国内指数"
    ]
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["trace_id"] == "t1"
    assert trace[0]["trace_type"] == "action"
    assert trace[0]["action_id"] == "a1"
    assert trace[0]["planned_target"] == "更多"
    assert trace[0]["normalized_target"] == "更多"
    assert trace[0]["action_risk_level"] == "low"
    assert trace[0]["before_evidence"] == ["screenshots/001_before_a1.png", "element_summaries/001_before_a1.json"]
    assert trace[0]["after_evidence"] == ["screenshots/001_after_a1.png", "element_summaries/001_after_a1.json"]


def test_device_workflow_unavailable_airtest_skips_explicitly(tmp_path):
    workflow = DeviceWorkflow(airtest=FakeAirtest(available=False), poco=FakePoco())

    results = workflow.execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SKIPPED_DEVICE_UNAVAILABLE
    assert "Airtest/Poco execution is unavailable" in results[0].notes[0]


def test_device_workflow_blocks_when_device_connection_fails_before_actions(tmp_path):
    airtest = FakeAirtest(connect_results=[{"status": "unavailable", "reason": "adb has no device"}])

    results = DeviceWorkflow(airtest=airtest, poco=FakePoco()).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SKIPPED_DEVICE_UNAVAILABLE
    assert airtest.connect_calls == 1
    assert airtest.snapshots == []
    assert airtest.touches == []
    setup = json.loads((tmp_path / "device_setup.json").read_text(encoding="utf-8"))
    assert setup["status"] == "blocked"
    assert setup["connect"]["reason"] == "adb has no device"


def test_device_workflow_retries_app_start_before_executing_actions(tmp_path):
    airtest = FakeAirtest(
        start_app_results=[
            {"status": "unavailable", "reason": "launch timeout"},
            {"status": "success"},
        ]
    )

    results = DeviceWorkflow(
        airtest=airtest,
        poco=FakePoco(
            dump_results=[
                {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
                {"status": "success", "visible_texts": ["国内指数"], "elements": [{"text": "国内指数"}]},
            ]
        ),
        app_config={"package": "com.example.securities", "activity": ".MainActivity"},
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
        retry_config={"default_max_attempts": 2, "default_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert airtest.start_app_calls == [
        {"package": "com.example.securities", "activity": ".MainActivity"},
        {"package": "com.example.securities", "activity": ".MainActivity"},
    ]
    setup = json.loads((tmp_path / "device_setup.json").read_text(encoding="utf-8"))
    assert setup["status"] == "ready"
    assert setup["start_app"]["attempts"] == 2
    assert setup["start_app"]["previous_failures"] == [{"status": "unavailable", "reason": "launch timeout"}]


def test_device_workflow_retries_transient_snapshot_failure(tmp_path):
    airtest = FakeAirtest(
        snapshot_results=[
            {"status": "unavailable", "reason": "snapshot busy"},
            {"status": "success"},
        ]
    )

    results = DeviceWorkflow(
        airtest=airtest,
        poco=FakePoco(
            dump_results=[
                {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
                {"status": "success", "visible_texts": ["国内指数"], "elements": [{"text": "国内指数"}]},
            ]
        ),
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
        retry_config={"default_max_attempts": 2, "default_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert airtest.snapshots[:2] == [
        str(tmp_path / "screenshots/001_before_a1.png"),
        str(tmp_path / "screenshots/001_before_a1.png"),
    ]


def test_device_workflow_skips_when_snapshot_retry_exhausted(tmp_path):
    airtest = FakeAirtest(
        snapshot_results=[
            {"status": "unavailable", "reason": "snapshot busy"},
            {"status": "unavailable", "reason": "snapshot busy"},
        ]
    )

    results = DeviceWorkflow(
        airtest=airtest,
        poco=FakePoco(),
        retry_config={"default_max_attempts": 2, "default_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SKIPPED_DEVICE_UNAVAILABLE
    assert len(airtest.snapshots) == 2
    assert "Airtest/Poco execution is unavailable" in results[0].notes[0]


def test_device_workflow_blocks_high_risk_action_without_touching_device(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco()
    plan = _plan()
    high_risk_action = PlanAction(
        action_id="a_high",
        intent="tap",
        description="确认交易",
        target="确认",
        target_context="交易确认",
        preferred_locator="poco_text",
        action_risk_level=ActionRiskLevel.HIGH,
    )
    plan = ExecutionPlan(
        case_id=plan.case_id,
        preconditions=plan.preconditions,
        actions=[high_risk_action],
        verification_goals=plan.verification_goals,
        notes=plan.notes,
    )
    workflow = DeviceWorkflow(airtest=airtest, poco=poco)

    results = workflow.execute_plan(plan, tmp_path)

    assert results[0].status == ActionStatus.BLOCKED
    assert results[0].before_screenshot == "screenshots/001_before_a_high.png"
    assert results[0].element_summary_before == "element_summaries/001_before_a_high.json"
    assert "High-risk action requires human confirmation" in results[0].notes[0]
    assert airtest.touches == []
    assert poco.clicks == []


def test_device_workflow_blocks_when_login_page_is_detected(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco(visible_texts=["登录", "请输入手机号", "验证码"])

    results = DeviceWorkflow(airtest=airtest, poco=poco).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.BLOCKED
    assert "Login state is not prepared" in results[0].notes[0]
    assert poco.clicks == []
    before_summary = json.loads((tmp_path / results[0].element_summary_before).read_text(encoding="utf-8"))
    assert before_summary["visible_texts"] == ["登录", "[REDACTED]", "验证码"]
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert "login_page_detected" in trace[0]["execution_rationale"]


def test_device_workflow_writes_plan_amendment_for_navigation_alias(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco(
        visible_texts=["首页", "我的自选"],
        click_status_by_text={"自选": "unavailable", "我的自选": "success"},
    )
    plan = _plan()
    alias_action = PlanAction(
        action_id="a_alias",
        intent="tap",
        description="进入自选",
        target="自选",
        target_context="首页底部导航",
        preferred_locator="poco_text",
    )
    plan = ExecutionPlan(
        case_id=plan.case_id,
        preconditions=plan.preconditions,
        actions=[alias_action],
        verification_goals=plan.verification_goals,
        notes=plan.notes,
    )

    results = DeviceWorkflow(airtest=airtest, poco=poco).execute_plan(plan, tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.clicks == ["自选", "我的自选"]
    amendments = json.loads((tmp_path / "plan_amendments.json").read_text(encoding="utf-8"))
    assert amendments == [
        {
            "amendment_id": "pa1",
            "action_id": "a_alias",
            "original_target": "自选",
            "resolved_target": "我的自选",
            "reason": "navigation alias matched current UI evidence",
            "matched_skill_rules": ["navigation_alias.self_selected"],
            "evidence_files": ["element_summaries/001_before_a_alias.json"],
        }
    ]
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["planned_target"] == "自选"
    assert trace[0]["normalized_target"] == "我的自选"
    assert trace[0]["correction_step"]["type"] == "navigation_alias"


def test_device_workflow_blocks_alias_correction_when_low_budget_is_zero(tmp_path):
    poco = FakePoco(
        visible_texts=["首页", "我的自选"],
        click_status_by_text={"自选": "unavailable", "我的自选": "success"},
    )
    plan = _plan()
    alias_action = PlanAction(
        action_id="a_alias",
        intent="tap",
        description="进入自选",
        target="自选",
        target_context="首页底部导航",
        preferred_locator="poco_text",
    )
    plan = ExecutionPlan(
        case_id=plan.case_id,
        preconditions=plan.preconditions,
        actions=[alias_action],
        verification_goals=plan.verification_goals,
        notes=plan.notes,
    )

    results = DeviceWorkflow(
        airtest=FakeAirtest(),
        poco=poco,
        correction_budget={"low": 0, "medium": 1, "high": 0},
    ).execute_plan(plan, tmp_path)

    assert results[0].status == ActionStatus.FAILED
    assert poco.clicks == ["自选"]
    assert not (tmp_path / "plan_amendments.json").exists()
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["correction_step"] is None


def test_device_workflow_uses_ocr_fallback_coordinates_when_poco_click_fails(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco(click_status_by_text={"更多": "unavailable"})
    ocr = FakeOCR(texts=[{"text": "更多", "bounds": [100, 200, 160, 240]}])

    results = DeviceWorkflow(airtest=airtest, poco=poco, ocr=ocr).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.clicks == ["更多"]
    assert airtest.touches == [(130, 220)]
    assert (tmp_path / "ocr" / "001_before_a1.json").exists()
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["normalized_target"] == "更多"
    assert trace[0]["selected_element"]["response"]["source"] == "ocr"
    assert trace[0]["correction_step"] == {
        "type": "ocr_fallback",
        "attempt": 1,
        "target": "更多",
        "touch_point": [130, 220],
        "risk_level": "low",
    }
    assert "ocr/001_before_a1.json" in trace[0]["before_evidence"]


def test_device_workflow_retries_click_when_page_evidence_does_not_change(tmp_path):
    poco = FakePoco(
        dump_results=[
            {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
            {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
            {"status": "success", "visible_texts": ["国内指数"], "elements": [{"text": "国内指数"}]},
        ]
    )

    results = DeviceWorkflow(
        airtest=FakeAirtest(),
        poco=poco,
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
        retry_config={"default_max_attempts": 2, "default_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.clicks == ["更多", "更多"]
    after_summary = json.loads((tmp_path / results[0].element_summary_after).read_text(encoding="utf-8"))
    assert after_summary["visible_texts"] == ["国内指数"]
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["correction_step"]["type"] == "action_retry"
    assert trace[0]["correction_step"]["reason"] == "page_evidence_unchanged"
    assert "click_no_response_retry" in trace[0]["execution_rationale"]


def test_device_workflow_dispatches_swipe_text_and_back_without_click_retry(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco(
        dump_results=[
            {"status": "success", "visible_texts": ["列表"], "elements": [{"text": "列表"}]},
            {"status": "success", "visible_texts": ["列表"], "elements": [{"text": "列表"}]},
            {"status": "success", "visible_texts": ["搜索框"], "elements": [{"text": "搜索框"}]},
            {"status": "success", "visible_texts": ["搜索框"], "elements": [{"text": "搜索框"}]},
            {"status": "success", "visible_texts": ["详情页"], "elements": [{"text": "详情页"}]},
            {"status": "success", "visible_texts": ["详情页"], "elements": [{"text": "详情页"}]},
        ]
    )
    plan = ExecutionPlan(
        case_id="TC_airtest_actions",
        preconditions=[],
        actions=[
            PlanAction(
                action_id="a_swipe",
                intent="swipe",
                description="向上滑动列表",
                target="up",
                target_context="列表页",
                preferred_locator="airtest_swipe",
            ),
            PlanAction(
                action_id="a_text",
                intent="text",
                description="输入股票代码",
                target="600519",
                target_context="搜索框",
                preferred_locator="airtest_text",
            ),
            PlanAction(
                action_id="a_back",
                intent="keyevent",
                description="返回上一页",
                target="BACK",
                target_context="详情页",
                preferred_locator="airtest_keyevent",
            ),
        ],
        verification_goals=[],
        notes=[],
    )

    results = DeviceWorkflow(
        airtest=airtest,
        poco=poco,
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
    ).execute_plan(plan, tmp_path)

    assert [result.status for result in results] == [ActionStatus.SUCCESS, ActionStatus.SUCCESS, ActionStatus.SUCCESS]
    assert airtest.swipes == [{"start": (0.5, 0.8), "end": (0.5, 0.2)}]
    assert airtest.texts == ["600519"]
    assert airtest.keyevents == ["BACK"]
    assert poco.clicks == []
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert [item["selected_element"]["response"]["source"] for item in trace] == ["airtest_swipe", "airtest_text", "airtest_keyevent"]
    assert all(item["correction_step"] is None for item in trace)


def test_device_workflow_observe_action_collects_evidence_without_touching_device(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco(
        dump_results=[
            {"status": "success", "visible_texts": ["国内指数", "科创综指"], "elements": [{"text": "国内指数"}]},
            {"status": "success", "visible_texts": ["国内指数", "科创综指"], "elements": [{"text": "国内指数"}]},
        ]
    )
    plan = ExecutionPlan(
        case_id="TC_observe",
        preconditions=[],
        actions=[
            PlanAction(
                action_id="a_observe",
                intent="observe",
                description="观察国内指数模块",
                target="当前页面",
                target_context="查看国内指数模块数据显示",
                preferred_locator="poco_semantic",
            )
        ],
        verification_goals=[],
        notes=[],
    )

    results = DeviceWorkflow(
        airtest=airtest,
        poco=poco,
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
    ).execute_plan(plan, tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.clicks == []
    assert airtest.touches == []
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["selected_element"]["response"]["source"] == "observe"
    assert "observation_only" in trace[0]["execution_rationale"]


def test_device_workflow_redacts_sensitive_text_in_element_summaries(tmp_path):
    poco = FakePoco(
        dump_results=[
            {
                "status": "success",
                "visible_texts": ["手机号 13800138000", "更多"],
                "elements": [{"text": "资金账号 123456", "label": "更多"}],
            },
            {"status": "success", "visible_texts": ["国内指数"], "elements": [{"text": "资产 1000000"}]},
        ]
    )

    results = DeviceWorkflow(
        airtest=FakeAirtest(),
        poco=poco,
        evidence_config={
            "redact_sensitive_text": True,
            "sensitive_keywords": ["手机号", "资金账号", "资产"],
            "redaction_placeholder": "[REDACTED]",
        },
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.clicks == ["更多"]
    before_summary = json.loads((tmp_path / results[0].element_summary_before).read_text(encoding="utf-8"))
    after_summary = json.loads((tmp_path / results[0].element_summary_after).read_text(encoding="utf-8"))
    assert before_summary["visible_texts"] == ["[REDACTED]", "更多"]
    assert before_summary["elements"][0]["text"] == "[REDACTED]"
    assert before_summary["elements"][0]["label"] == "更多"
    assert after_summary["elements"][0]["text"] == "[REDACTED]"


def test_device_workflow_blocks_without_retry_when_default_attempt_budget_is_one(tmp_path):
    poco = FakePoco(
        dump_results=[
            {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
            {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
        ]
    )

    results = DeviceWorkflow(
        airtest=FakeAirtest(),
        poco=poco,
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
        retry_config={"default_max_attempts": 1, "default_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.BLOCKED
    assert poco.clicks == ["更多"]
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["correction_step"] is None
    assert "page_evidence_unchanged" in trace[0]["execution_rationale"]


def test_device_workflow_retries_transient_poco_dump_failure(tmp_path):
    poco = FakePoco(
        dump_results=[
            {"status": "unavailable", "reason": "ui busy", "visible_texts": []},
            {"status": "success", "visible_texts": ["行情", "更多"], "elements": [{"text": "更多"}]},
            {"status": "success", "visible_texts": ["国内指数"], "elements": [{"text": "国内指数"}]},
        ]
    )

    results = DeviceWorkflow(
        airtest=FakeAirtest(),
        poco=poco,
        stability_waiter_factory=lambda: type(
            "FakeWaiter",
            (),
            {"wait": lambda self: {"stable": True, "attempts": 1}},
        )(),
        retry_config={"poco_dump_max_attempts": 2, "poco_dump_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.dump_calls >= 2
    before_summary = json.loads((tmp_path / results[0].element_summary_before).read_text(encoding="utf-8"))
    assert before_summary["status"] == "success"
    assert before_summary["dump_attempts"] == 2
    assert before_summary["previous_failures"] == [{"status": "unavailable", "reason": "ui busy"}]


def test_device_workflow_degrades_to_ocr_when_poco_dump_keeps_failing(tmp_path):
    airtest = FakeAirtest()
    poco = FakePoco(
        dump_results=[
            {"status": "unavailable", "reason": "ui busy", "visible_texts": []},
            {"status": "unavailable", "reason": "ui busy", "visible_texts": []},
        ]
    )
    ocr = FakeOCR(texts=[{"text": "更多", "bounds": [100, 200, 160, 240]}])

    results = DeviceWorkflow(
        airtest=airtest,
        poco=poco,
        ocr=ocr,
        retry_config={"poco_dump_max_attempts": 2, "poco_dump_interval_seconds": 0},
    ).execute_plan(_plan(), tmp_path)

    assert results[0].status == ActionStatus.SUCCESS
    assert poco.clicks == []
    assert airtest.touches == [(130, 220)]
    before_summary = json.loads((tmp_path / results[0].element_summary_before).read_text(encoding="utf-8"))
    assert before_summary["status"] == "unavailable"
    assert before_summary["dump_attempts"] == 2
    assert before_summary["hierarchy_unreliable"] is True
    trace = json.loads((tmp_path / "execution_trace.json").read_text(encoding="utf-8"))
    assert trace[0]["selected_element"]["response"]["source"] == "ocr"
    assert trace[0]["correction_step"]["type"] == "ocr_fallback"
    assert "poco_dump_unavailable" in trace[0]["execution_rationale"]
