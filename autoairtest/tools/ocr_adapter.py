"""OCR 适配器占位实现。

OCR 是 Poco 不可见文本场景的重要兜底证据来源。当前离线核心仅定义返回结构，避免
在未安装 OCR 引擎时破坏整体流程。
"""

from __future__ import annotations

from typing import Any


class OCRAdapter:
    """封装截图文字识别能力的适配器。"""

    def recognize(self, image_path: str) -> dict[str, Any]:
        """识别截图中的文本及其位置。"""

        return {
            "status": "unavailable",
            "reason": "OCR is out of scope for the offline core pass",
            "image_path": image_path,
            "texts": [],
        }
