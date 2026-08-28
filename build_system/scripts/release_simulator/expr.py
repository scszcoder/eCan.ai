"""
GitHub Actions expression evaluator.

Reused by the legacy 4086-case static simulator
(`release-workflow-simulator.py`) and the new full executor
(`release_simulator.runner`). Kept as a thin standalone module so it
can be unit-tested in isolation and so the two simulators cannot drift
in their understanding of ${{ ... }} semantics.

Supports a deliberate subset of GH Actions expressions — enough for
eCan.ai's release pipelines:

  * Literals: strings, numbers, booleans, empty string
  * Variables: dotted paths (a.b.c) with GH's empty-string-on-miss rule
  * Operators: ==, !=, &&, ||, !, parens
  * Functions: always, success, failure, cancelled,
               contains, fromJSON, startsWith, endsWith, format, toJSON
"""

from __future__ import annotations

import json
import re
from typing import Any


class ExprError(Exception):
    """Raised when an expression cannot be parsed or evaluated."""


class ExprEnv:
    """
    Evaluator for a single ${{ ... }} expression body.

    Construct with the variable namespace (`github`, `needs`, `secrets`,
    `inputs`, `runner`, `env`, ...) and call `eval(expr_str)`.
    """

    def __init__(self, vars: dict[str, Any]):
        self.vars = vars

    def eval(self, expr: str) -> Any:
        expr = expr.strip()
        return self._parse(expr)

    # ---- public helpers (small surface so callers/tests don't reach in) ----

    def lookup(self, path: str) -> Any:
        """
        Resolve a dotted variable path against the namespace. Returns
        empty string if any segment is missing — matching GH Actions
        behaviour for ${{ foo.bar.baz }} where any of foo/bar/baz is
        undefined.
        """
        cur: Any = self.vars
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return ""
        return cur

    # ---- internal parse tree (recursive descent over a small grammar) ----

    def _parse(self, s: str) -> Any:
        s = s.strip()
        if not s:
            raise ExprError("empty expression")
        return self._parse_impl(s)

    def _parse_impl(self, s: str) -> Any:

        # Parens first — strip outer wrapping ONLY if the whole
        # expression is exactly wrapped in balanced parens (e.g.
        # `(A && B)`). Otherwise leave alone; any inner parens are just
        # grouping and will be stripped by recursive calls as needed.
        if self._is_outer_wrapped(s):
            return self._parse(s[1:-1])

        # Boolean ops at top level — left-associative.
        # In GH Actions (and most C-style precedence), `&&` binds tighter
        # than `||`. To honour that precedence we split on `||` FIRST at
        # the top level: `||` is the lowest-precedence operator so it
        # should appear at the outermost (top-level) split. Only when
        # `||` is absent do we split on `&&`. Reversing this order (the
        # original implementation tried `&&` first) caused expressions
        # like `(A || B) && 'success' || 'failure'` to split on the
        # `&&` and never reach the outer `||`, losing the entire
        # ternary-style "fallback to 'failure'" semantics.
        for op in ("||", "&&"):
            parts = self._split_outside_parens(s, op)
            if parts:
                left = self._parse(parts[0])
                right = self._parse(parts[1])
                if op == "||":
                    return left or right
                return left and right

        # Unary ! prefix
        if s.startswith("!"):
            return not self._parse(s[1:])

        # Function call: name(arg, arg, ...)
        m = re.match(r"^([a-zA-Z_]+)\((.*)\)$", s)
        if m:
            return self._call(m.group(1), m.group(2))

        # Literal number
        if re.match(r"^-?\d+(\.\d+)?$", s):
            return float(s) if "." in s else int(s)

        # Literal bool
        if s == "true":
            return True
        if s == "false":
            return False

        # String literal (single or double quoted). The whole input must
        # be exactly one quoted literal — starts AND ends with the same
        # quote AND no other unescaped quote of that kind in the middle.
        # The previous check (startswith + endswith only) misclassified
        # expressions like "'foo' == 'foo'" as a single string because
        # both ends happened to be a single quote.
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
            quote = s[0]
            body = s[1:-1]
            i = 0
            ok = True
            while i < len(body):
                if body[i] == "\\" and i + 1 < len(body):
                    i += 2
                    continue
                if body[i] == quote:
                    ok = False
                    break
                i += 1
            if ok:
                return body

        # Comparison (== or !=) — same-precedence left-to-right, lower than
        # function call but higher than boolean ops.
        for op, fn in (("==", lambda a, b: a == b), ("!=", lambda a, b: a != b)):
            parts = self._split_outside_parens(s, op)
            if parts:
                return fn(self._parse(parts[0]), self._parse(parts[1]))

        # Variable (dotted path). GH Actions allows `needs.<job_id>.<path>`
        # where `<job_id>` and intermediate identifiers can contain `-`.
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_.\-]*$", s):
            return self.lookup(s)

        raise ExprError(f"cannot parse expression: {s!r}")

    def _split_outside_parens(self, s: str, op: str):
        """
        Split s on the FIRST occurrence of op that is outside any string
        literal AND outside any unmatched paren block.

        Parens DO block: an `op` inside `(...)` is part of the operand
        expression and will be handled by recursive calls once the outer
        paren is stripped by `_is_outer_wrapped`. The previous behaviour
        of splitting through parens worked only when the caller happened
        to split on the LOWEST-precedence operator at the top level;
        combined with the inverted `&&`/`||` split order it produced
        incorrect parses for `&&` inside `(...)`.

        Returns (left, right) or None if op is not found outside both
        strings and parens.
        """
        in_str: str | None = None
        paren_depth = 0
        i = 0
        while i < len(s):
            ch = s[i]
            if in_str:
                if ch == in_str and (i == 0 or s[i - 1] != "\\"):
                    in_str = None
                i += 1
                continue
            if ch in ("'", '"'):
                in_str = ch
                i += 1
                continue
            if ch == "(":
                paren_depth += 1
                i += 1
                continue
            if ch == ")":
                paren_depth -= 1
                i += 1
                continue
            if paren_depth == 0 and s[i:i + len(op)] == op:
                # Make sure it's a token boundary — surrounded by
                # whitespace or start/end of string — so we don't split
                # inside identifiers like 'foo&&bar'.
                left_ok = (i == 0) or s[i - 1] in " \t"
                right_ok = (i + len(op) == len(s)) or s[i + len(op)] in " \t"
                if left_ok and right_ok:
                    return s[:i], s[i + len(op):]
                i += 1
                continue
            i += 1
        return None

    def _is_outer_wrapped(self, s: str) -> bool:
        """True iff s starts with '(' and ends with ')' AND that '(' is
        matched by the trailing ')' at depth zero (i.e. it's a true outer
        wrap, not just a tail-paren)."""
        if not (s.startswith("(") and s.endswith(")")):
            return False
        depth = 0
        in_str = None
        for i, ch in enumerate(s):
            if in_str:
                if ch == in_str and s[i - 1] != "\\":
                    in_str = None
                continue
            if ch in ("'", '"'):
                in_str = ch
                continue
            if ch == "(":
                depth += 1
                if depth == 1 and i != 0:
                    return False
                continue
            if ch == ")":
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    return False
        return depth == 0

    # ---- built-in functions (subset) ----

    def _call(self, name: str, args_str: str) -> Any:
        args = self._split_args(args_str)
        evaled = [self._parse(a) for a in args]

        if name == "always":
            return True
        if name == "success":
            # Without a job context we treat the active job as success.
            # For `if: always() && ...` patterns this is good enough; the
            # full executor overrides this per-job with the real result.
            return True
        if name == "failure":
            return False
        if name == "cancelled":
            return False
        if name == "contains":
            if len(evaled) != 2:
                raise ExprError(f"contains() takes 2 args, got {len(evaled)}")
            haystack = evaled[0] or ""
            needle = evaled[1] or ""
            return needle in haystack
        if name == "startsWith":
            if len(evaled) != 2:
                raise ExprError(f"startsWith() takes 2 args, got {len(evaled)}")
            return str(evaled[0] or "").startswith(str(evaled[1] or ""))
        if name == "endsWith":
            if len(evaled) != 2:
                raise ExprError(f"endsWith() takes 2 args, got {len(evaled)}")
            return str(evaled[0] or "").endswith(str(evaled[1] or ""))
        if name == "format":
            if not evaled:
                return ""
            tmpl = str(evaled[0])
            return tmpl.format(*evaled[1:])
        if name == "fromJSON":
            if len(evaled) != 1:
                raise ExprError(f"fromJSON() takes 1 arg, got {len(evaled)}")
            try:
                return json.loads(evaled[0] or "")
            except (json.JSONDecodeError, TypeError) as e:
                raise ExprError(f"fromJSON() bad input: {e}") from e
        if name == "toJSON":
            return json.dumps(evaled[0] if evaled else None)

        raise ExprError(f"unknown function: {name}")

    def _split_args(self, s: str) -> list[str]:
        """Split a function-arg list on top-level commas, respecting
        strings and parens."""
        args: list[str] = []
        buf: list[str] = []
        in_str = None
        paren = 0
        for ch in s:
            if in_str:
                buf.append(ch)
                if ch == in_str and (not buf or buf[-2] != "\\"):
                    in_str = None
                continue
            if ch in ("'", '"'):
                in_str = ch
                buf.append(ch)
                continue
            if ch == "(":
                paren += 1
                buf.append(ch)
                continue
            if ch == ")":
                paren -= 1
                buf.append(ch)
                continue
            if ch == "," and paren == 0:
                args.append("".join(buf))
                buf = []
                continue
            buf.append(ch)
        if buf:
            args.append("".join(buf))
        return [a.strip() for a in args if a.strip()]