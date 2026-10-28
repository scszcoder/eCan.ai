"""The Amazon after-sales run report: the generic store report with Amazon's names.

Kept as its own module because the amazon_after_sales skill's Save_Report code step
imports ``save_amazon_run_report`` from here.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agent.ec_skills.reports import store_report
from agent.ec_skills.reports.store_report import browser_final, parse_report  # noqa: F401 (re-exported)


def render_failure(final: Any) -> str:
    return store_report.render_failure(final, "amazon")


def summary_title(report: Dict[str, Any]) -> str:
    return store_report.summary_title(report, "amazon")


def render_markdown(report: Dict[str, Any]) -> str:
    return store_report.render_markdown(report, "amazon")


def save_amazon_run_report(state: Dict[str, Any], store_name: str = "", date: Optional[str] = None) -> Dict[str, Any]:
    return store_report.save_store_run_report(state, "amazon", store_name, date=date)
