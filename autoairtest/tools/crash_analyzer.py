"""Android 崩溃日志签名提取。"""

from __future__ import annotations

import hashlib
import re
from typing import Any


_PROCESS_RE = re.compile(r"Process:\s*(?P<process>[^,\s]+)")
_EXCEPTION_RE = re.compile(r"AndroidRuntime:\s*(?P<class>(?:[a-zA-Z_$][\w$]*\.)+[A-Za-z_$][\w$]*)")
_FRAME_RE = re.compile(r"\bat\s+(?P<frame>[\w.$]+)\([^)]*\)")
_ANR_PROCESS_RE = re.compile(r"ANR in\s+(?P<process>[^\s]+)")
_ANR_REASON_RE = re.compile(r"Reason:\s*(?P<reason>.+)")
_NATIVE_PROCESS_RE = re.compile(r">>>\s*(?P<process>[^<\s]+)\s*<<<")
_NATIVE_FRAME_RE = re.compile(r"#\d+\s+pc\s+[0-9a-fA-F]+\s+(?P<frame>\S+(?:\s+\([^)]*\))?)")


def extract_crash_signatures(log_text: str, package: str = "") -> list[dict[str, Any]]:
    """从 logcat 文本中提取 crash signature 列表。

    当前 MVP 先覆盖 Java crash。行号、文件名和空白不进入签名，避免同一问题因构建差异
    被错误拆成多个 crash。
    """

    if "ANR in " in log_text:
        return _extract_anr_signature(log_text, package)

    if "*** *** ***" in log_text and ">>>" in log_text:
        return _extract_native_signature(log_text, package)

    if "FATAL EXCEPTION" not in log_text and "AndroidRuntime" not in log_text:
        return []

    process = _extract_process(log_text)
    if package and process and process != package:
        return []

    exception_class = _extract_exception_class(log_text)
    if not exception_class:
        return []

    frames = _extract_top_frames(log_text)
    signature_id = _signature_id("java", exception_class, frames[:3], process or package)
    return [
        {
            "signature_id": signature_id,
            "kind": "java",
            "exception_class": exception_class,
            "top_frames_normalized": frames[:3],
            "process": process or package,
            "source": "logcat",
            "first_seen_step": 0,
        }
    ]


def _extract_anr_signature(log_text: str, package: str) -> list[dict[str, Any]]:
    match = _ANR_PROCESS_RE.search(log_text)
    process = match.group("process") if match else package
    if package and process and process != package:
        return []

    reason_match = _ANR_REASON_RE.search(log_text)
    reason = reason_match.group("reason").strip() if reason_match else "ANR"
    signature_id = _signature_id("anr", "ANR", [reason], process or package)
    return [
        {
            "signature_id": signature_id,
            "kind": "anr",
            "exception_class": "ANR",
            "top_frames_normalized": [reason],
            "process": process or package,
            "source": "logcat",
            "first_seen_step": 0,
        }
    ]


def _extract_native_signature(log_text: str, package: str) -> list[dict[str, Any]]:
    match = _NATIVE_PROCESS_RE.search(log_text)
    process = match.group("process") if match else package
    if package and process and process != package:
        return []

    frames = _extract_native_frames(log_text)
    signature_id = _signature_id("native", "native_crash", frames[:3], process or package)
    return [
        {
            "signature_id": signature_id,
            "kind": "native",
            "exception_class": "native_crash",
            "top_frames_normalized": frames[:3],
            "process": process or package,
            "source": "logcat",
            "first_seen_step": 0,
        }
    ]


def _extract_process(log_text: str) -> str:
    match = _PROCESS_RE.search(log_text)
    return match.group("process") if match else ""


def _extract_exception_class(log_text: str) -> str:
    for line in log_text.splitlines():
        if "AndroidRuntime:" not in line:
            continue
        if "FATAL EXCEPTION" in line or "Process:" in line:
            continue
        match = _EXCEPTION_RE.search(line)
        if match:
            return match.group("class")
    return ""


def _extract_top_frames(log_text: str) -> list[str]:
    frames: list[str] = []
    for line in log_text.splitlines():
        match = _FRAME_RE.search(line)
        if not match:
            continue
        frames.append(match.group("frame"))
        if len(frames) == 3:
            break
    return frames


def _extract_native_frames(log_text: str) -> list[str]:
    frames: list[str] = []
    for line in log_text.splitlines():
        match = _NATIVE_FRAME_RE.search(line)
        if not match:
            continue
        frames.append(match.group("frame").strip())
        if len(frames) == 3:
            break
    return frames


def _signature_id(kind: str, exception_class: str, frames: list[str], process: str) -> str:
    payload = "|".join([kind, exception_class, *frames, process])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
