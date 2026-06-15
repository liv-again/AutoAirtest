"""HTML 报告生成器。

报告用于把运行结果转化为可审计、可复核的人工阅读材料。当前实现采用静态 HTML，
以降低部署成本并保证证据包可离线分发。
"""

from __future__ import annotations

from html import escape
from pathlib import Path


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
        "</tr>"
        for item in case_summaries
    )
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
  <table>
    <thead><tr><th>Case</th><th>Status</th><th>Summary</th><th>Evidence</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
    output = output_dir / "report.html"
    output.write_text(html, encoding="utf-8")
    return output
