"""
Test Runner - Unified test execution engine for eCan.ai.

Provides programmatic and CLI access to run test suites with reporting.

Usage:
    # Programmatic
    runner = ECTestRunner(mode="dev")
    result = runner.run(categories=["unit", "smoke"])
    runner.generate_report()

    # CLI
    python -m tests.framework.runners --categories unit,smoke --report
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal


class ECTestRunner:
    """
    Unified test runner for eCan.ai.

    Modes:
      - "dev":     Fast feedback, stop on first failure, verbose
      - "ci":      Full suite, parallel, strict, XML/JUnit reports
      - "report":  Generate HTML/JSON report from previous run
    """

    def __init__(
        self,
        mode: Literal["dev", "ci", "report"] = "dev",
        root_dir: str | None = None,
    ) -> None:
        self._mode = mode
        self._root_dir = Path(root_dir or self._find_root())
        self._results: dict = {}
        self._exit_code = 0

    @staticmethod
    def _find_root() -> str:
        cur = Path(__file__).resolve().parent
        for _ in range(10):
            if (cur / "pytest.ini").exists() or (cur / "pyproject.toml").exists():
                return str(cur)
            cur = cur.parent
        return os.getcwd()

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def _base_pytest_args(self) -> list[str]:
        base = ["pytest", str(self._root_dir)]

        if self._mode == "dev":
            base += [
                "-v",
                "--tb=short",
                "--color=yes",
                "-p", "no:warnings",
            ]
        elif self._mode == "ci":
            base += [
                "-v",
                "--tb=line",
                "--color=yes",
                "-n", "auto",
                f"--junitxml={self._root_dir}/test-reports/results.xml",
                f"--html={self._root_dir}/test-reports/report.html",
                "--self-contained-html",
                "--cov=agent",
                "--cov=utils",
                "--cov=config",
                "--cov-report=term-missing",
                f"--cov-report=xml:{self._root_dir}/test-reports/coverage.xml",
            ]

        return base

    def _select_categories(self, categories: list[str] | None) -> list[str]:
        """Convert category names to pytest --ignore/--select args."""
        all_paths = {
            "unit": "tests/unit",
            "integration": "tests/integration",
            "smoke": "tests/smoke",
            "e2e": "tests/e2e",
        }

        # Default: unit + smoke (fastest, most valuable for dev)
        if not categories:
            categories = ["unit", "smoke"]

        args = []
        # Only run selected categories
        for cat, path in all_paths.items():
            if cat not in categories:
                args.extend(["--ignore", str(self._root_dir / path)])
        return args

    def _filter_markers(self, include_cloud: bool = False) -> list[str]:
        """Apply marker filters."""
        if include_cloud:
            return []
        return ["-m", "not cloud"]

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    def run(
        self,
        categories: list[str] | None = None,
        include_cloud: bool = False,
        parallel: bool | None = None,
        verbose: bool | None = None,
        extra_args: list[str] | None = None,
    ) -> dict:
        """
        Run the test suite.

        Args:
            categories: Test categories to run ["unit", "integration", "smoke", "e2e"]
            include_cloud: Include tests marked @pytest.mark.cloud (real API calls)
            parallel: Override parallel execution (default: ci=True, dev=False)
            verbose: Override verbosity (default: ci=False, dev=True)
            extra_args: Additional pytest arguments

        Returns:
            dict with exit_code, stdout, stderr, duration
        """
        if parallel is None:
            parallel = self._mode == "ci"
        if verbose is None:
            verbose = self._mode == "dev"

        args = self._base_pytest_args()

        if parallel and not any("-n" in a for a in args):
            try:
                import pytest_xdist  # noqa: F401
                args.append("-n")
                args.append("auto")
            except ImportError:
                pass

        if not verbose:
            for i, a in enumerate(args):
                if a == "-v":
                    args[i] = "-q"

        args.extend(self._select_categories(categories))
        args.extend(self._filter_markers(include_cloud))

        if extra_args:
            args.extend(extra_args)

        # Ensure report dir exists
        if self._mode == "ci":
            report_dir = self._root_dir / "test-reports"
            report_dir.mkdir(exist_ok=True)

        print(f"[ECTestRunner] Running: {' '.join(args)}")
        print(f"[ECTestRunner] Mode: {self._mode}")
        print("=" * 60)

        import time
        start = time.time()

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=str(self._root_dir),
        )

        duration = time.time() - start
        self._exit_code = result.returncode
        self._results = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": round(duration, 2),
            "mode": self._mode,
            "categories": categories,
        }

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr, file=sys.stderr)

        print(f"[ECTestRunner] Finished in {duration:.2f}s, exit={result.returncode}")

        return self._results

    @property
    def exit_code(self) -> int:
        return self._exit_code

    @property
    def results(self) -> dict:
        return self._results

    # -------------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------------

    def generate_report(self, output: str = "test-reports/summary.json") -> str:
        """Generate a JSON summary report."""
        report_path = self._root_dir / output
        report_path.parent.mkdir(exist_ok=True)

        summary = {
            "mode": self._mode,
            "exit_code": self._exit_code,
            "duration_s": self._results.get("duration", 0),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "stdout_tail": self._results.get("stdout", "")[-2000:],
        }

        with open(report_path, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"[ECTestRunner] Report saved to {report_path}")
        return str(report_path)


# -------------------------------------------------------------------------
# CLI entry point
# -------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="eCan.ai Test Runner")
    parser.add_argument(
        "--categories",
        default="unit,smoke",
        help="Comma-separated categories: unit,integration,smoke,e2e",
    )
    parser.add_argument("--mode", choices=["dev", "ci"], default="dev")
    parser.add_argument("--report", action="store_true", help="Generate HTML/JSON report")
    parser.add_argument("--cloud", action="store_true", help="Include cloud tests")
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("extra", nargs="*", help="Extra pytest arguments")

    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    runner = ECTestRunner(mode=args.mode)
    results = runner.run(
        categories=categories,
        include_cloud=args.cloud,
        parallel=args.parallel,
    )

    if args.report:
        runner.generate_report()

    sys.exit(runner.exit_code)
