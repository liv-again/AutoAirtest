from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autoairtest.models import dataclass_to_dict


class EvidenceStore:
    def __init__(self, output_dir: str | Path, timestamp: str):
        self.root = Path(output_dir) / timestamp
        self.cases_root = self.root / "cases"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases_root.mkdir(parents=True, exist_ok=True)

    def create_case_dir(self, case_id: str) -> Path:
        case_dir = self.cases_root / safe_path_name(case_id)
        for child in ["screenshots", "element_summaries", "ocr"]:
            (case_dir / child).mkdir(parents=True, exist_ok=True)
        return case_dir

    def write_case_json(self, case_id: str, filename: str, payload: Any) -> Path:
        case_dir = self.create_case_dir(case_id)
        output = case_dir / filename
        output.write_text(
            json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output

    def write_run_json(self, filename: str, payload: Any) -> Path:
        output = self.root / filename
        output.write_text(
            json.dumps(dataclass_to_dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return output


def safe_path_name(value: str) -> str:
    return "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in value).strip() or "case"
