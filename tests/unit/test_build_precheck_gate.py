# -*- coding: utf-8 -*-
"""The build precheck must actually block on the issues it calls critical.

Regression for a gate that was dead code in two independent ways:

* ``critical_patterns`` holds regular expressions (``"Python.*too old"``) but
  they were matched with ``pattern.lower() in issue.lower()`` -- a substring
  test against the *regex source text*, which never matches;
* only ``results["platform"]["issues"]`` was scanned, while
  ``BuildValidator._validate_environment`` files the Python-version problem
  under ``environment``.

Either one alone was enough to let a too-old interpreter reach PyInstaller
with nothing but a warning, so ``build_validator.py`` exited FAIL while
``build.py`` went on to produce an artifact. Both are pinned here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from build_system.unified_build import BuildError, UnifiedBuildSystem


class _FakeValidator:
    """Stands in for BuildValidator: hands back a canned result dict."""

    def __init__(self, results):
        self._results = results
        self.calls = 0

    def run_full_validation(self):
        self.calls += 1
        return self._results


def _system_with(results):
    """A UnifiedBuildSystem whose validator is the fake, no __init__ side effects."""
    system = object.__new__(UnifiedBuildSystem)
    system.validator = _FakeValidator(results)
    return system


def _results(**category_issues):
    """A validator result: overall FAIL, with issues in the named categories."""
    base = {category: {"status": "pass", "issues": []}
            for category in ("platform", "environment", "project",
                             "dependencies", "platform_specific")}
    for category, issues in category_issues.items():
        base[category] = {"status": "fail", "issues": list(issues)}
    base["overall_status"] = "fail" if category_issues else "pass"
    return base


TOO_OLD = "Python 3.11 is too old. Minimum required: 3.12"


def test_a_too_old_python_reported_under_environment_blocks_the_build():
    """The bug as it shipped: the issue is real, but it is not in `platform`."""
    system = _system_with(_results(environment=[TOO_OLD]))
    with pytest.raises(BuildError) as exc:
        system.validate_environment()
    assert "Python 3.11 is too old" in str(exc.value)


def test_the_python_pattern_is_matched_as_a_regex_not_as_a_substring():
    """`"Python.*too old"` must be searched; the literal never appears in the issue."""
    assert "Python.*too old" not in TOO_OLD          # the old substring test
    system = _system_with(_results(environment=[TOO_OLD]))
    with pytest.raises(BuildError):
        system.validate_environment()


def test_a_critical_issue_in_any_category_blocks():
    """Not just `platform` and not just `environment` -- every category counts."""
    for category in ("platform", "environment", "project",
                     "dependencies", "platform_specific"):
        system = _system_with(_results(**{category: ["Missing tool: iscc"]}))
        with pytest.raises(BuildError, match="Missing tool"):
            system.validate_environment()


def test_the_blocking_message_names_the_issue_and_the_override():
    """An operator must see *what* blocked and *how* to proceed."""
    system = _system_with(_results(environment=[TOO_OLD]))
    with pytest.raises(BuildError) as exc:
        system.validate_environment()
    message = str(exc.value)
    assert TOO_OLD in message
    assert "--skip-precheck" in message


def test_non_critical_issues_warn_and_let_the_build_continue(capsys):
    """A warning is still a warning: only the listed patterns are fatal."""
    system = _system_with(_results(project=["README.md is older than the last release"]))
    system.validate_environment()                  # must not raise
    assert "Non-critical validation issues found" in capsys.readouterr().out


def test_several_blocking_issues_are_all_reported():
    system = _system_with(_results(
        environment=[TOO_OLD], platform=["Missing tool: git"]))
    with pytest.raises(BuildError) as exc:
        system.validate_environment()
    message = str(exc.value)
    assert "Python 3.11 is too old" in message
    assert "Missing tool: git" in message


def test_a_passing_validation_runs_no_pattern_matching():
    system = _system_with(_results())
    system.validate_environment()                  # must not raise
    assert system.validator.calls == 1


def test_skip_precheck_never_consults_the_validator():
    """The documented override still works, and costs nothing."""
    system = _system_with(_results(environment=[TOO_OLD]))
    system.validate_environment(skip_precheck=True)    # must not raise
    assert system.validator.calls == 0


def test_a_validator_that_raises_is_reported_as_a_build_error():
    class _Boom:
        def run_full_validation(self):
            raise RuntimeError("disk went away")

    system = object.__new__(UnifiedBuildSystem)
    system.validator = _Boom()
    with pytest.raises(BuildError, match="disk went away"):
        system.validate_environment()
