from autoairtest.execution.stability import PageStabilityWaiter


def test_page_stability_waiter_stops_after_consecutive_equal_signatures():
    signatures = iter(["screen-a", "screen-b", "screen-b"])
    waiter = PageStabilityWaiter(max_attempts=5, required_stable_samples=2, sampler=lambda: next(signatures))

    result = waiter.wait()

    assert result["stable"] is True
    assert result["attempts"] == 3
    assert result["last_signature"] == "screen-b"


def test_page_stability_waiter_reports_unstable_after_budget_exhausted():
    signatures = iter(["a", "b", "c"])
    waiter = PageStabilityWaiter(max_attempts=3, required_stable_samples=2, sampler=lambda: next(signatures))

    result = waiter.wait()

    assert result["stable"] is False
    assert result["attempts"] == 3
    assert result["last_signature"] == "c"
