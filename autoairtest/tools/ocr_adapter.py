from __future__ import annotations

from typing import Any


class OCRAdapter:
    def recognize(self, image_path: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "reason": "OCR is out of scope for the offline core pass",
            "image_path": image_path,
            "texts": [],
        }
