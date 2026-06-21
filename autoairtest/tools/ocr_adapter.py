"""OCR 适配器占位实现。

OCR 是 Poco 不可见文本场景的重要兜底证据来源。当前离线核心仅定义返回结构，避免
在未安装 OCR 引擎时破坏整体流程。
"""

from __future__ import annotations

from typing import Any


class OCRAdapter:
    """封装截图文字识别能力的适配器。"""

    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine

    def recognize(self, image_path: str) -> dict[str, Any]:
        """识别截图中的文本及其位置。"""

        if self.engine is not None:
            try:
                raw_result = self.engine.recognize(image_path)
            except Exception as exc:  # pragma: no cover - depends on third-party engine behavior
                return {
                    "status": "unavailable",
                    "reason": f"OCR engine failed: {type(exc).__name__}: {exc}",
                    "image_path": image_path,
                    "texts": [],
                }
            return {"status": "success", "image_path": image_path, "texts": _normalize_texts(raw_result)}

        return {
            "status": "unavailable",
            "reason": "OCR is out of scope for the offline core pass",
            "image_path": image_path,
            "texts": [],
        }


def _normalize_texts(raw_result: Any) -> list[dict[str, Any]]:
    if isinstance(raw_result, dict):
        texts = raw_result.get("texts", [])
    else:
        texts = raw_result
    if not isinstance(texts, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in texts:
        if isinstance(item, dict):
            normalized.append({"text": str(item.get("text", "")), "bounds": item.get("bounds")})
        elif isinstance(item, tuple) and len(item) >= 2:
            normalized.append({"text": str(item[0]), "bounds": item[1]})
    return normalized
