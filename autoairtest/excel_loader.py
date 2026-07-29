"""Excel 自然语言测试用例加载器。

该模块把工作簿中的业务语言字段映射为系统内部的标准化测试用例对象。解析过程
强调字段稳定性、空值规范化和重复用例名称的可追踪性。
"""

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
    """当前环境缺少 Excel 解析依赖时抛出的显式错误。"""

    pass


def normalize_cell(value: Any) -> str:
    """把 Excel 单元格值规范化为字符串，空值统一表示为空串。"""

    if value is None:
        return ""
    return str(value).strip()


def build_case_from_row(
    row: dict[str, Any],
    row_number: int,
    duplicate_names: set[str],
) -> NaturalLanguageTestCase:
    """由一行表格数据构造自然语言测试用例对象。"""

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
    """从指定工作簿与 sheet 中读取所有非空测试用例。"""

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

    # 重名用例保留原始名称，同时用行号构造内部 ID，保证证据目录唯一。
    duplicates = {name for name, count in Counter(case_names).items() if name and count > 1}
    individual_cases = [build_case_from_row(row, row_number, duplicates) for row_number, row in rows]
    return group_consecutive_cases(individual_cases)


def group_consecutive_cases(cases: list[NaturalLanguageTestCase]) -> list[NaturalLanguageTestCase]:
    """将连续的同名用例合并为多步骤用例。

    同名且连续的行被视为同一条用例的多个步骤，合并为一条
    NaturalLanguageTestCase；单行或不同名的行保持不变。
    """

    if not cases:
        return []

    result: list[NaturalLanguageTestCase] = []
    group: list[NaturalLanguageTestCase] = [cases[0]]

    for case in cases[1:]:
        if case.case_id == group[-1].case_id:
            group.append(case)
        else:
            result.append(_merge_case_group(group))
            group = [case]

    result.append(_merge_case_group(group))
    return result


def _merge_case_group(group: list[NaturalLanguageTestCase]) -> NaturalLanguageTestCase:
    """把同一用例的一组连续行合并为一条多步骤用例。"""

    if len(group) == 1:
        return group[0]

    first = group[0]
    ops: list[str] = []
    exps: list[str] = []
    step_names: list[str] = []

    for i, case in enumerate(group, start=1):
        if case.operation_description:
            ops.append(f"步骤{i}: {case.operation_description}")
        if case.expected_result:
            exps.append(f"步骤{i}预期: {case.expected_result}")
        if case.step_name:
            step_names.append(f"步骤{i}: {case.step_name}")

    merged_op = "\n".join(ops)
    merged_exp = "\n".join(exps)
    merged_step = "\n".join(step_names)

    return NaturalLanguageTestCase(
        case_id=first.case_id,
        internal_id=first.case_id,
        row_number=first.row_number,
        business_module=first.business_module,
        feature_module=first.feature_module,
        feature_item=first.feature_item,
        test_purpose=first.test_purpose,
        priority=first.priority,
        step_name=merged_step,
        precondition=first.precondition,
        operation_description=merged_op,
        parameters=first.parameters,
        expected_result=merged_exp,
        original_fields={
            **first.original_fields,
            "操作描述": merged_op,
            "预期结果": merged_exp,
            "步骤名称": merged_step,
            "_merged_rows": str(len(group)),
            "_merged_row_numbers": ",".join(str(c.row_number) for c in group),
        },
    )
