from autoairtest.tools.crash_analyzer import extract_crash_signatures


JAVA_CRASH = """
06-21 10:30:00.000 1234 1234 E AndroidRuntime: FATAL EXCEPTION: main
06-21 10:30:00.000 1234 1234 E AndroidRuntime: Process: com.example.securities, PID: 1234
06-21 10:30:00.000 1234 1234 E AndroidRuntime: java.lang.NullPointerException: boom
06-21 10:30:00.000 1234 1234 E AndroidRuntime:     at com.example.LoginActivity.onClick(LoginActivity.java:42)
06-21 10:30:00.000 1234 1234 E AndroidRuntime:     at android.view.View.performClick(View.java:7650)
"""


def test_extract_java_crash_signature_ignores_line_number_changes():
    changed_line = JAVA_CRASH.replace("LoginActivity.java:42", "LoginActivity.java:99")

    first = extract_crash_signatures(JAVA_CRASH, package="com.example.securities")
    second = extract_crash_signatures(changed_line, package="com.example.securities")

    assert len(first) == 1
    assert first[0]["kind"] == "java"
    assert first[0]["exception_class"] == "java.lang.NullPointerException"
    assert first[0]["top_frames_normalized"][0] == "com.example.LoginActivity.onClick"
    assert first[0]["signature_id"] == second[0]["signature_id"]


def test_extract_java_crash_signature_changes_when_exception_class_changes():
    other = JAVA_CRASH.replace("java.lang.NullPointerException", "java.lang.IllegalStateException")

    first = extract_crash_signatures(JAVA_CRASH, package="com.example.securities")
    second = extract_crash_signatures(other, package="com.example.securities")

    assert first[0]["signature_id"] != second[0]["signature_id"]


def test_extract_crash_signatures_returns_empty_for_unrelated_or_quiet_logs():
    quiet = "06-21 10:30:00.000 I ActivityTaskManager: Displayed com.other/.MainActivity"

    assert extract_crash_signatures(quiet, package="com.example.securities") == []
