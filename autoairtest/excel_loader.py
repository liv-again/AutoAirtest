from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .models import NaturalLanguageTestCase


REQUIRED_HEADERS = [
    "业务模块",
    "功能模块",
    "功能项",
    "测试目的",
    "TC_用例名称",
    "优先级",
    "步骤名称",
    "前置条件",
    "操作描述",
    "参数",
    "预期结果",
    "测试结果",
    "备注",
]


class ExcelDependencyError(RuntimeError):
    pass


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_case_from_row(
    row: dict[str, Any],
    row_number: int,
    duplicate_names: set[str],
) -> NaturalLanguageTestCase:
    normalized = {header: normalize_cell(row.get(header)) for header in REQUIRED_HEADERS}
    case_id = normalized["TC_用例名称"]
    internal_id = f"{case_id}__row_{row_number}" if case_id in duplicate_names else case_id
    return NaturalLanguageTestCase(
        case_id=case_id,
        internal_id=internal_id,
        row_number=row_number,
        business_module=normalized["业务模块"],
        feature_module=normalized["功能模块"],
        feature_item=normalized["功能项"],
        test_purpose=normalized["测试目的"],
        priority=normalized["优先级"],
        step_name=normalized["步骤名称"],
        precondition=normalized["前置条件"],
        operation_description=normalized["操作描述"],
        parameters=normalized["参数"],
        expected_result=normalized["预期结果"],
        original_fields=normalized,
    )


def load_test_cases(excel_path: str | Path, sheet_name: str) -> list[NaturalLanguageTestCase]:
    try:
        import openpyxl  # type: ignore
    except ModuleNotFoundError as exc:
        raise ExcelDependencyError(
            "openpyxl is not installed in the torch environment; install it in torch or use test fixtures."
        ) from exc

    workbook = openpyxl.load_workbook(excel_path, data_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Sheet not found: {sheet_name}")
    sheet = workbook[sheet_name]

    headers = [normalize_cell(sheet.cell(row=1, column=col).value) for col in range(1, sheet.max_column + 1)]
    missing = [header for header in REQUIRED_HEADERS if header not in headers]
    if missing:
        raise ValueError(f"Missing required Excel headers: {', '.join(missing)}")

    rows: list[tuple[int, dict[str, Any]]] = []
    case_names: list[str] = []
    for row_number in range(2, sheet.max_row + 1):
        row = {
            header: sheet.cell(row=row_number, column=headers.index(header) + 1).value
            for header in REQUIRED_HEADERS
        }
        if not any(normalize_cell(value) for value in row.values()):
            continue
        rows.append((row_number, row))
        case_names.append(normalize_cell(row.get("TC_用例名称")))

    duplicates = {name for name, count in Counter(case_names).items() if name and count > 1}
    return [build_case_from_row(row, row_number, duplicates) for row_number, row in rows]
