"""
Test Reporter - Generate HTML/Markdown test reports for eCan.ai.

Usage:
    reporter = TestReporter(output_dir="test-reports")
    reporter.add_results(results)
    reporter.generate_html()
    reporter.generate_markdown()
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class TestReporter:
    """
    Generate test reports from pytest results.

    Supports HTML (with charts) and Markdown output.
    """

    def __init__(
        self,
        output_dir: str = "test-reports",
        title: str = "eCan.ai Test Report",
    ) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._title = title
        self._results: list[dict] = []
        self._metadata: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration_s": 0.0,
        }

    def add_results(self, results: dict) -> None:
        """Add test run results."""
        self._results.append(results)
        if "duration" in results:
            self._metadata["duration_s"] += results["duration"]

    def add_metadata(self, **kwargs: Any) -> None:
        """Add metadata fields."""
        self._metadata.update(kwargs)

    def generate_json(self, filename: str = "report.json") -> str:
        """Generate JSON report."""
        path = self._output_dir / filename
        report = {
            "metadata": self._metadata,
            "results": self._results,
        }
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        return str(path)

    def generate_markdown(self, filename: str = "report.md") -> str:
        """Generate Markdown report."""
        path = self._output_dir / filename
        total = self._metadata.get("total", 0)
        passed = self._metadata.get("passed", 0)
        failed = self._metadata.get("failed", 0)
        skipped = self._metadata.get("skipped", 0)
        duration = self._metadata.get("duration_s", 0)

        pass_rate = (passed / total * 100) if total > 0 else 0

        lines = [
            f"# {self._title}",
            "",
            f"**Generated:** {self._metadata['timestamp']}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total | {total} |",
            f"| Passed | {passed} |",
            f"| Failed | {failed} |",
            f"| Skipped | {skipped} |",
            f"| Pass Rate | {pass_rate:.1f}% |",
            f"| Duration | {duration:.1f}s |",
            "",
        ]

        if self._results:
            lines.append("## Recent Runs")
            lines.append("")
            for i, r in enumerate(self._results[-5:], 1):
                status = "PASS" if r.get("exit_code", 1) == 0 else "FAIL"
                duration = r.get("duration", 0)
                lines.append(f"- Run {i}: **{status}** ({duration:.1f}s)")

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return str(path)

    def generate_html(self, filename: str = "report.html") -> str:
        """Generate HTML report with a summary table."""
        path = self._output_dir / filename

        total = self._metadata.get("total", 0)
        passed = self._metadata.get("passed", 0)
        failed = self._metadata.get("failed", 0)
        duration = self._metadata.get("duration_s", 0)
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Determine color based on pass rate
        if pass_rate >= 90:
            color = "#22c55e"
        elif pass_rate >= 70:
            color = "#f59e0b"
        else:
            color = "#ef4444"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self._title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; color: #f8fafc; }}
  .timestamp {{ color: #64748b; font-size: 0.85rem; margin-bottom: 2rem; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
  .stat-card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem;
                border: 1px solid #334155; }}
  .stat-value {{ font-size: 2rem; font-weight: 700; color: {color}; }}
  .stat-label {{ font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b;
           border-radius: 12px; overflow: hidden; border: 1px solid #334155; }}
  th {{ background: #334155; padding: 0.75rem 1rem; text-align: left;
        font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }}
  td {{ padding: 0.75rem 1rem; border-top: 1px solid #334155; font-size: 0.9rem; }}
  tr:hover {{ background: #263344; }}
  .pass {{ color: #22c55e; }} .fail {{ color: #ef4444; }} .skip {{ color: #94a3b8; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 9999px;
            font-size: 0.75rem; font-weight: 600; }}
  .badge-pass {{ background: #22c55e20; color: #22c55e; }}
  .badge-fail {{ background: #ef444420; color: #ef4444; }}
</style>
</head>
<body>
<div class="container">
  <h1>{self._title}</h1>
  <p class="timestamp">Generated: {self._metadata["timestamp"]}</p>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-value">{total}</div>
      <div class="stat-label">Total Tests</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{passed}</div>
      <div class="stat-label">Passed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{failed}</div>
      <div class="stat-label">Failed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{pass_rate:.1f}%</div>
      <div class="stat-label">Pass Rate</div>
    </div>
  </div>

  <h2 style="font-size:1.1rem;margin-bottom:1rem;color:#94a3b8;">Recent Test Runs</h2>
  <table>
    <thead>
      <tr>
        <th>Status</th>
        <th>Mode</th>
        <th>Categories</th>
        <th>Duration</th>
      </tr>
    </thead>
    <tbody>
      {"".join(
          f'<tr>'
          f'<td><span class="badge {"badge-pass" if r.get("exit_code",1)==0 else "badge-fail"}">'
          f'{"PASS" if r.get("exit_code",1)==0 else "FAIL"}</span></td>'
          f'<td>{r.get("mode","-")}</td>'
          f'<td>{", ".join(r.get("categories",[]))}</td>'
          f'<td>{r.get("duration",0):.1f}s</td>'
          f'</tr>'
          for r in self._results
      )}
    </tbody>
  </table>
</div>
</body>
</html>"""

        with open(path, "w") as f:
            f.write(html)

        return str(path)
