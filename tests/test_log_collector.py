from autoairtest.tools.log_collector import LogCollector


JAVA_CRASH = """
06-21 10:30:00.000 1234 1234 E AndroidRuntime: FATAL EXCEPTION: main
06-21 10:30:00.000 1234 1234 E AndroidRuntime: Process: com.example.securities, PID: 1234
06-21 10:30:00.000 1234 1234 E AndroidRuntime: java.lang.NullPointerException: boom
06-21 10:30:00.000 1234 1234 E AndroidRuntime:     at com.example.LoginActivity.onClick(LoginActivity.java:42)
"""


def test_log_collector_returns_unavailable_when_adb_missing():
    collector = LogCollector(adb_path="", enabled=True)

    result = collector.get_recent_crashes(package="com.example.securities")

    assert result["status"] == "unavailable"
    assert result["crashes"] == []
    assert "adb" in result["reason"]


def test_log_collector_parses_runner_output_into_crash_signatures():
    calls = []

    def fake_runner(args):
        calls.append(args)
        return {"status": "success", "stdout": JAVA_CRASH, "stderr": ""}

    collector = LogCollector(adb_path="adb", enabled=True, runner=fake_runner)

    result = collector.get_recent_crashes(package="com.example.securities", lines=200)

    assert calls == [["adb", "logcat", "-d", "-t", "200"]]
    assert result["status"] == "success"
    assert result["crash_count"] == 1
    assert result["crashes"][0]["exception_class"] == "java.lang.NullPointerException"


def test_log_collector_does_not_call_runner_when_disabled():
    def fake_runner(args):
        raise AssertionError(f"runner should not be called: {args}")

    collector = LogCollector(adb_path="adb", enabled=False, runner=fake_runner)

    result = collector.get_recent_crashes(package="com.example.securities")

    assert result["status"] == "disabled"
    assert result["crash_count"] == 0
