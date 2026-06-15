"""证据存储工具。

证据目录是本系统可审计性的基础：每条用例的输入、计划、动作结果、验证结论和日志
均以稳定路径落盘，便于人工复核和后续实验复现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autoairtest.models import dataclass_to_dict


class EvidenceStore:
    """管理单次运行的证据目录与 JSON 文件写入。"""

    def __init__(self, output_dir: str | Path, timestamp: str):
        """初始化运行根目录。"""

        self.root = Path(output_dir) / timestamp
        self.cases_root = self.root / "cases"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases_root.mkdir(parents=True, exist_ok=True)

    def create_case_dir(self, case_id: str) -> Path:
        """创建单条用例的证据目录及其标准子目录。"""

        case_dir = self.cases_root / safe_path_name(case_id)
        for child in ["screenshots", "element_summaries", "ocr"]:
            (case_dir / child).mkdir(parents=True, exist_ok=True)
        return case_dir

    def write_case_json(self, case_id: str, filename: str, payload: Any) -> Path:
        """把用例级结构化对象写为 JSON 文件。"""

        case_dir = self.create_case_dir(case_id)
        output = case_dir / filename
        output.write_text(
            json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output

    def write_run_json(self, filename: str, payload: Any) -> Path:
        """把运行级结构化对象写为 JSON 文件。"""

        output = self.root / filename
        output.write_text(
            json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output


def safe_path_name(value: str) -> str:
    """把任意用例标识转换为适合文件系统路径的名称。"""

    return "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in value).strip() or "case"
