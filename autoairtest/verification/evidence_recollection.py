"""受限证据补采。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autoairtest.tools.airtest_adapter import AirtestAdapter
from autoairtest.tools.ocr_adapter import OCRAdapter
from autoairtest.tools.poco_adapter import PocoAdapter


class EvidenceRecollector:
    """在同一验证上下文内刷新界面证据。"""

    def __init__(
        self,
        poco: Any | None = None,
        airtest: Any | None = None,
        ocr: Any | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.poco = poco or PocoAdapter()
        self.airtest = airtest or AirtestAdapter()
        self.ocr = ocr or OCRAdapter()
        self.max_attempts = max_attempts

    def recollect(self, goal_id: str, case_dir: str | Path, attempt: int) -> dict[str, Any]:
        """执行一次受限证据补采。"""

        if attempt > self.max_attempts:
            return {"status": "budget_exhausted", "attempt": attempt, "max_attempts": self.max_attempts}

        root = Path(case_dir)
        screenshot = f"screenshots/recollect_{goal_id}_{attempt:02d}.png"
        screenshot_result = self.airtest.snapshot(str(root / screenshot))
        poco_result = self.poco.dump()
        ocr_result = self.ocr.recognize(str(root / screenshot))
        action = "visibility_adjustment" if attempt >= 2 else "refresh_current_screen_evidence"
        return {
            "status": "collected",
            "attempt": attempt,
            "goal_id": goal_id,
            "action": action,
            "action_risk_level": "low",
            "screenshot": screenshot,
            "screenshot_result": screenshot_result,
            "poco": poco_result,
            "ocr": ocr_result,
        }
