from autoairtest.config import default_config, merge_config


def test_default_config_exposes_latest_design_session_logs_doctor_and_state_graph():
    config = default_config()

    assert config["execution"]["max_steps_per_case"] == 30
    assert config["execution"]["enable_state_graph"] is False
    assert config["logs"]["enable_capture"] is True
    assert "FATAL EXCEPTION" in config["logs"]["crash_patterns"]
    assert config["report"]["session_name"] == ""
    assert config["doctor"]["check_airtest"] is True
    assert config["doctor"]["check_poco"] is True
    assert config["verification"]["llm_preliminary_judgment"] is True
    assert config["verification"]["evidence_recollection"]["max_attempts"] == 2
    assert config["execution"]["correction_budget"] == {"low": 3, "medium": 1, "high": 0}
    assert config["evidence"]["redact_sensitive_text"] is True
    assert "手机号" in config["evidence"]["sensitive_keywords"]
    assert config["evidence"]["screenshot_redaction"] is False
    assert config["llm"]["enabled"] is False
    assert config["llm"]["provider"] == "openai_compatible"
    assert config["llm"]["base_url"] == "https://api.openai.com/v1"
    assert config["llm"]["api_key_env"] == "OPENAI_API_KEY"
    assert config["llm"]["use_for_planning"] is False
    assert config["llm"]["use_for_verification"] is True
    assert config["llm"]["retry_backoff_seconds"] == 0.25


def test_merge_config_preserves_nested_latest_design_defaults():
    merged = merge_config(default_config(), {"logs": {"enable_capture": False}})

    assert merged["logs"]["enable_capture"] is False
    assert merged["logs"]["default_window_seconds"] == 5
    assert "AndroidRuntime" in merged["logs"]["crash_patterns"]
    assert merged["execution"]["correction_budget"]["low"] == 3
    assert merged["llm"]["base_url"] == "https://api.openai.com/v1"
