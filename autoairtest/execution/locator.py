"""执行期定位漏斗。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autoairtest.models import LocatorCandidate


class Locator:
    """Poco、控件树截图联合定位、OCR 的三级定位入口。"""

    def __init__(self, poco: Any, ocr: Any, airtest: Any) -> None:
        self.poco = poco
        self.ocr = ocr
        self.airtest = airtest

    def locate_and_act(
        self,
        target: str,
        screenshot_path: str,
        allow_ocr: bool = True,
        ocr_evidence_path: str = "",
        locators: list[LocatorCandidate] | None = None,
    ) -> dict[str, Any]:
        if locators:
            located = self._locate_with_candidates(target, locators)
            if located["response"].get("status") == "success" or not allow_ocr:
                return located
            return self._ocr_fallback(target, screenshot_path, ocr_evidence_path)
        response = self.poco.click(target)
        if response.get("status") == "success":
            return {
                "locator_level": "poco",
                "response": response,
                "selected_element": {"text": target, "source": "poco"},
                "ocr_evidence": "",
                "correction_step": None,
            }
        if not allow_ocr:
            return {
                "locator_level": "poco",
                "response": response,
                "selected_element": None,
                "ocr_evidence": "",
                "correction_step": None,
            }
        return self._ocr_fallback(target, screenshot_path, ocr_evidence_path)

    def _locate_with_candidates(
        self,
        target: str,
        locators: list[LocatorCandidate],
    ) -> dict[str, Any]:
        last_response: dict[str, Any] = {
            "status": "unavailable",
            "reason": "no supported locator candidate",
            "query": target,
        }
        last_level = "poco"
        for candidate in locators:
            locator_type = str(candidate.type)
            value = candidate.value
            if locator_type == "resource_id":
                last_level = "poco_resource_id"
                if not hasattr(self.poco, "click_resource_id"):
                    last_response = {
                        "status": "unavailable",
                        "reason": "poco adapter does not support resource_id",
                        "query": value,
                    }
                    continue
                last_response = self.poco.click_resource_id(str(value))
            elif locator_type == "text":
                last_level = "poco_text"
                last_response = self.poco.click(str(value))
            else:
                last_level = f"poco_{locator_type}"
                last_response = {
                    "status": "unavailable",
                    "reason": f"unsupported locator type: {locator_type}",
                    "query": value,
                }
                continue
            if last_response.get("status") == "success":
                return {
                    "locator_level": last_level,
                    "response": last_response,
                    "selected_element": {
                        "text": target,
                        "locator_type": locator_type,
                        "value": value,
                        "source": "poco",
                    },
                    "ocr_evidence": "",
                    "correction_step": None,
                }
        return {
            "locator_level": last_level,
            "response": last_response,
            "selected_element": None,
            "ocr_evidence": "",
            "correction_step": None,
        }

    def locate_from_dump_and_screenshot(
        self,
        target: str,
        dump: dict[str, Any],
        screenshot_path: str,
        allow_ocr: bool = True,
        ocr_evidence_path: str = "",
    ) -> dict[str, Any]:
        match = _dump_match(target, dump)
        if match:
            touch_point = _bounds_center(match["bounds"])
            response = self.airtest.touch(touch_point)
            if response.get("status") == "success":
                return {
                    "locator_level": "dump_bounds",
                    "response": response | {"source": "dump_bounds", "query": target, "target": touch_point},
                    "selected_element": match,
                    "ocr_evidence": "",
                    "correction_step": {
                        "type": "dump_bounds",
                        "target": target,
                        "touch_point": list(touch_point),
                    },
                }
            return {
                "locator_level": "dump_bounds",
                "response": response | {"source": "dump_bounds", "query": target, "target": touch_point},
                "selected_element": match,
                "ocr_evidence": "",
                "correction_step": None,
            }
        if not allow_ocr:
            return {
                "locator_level": "dump_bounds",
                "response": {"status": "unavailable", "reason": "dump target not found", "query": target},
                "selected_element": None,
                "ocr_evidence": "",
                "correction_step": None,
            }
        return self._ocr_fallback(target, screenshot_path, ocr_evidence_path)

    def locate_with_ocr(self, target: str, screenshot_path: str, ocr_evidence_path: str = "") -> dict[str, Any]:
        """直接使用 OCR 定位，供 Poco 层级不可用的降级路径调用。"""

        return self._ocr_fallback(target, screenshot_path, ocr_evidence_path)

    def _ocr_fallback(self, target: str, screenshot_path: str, ocr_evidence_path: str = "") -> dict[str, Any]:
        ocr_result = self.ocr.recognize(screenshot_path)
        match = ocr_match(target, ocr_result)
        if not match:
            return {
                "locator_level": "ocr",
                "response": {"status": "unavailable", "reason": "ocr target not found", "source": "ocr", "query": target},
                "selected_element": None,
                "ocr_evidence": ocr_evidence_path,
                "ocr_result": ocr_result,
                "correction_step": None,
            }
        touch_point = _bounds_center(match["bounds"])
        response = self.airtest.touch(touch_point)
        if response.get("status") != "success":
            return {
                "locator_level": "ocr",
                "response": response | {"source": "ocr", "query": target, "target": touch_point},
                "selected_element": match,
                "ocr_evidence": ocr_evidence_path,
                "ocr_result": ocr_result,
                "correction_step": None,
            }
        return {
            "locator_level": "ocr",
            "response": {
                "status": "success",
                "source": "ocr",
                "query": target,
                "target": touch_point,
                "match": match,
            },
            "selected_element": match,
            "ocr_evidence": ocr_evidence_path,
            "ocr_result": ocr_result,
            "correction_step": {
                "type": "ocr_fallback",
                "target": target,
                "touch_point": list(touch_point),
            },
        }


def write_ocr_result(path: str | Path, payload: dict[str, Any]) -> None:
    import json

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ocr_match(target: str, ocr_result: dict[str, Any]) -> dict[str, Any] | None:
    texts = ocr_result.get("texts", [])
    if not isinstance(texts, list):
        return None
    for item in texts:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", ""))
        bounds = item.get("bounds")
        if target and target in text and valid_bounds(bounds):
            return {"text": text, "bounds": bounds}
    return None


def valid_bounds(bounds: Any) -> bool:
    return (
        isinstance(bounds, list)
        and len(bounds) == 4
        and all(isinstance(item, int | float) for item in bounds)
        and bounds[2] > bounds[0]
        and bounds[3] > bounds[1]
    )


def _dump_match(target: str, dump: dict[str, Any]) -> dict[str, Any] | None:
    elements = dump.get("elements", [])
    if not isinstance(elements, list):
        return None
    for element in elements:
        if not isinstance(element, dict):
            continue
        text = str(element.get("text", ""))
        bounds = element.get("bounds")
        if target and target in text and valid_bounds(bounds):
            return {"text": text, "bounds": bounds, "source": "dump"}
    return None


def _bounds_center(bounds: list[int | float]) -> tuple[int, int]:
    return (int((bounds[0] + bounds[2]) / 2), int((bounds[1] + bounds[3]) / 2))
