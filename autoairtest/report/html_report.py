"""HTML 报告生成器。

报告用于把运行结果转化为可审计、可复核的人工阅读材料。当前实现采用静态 HTML，
以降低部署成本并保证证据包可离线分发。
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


def write_html_report(run_dir: str | Path, case_summaries: list[dict[str, str]]) -> Path:
    """根据用例摘要生成单页 HTML 报告。"""

    output_dir = Path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(item['case_id'])}</td>"
        f"<td>{escape(item['run_status'])}</td>"
        f"<td>{escape(item['summary'])}</td>"
        f"<td>{escape(item['evidence_dir'])}</td>"
        f"<td>{escape(item.get('manual_review_reason', ''))}</td>"
        "</tr>"
        for item in case_summaries
    )
    session_meta = _read_json(output_dir / "session_meta.json")
    crashes = _read_jsonl(output_dir / "crashes.jsonl")
    session_html = _render_session_summary(session_meta)
    crash_html = _render_crash_summary(crashes)
    manual_review_html = _render_manual_review_clusters(case_summaries)
    audit_html = _render_case_audit(output_dir, case_summaries)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AutoAirtest Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>AutoAirtest Report</h1>
  {session_html}
  {crash_html}
  {manual_review_html}
  <table>
    <thead><tr><th>Case</th><th>Status</th><th>Summary</th><th>Evidence</th><th>Manual Review Reason</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {audit_html}
</body>
</html>
"""
    output = output_dir / "report.html"
    output.write_text(html, encoding="utf-8")
    return output


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _render_session_summary(session_meta: dict[str, Any]) -> str:
    if not session_meta:
        return ""
    return (
        "<section>"
        "<h2>Test Session</h2>"
        "<dl>"
        f"<dt>Session</dt><dd>{escape(str(session_meta.get('session_id', '')))}</dd>"
        f"<dt>Workflow</dt><dd>{escape(str(session_meta.get('workflow', '')))}</dd>"
        f"<dt>Status</dt><dd>{escape(str(session_meta.get('status', '')))}</dd>"
        f"<dt>Case Count</dt><dd>{escape(str(session_meta.get('case_count', '')))}</dd>"
        "</dl>"
        "</section>"
    )


def _render_crash_summary(crashes: list[dict[str, Any]]) -> str:
    if not crashes:
        return "<section><h2>Crashes</h2><p>No structured crashes recorded.</p></section>"
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(crash.get('crash_id', '')))}</td>"
        f"<td>{escape(str(crash.get('case_id', '')))}</td>"
        f"<td>{escape(str(crash.get('step_index', '')))}</td>"
        f"<td>{escape(str(crash.get('signature', {}).get('signature_id', '')))}</td>"
        f"<td>{escape(str(crash.get('signature', {}).get('exception_class', '')))}</td>"
        "</tr>"
        for crash in crashes
    )
    return (
        "<section>"
        "<h2>Crashes</h2>"
        "<table>"
        "<thead><tr><th>ID</th><th>Case</th><th>Step</th><th>Signature</th><th>Exception</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "</section>"
    )


def _render_manual_review_clusters(case_summaries: list[dict[str, str]]) -> str:
    clusters: dict[str, list[dict[str, str]]] = {}
    for item in case_summaries:
        reason = str(item.get("manual_review_reason", "")).strip()
        if not reason:
            continue
        clusters.setdefault(reason, []).append(item)

    if not clusters:
        return "<section><h2>Manual Review Clusters</h2><p>No manual review reasons recorded.</p></section>"

    sections = ["<section><h2>Manual Review Clusters</h2>"]
    for reason in sorted(clusters):
        cases = clusters[reason]
        rows = "\n".join(
            "<tr>"
            f"<td>{escape(str(item.get('case_id', '')))}</td>"
            f"<td>{escape(str(item.get('run_status', '')))}</td>"
            f"<td>{escape(str(item.get('summary', '')))}</td>"
            f"<td>{escape(str(item.get('evidence_dir', '')))}</td>"
            "</tr>"
            for item in cases
        )
        sections.append(
            f"<h3>{escape(reason)} ({len(cases)})</h3>"
            "<table>"
            "<thead><tr><th>Case</th><th>Status</th><th>Summary</th><th>Evidence</th></tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
        )
    sections.append("</section>")
    return "\n".join(sections)


def _render_case_audit(output_dir: Path, case_summaries: list[dict[str, str]]) -> str:
    sections = []
    for item in case_summaries:
        evidence_dir = str(item.get("evidence_dir", ""))
        if not evidence_dir:
            continue
        case_dir = output_dir / evidence_dir
        traces = _read_json_list(case_dir / "execution_trace.json")
        amendments = _read_json_list(case_dir / "plan_amendments.json")
        if not traces and not amendments:
            continue
        sections.append(
            "<section>"
            f"<h2>Audit: {escape(str(item.get('case_id', '')))}</h2>"
            f"{_render_execution_trace(traces)}"
            f"{_render_plan_amendments(amendments)}"
            "</section>"
        )
    return "\n".join(sections)


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _render_execution_trace(traces: list[dict[str, Any]]) -> str:
    if not traces:
        return ""
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(trace.get('trace_id', '')))}</td>"
        f"<td>{escape(str(trace.get('trace_type', '')))}</td>"
        f"<td>{escape(str(trace.get('action_id', '')))}</td>"
        f"<td>{escape(str(trace.get('planned_target', '')))}</td>"
        f"<td>{escape(str(trace.get('normalized_target', '')))}</td>"
        f"<td>{escape(str(trace.get('action_risk_level', '')))}</td>"
        f"<td>{escape(str((trace.get('correction_step') or {}).get('type', '')))}</td>"
        "</tr>"
        for trace in traces
    )
    return (
        "<h3>Execution Trace</h3>"
        "<table>"
        "<thead><tr><th>Trace</th><th>Trace Type</th><th>Action</th><th>Planned Target</th>"
        "<th>Normalized Target</th><th>Risk</th><th>Correction</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _render_plan_amendments(amendments: list[dict[str, Any]]) -> str:
    if not amendments:
        return ""
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(amendment.get('amendment_id', '')))}</td>"
        f"<td>{escape(str(amendment.get('action_id', '')))}</td>"
        f"<td>{escape(str(amendment.get('original_target', '')))}</td>"
        f"<td>{escape(str(amendment.get('resolved_target', '')))}</td>"
        f"<td>{escape(str(amendment.get('reason', '')))}</td>"
        "</tr>"
        for amendment in amendments
    )
    return (
        "<h3>Plan Amendments</h3>"
        "<table>"
        "<thead><tr><th>Amendment</th><th>Action</th><th>Original Target</th>"
        "<th>Resolved Target</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )
