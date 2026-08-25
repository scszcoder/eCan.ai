#!/usr/bin/env python3
"""Regression test for terminals/5.txt:448-465 (2026-08-25, 09:35):

    Application startup failed:
    Error type: NotImplementedError
    ...
    File "main.py", line 1247, in main
      loop.run_forever()
    File ".../nest_asyncio.py", line 81, in run_forever
      self._run_once()
    File ".../nest_asyncio.py", line 115, in _run_once
      event_list = self._selector.select(timeout)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File ".../qasync/_unix.py", line 53, in select
      raise NotImplementedError

Root cause: ``agent.cloud_api.endpoints`` had a top-level

    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

that runs **unconditionally**.  ``nest_asyncio.apply()`` patches the
qasync ``QEventLoop`` class with a ``_run_once`` that calls
``self._selector.select(timeout)`` — but qasync's
``_unix._Selector.select`` is a stub that raises NotImplementedError
(actual Qt dispatch happens through QSocketNotifier +
``_process_events``).  So importing endpoints (which main.py does
during boot) and then calling ``loop.run_forever()`` crashes the
process before the splash hides.

Fix: skip ``nest_asyncio.apply()`` on Python 3.12+.  This module also
documents the second known breakage (``asyncio.current_task()``
returning ``None`` under run_until_complete, which breaks
``asyncio.wait_for`` / ``asyncio.timeout`` everywhere process-wide —
see agent/chats/wan_a2a_chat.py:23-31 for the same rationale in
another module).

This test is a **source-level invariant check**: it greps the
endpoints.py source and asserts the apply() call is guarded by a
Python version check.  That catches the regression in CI even on
systems where the bug doesn't crash (e.g. Linux + uvloop + no Qt)
because the fix has to be present on every platform.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_script_path = Path(__file__).resolve().parent  # tests/unit/
_project_root = _script_path
for _ in range(2):  # → tests/ → project root
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def _read(rel: str) -> str:
    return (_project_root / rel).read_text()


def _strip_strings_and_comments(src: str) -> str:
    """Replace all string literals and ``#`` comments with spaces of the
    same length.  Useful when searching for real AST-level invocations
    rather than docstring prose that happens to mention the same name.
    """
    return _strip_strings_and_comments_impl(src, strip_comments=True)


def _strip_strings(src: str) -> str:
    """Replace all string literals (but keep comments) with spaces.

    Use this when you want to look at the comment context surrounding a
    piece of code without string mentions confusing the search.
    """
    return _strip_strings_and_comments_impl(src, strip_comments=False)


def _strip_strings_and_comments_impl(src: str, strip_comments: bool) -> str:
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if strip_comments and c == "#":
            j = src.find("\n", i)
            if j == -1:
                j = n
            out.append(" " * (j - i))
            i = j
        elif c in ('"', "'"):
            quote = c
            triple = src[i : i + 3] == quote * 3
            if triple:
                end_marker = quote * 3
                j = src.find(end_marker, i + 3)
                if j == -1:
                    j = n
                else:
                    j += 3
                out.append(" " * (j - i))
                i = j
            else:
                j = i + 1
                while j < n and src[j] != quote:
                    if src[j] == "\\" and j + 1 < n:
                        j += 2
                    else:
                        j += 1
                j = min(j + 1, n)
                out.append(" " * (j - i))
                i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


class TestEndpointsDoesNotApplyNestAsyncioOnPython312:
    """``agent.cloud_api.endpoints`` must NOT call ``nest_asyncio.apply()``
    on Python 3.12+ — doing so patches the qasync ``QEventLoop`` and
    causes ``loop.run_forever()`` to raise ``NotImplementedError``
    (see terminals/5.txt:448-465).
    """

    def test_endpoints_skips_apply_on_python_312(self):
        src = _read("agent/cloud_api/endpoints.py")
        # The fix shape we want: ``nest_asyncio.apply()`` is inside a
        # conditional that's only entered on Python < 3.12.  Acceptable
        # guards:
        #   * ``if sys.version_info < (3, 12):``
        #   * ``if sys.version_info[:2] < (3, 12):``
        # The simplest expression is the first.
        guard_patterns = [
            r"if\s+_?sys\.version_info\s*<\s*\(3,\s*12\)\s*:",
            r"if\s+_?sys\.version_info\s*<\s*\(3,\s*12\)\s+or\s+",
        ]

        # Find every real ``nest_asyncio.apply()`` invocation.  We skip
        # matches inside strings / comments (e.g. ``r"nest_asyncio.apply() ..."``
        # in docstrings or ``# nest_asyncio.apply() raises ...`` in prose)
        # by stripping them out before searching.
        code_only = _strip_strings_and_comments(src)
        apply_calls = list(re.finditer(r"nest_asyncio\.apply\s*\(", code_only))
        assert apply_calls, (
            "Could not find any real nest_asyncio.apply() call in "
            "agent/cloud_api/endpoints.py — has the file been refactored? "
            "Update this test accordingly."
        )
        for call in apply_calls:
            # Look at the 600 chars preceding the apply call.  The guard
            # ``if sys.version_info < (3, 12):`` is on the line(s) just
            # above the try block.
            window = code_only[max(0, call.start() - 600) : call.start()]
            if not any(re.search(p, window) for p in guard_patterns):
                raise AssertionError(
                    "nest_asyncio.apply() in agent/cloud_api/endpoints.py "
                    "is not guarded by a Python 3.12 check.  This was the "
                    "root cause of the qasync NotImplementedError crash "
                    "documented in terminals/5.txt:448-465 — on Python "
                    "3.12+, applying nest_asyncio patches the qasync "
                    "QEventLoop class with a _run_once that calls "
                    "_selector.select(), which raises NotImplementedError."
                )

    def test_endpoints_documents_why_we_skip(self):
        """The guard must come with a comment explaining WHY — otherwise
        a future refactor will probably remove it (the unconditional
        apply() looked harmless for years).  This test pins the
        rationale so the next person who sees ``if sys.version_info <
        (3, 12):`` knows what it's protecting against.
        """
        # We need to look at the comment ABOVE the version guard, so
        # we keep the comments intact here.  We do strip strings (so
        # we don't accidentally match strings that mention version
        # numbers), but comments must stay for this test.
        code_only = _strip_strings(src := _read("agent/cloud_api/endpoints.py"))
        # Find the version guard and look 1000 chars above for a comment.
        guard_match = re.search(
            r"if\s+_?sys\.version_info\s*<\s*\(3,\s*12\)\s*:",
            code_only,
        )
        assert guard_match is not None, (
            "Could not find the version guard in endpoints.py — has the "
            "fix been removed?  See test_endpoints_skips_apply_on_python_312."
        )
        # Look at the 1000 chars preceding the guard for a comment that
        # mentions qasync, NotImplementedError, or 3.12.
        preceding = src[max(0, guard_match.start() - 1000) : guard_match.start()]
        keywords = ("qasync", "NotImplementedError", "3.12", "current_task")
        assert any(kw in preceding for kw in keywords), (
            "The version guard in endpoints.py needs a comment explaining "
            "why we skip nest_asyncio on Python 3.12+.  Without it, the "
            "next refactor will almost certainly drop the guard and "
            "re-introduce terminals/5.txt:448-465."
        )


class TestWanA2aChatAlreadyHasGuard:
    """``agent.chats.wan_a2a_chat`` already had the Python 3.12+ guard
    in place (see wan_a2a_chat.py:29-31).  This test pins it so a
    careless refactor doesn't accidentally drop it.
    """

    def test_wan_a2a_chat_skips_apply_on_312(self):
        src = _read("agent/chats/wan_a2a_chat.py")
        # The pre-existing shape:
        #     if _sys.version_info < (3, 12):
        #         import nest_asyncio
        #         nest_asyncio.apply()
        # Look for the explicit version guard followed by the apply call.
        assert re.search(
            r"if\s+_?sys\.version_info\s*<\s*\(3,\s*12\)\s*:",
            src,
        ), (
            "agent/chats/wan_a2a_chat.py is missing the Python 3.12 "
            "guard around nest_asyncio.apply().  This guard prevents "
            "the same NotImplementedError crash on qasync loops (see "
            "terminals/5.txt:448-465 and the rationale at "
            "agent/cloud_api/endpoints.py)."
        )
