"""页面稳定等待。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class PageStabilityWaiter:
    """轮询页面签名，直到连续样本稳定或预算耗尽。"""

    def __init__(
        self,
        max_attempts: int = 8,
        required_stable_samples: int = 2,
        interval_seconds: float = 0.0,
        sampler: Callable[[], str] | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.required_stable_samples = required_stable_samples
        self.interval_seconds = interval_seconds
        self.sampler = sampler or (lambda: "")

    def wait(self) -> dict[str, Any]:
        last_signature = ""
        stable_count = 0
        attempts = 0
        for attempts in range(1, self.max_attempts + 1):
            signature = self.sampler()
            if signature and signature == last_signature:
                stable_count += 1
            else:
                stable_count = 1
            last_signature = signature
            if stable_count >= self.required_stable_samples:
                return {"stable": True, "attempts": attempts, "last_signature": last_signature}
            if self.interval_seconds:
                time.sleep(self.interval_seconds)
        return {"stable": False, "attempts": attempts, "last_signature": last_signature}
