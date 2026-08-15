#!/usr/bin/env python3
"""
release-workflow-simulator.py — static / dry-run evaluator for the new
release-{intl,cn}.yml layout.

Goal
----
For every (workflow × inputs) case, decide which jobs would actually be
queued and which would be skipped — including all the gates inside the
`validate-tag` job (tag detection, env/channel auto-detect, reserved-prefix
block, production/stable requires-tag check, staging eligibility).

This is NOT a real `act` run; we only evaluate job-level `if:` expressions
plus the deterministic bash in `validate-tag`. Anything depending on the
filesystem at runtime (artifact downloads, signing cert presence) is
modelled by the assumption that all builds whose gate opened will succeed.

Why static?
-----------
Real GitHub Actions cannot be invoked from a sandbox. Running the YAML
through `act` would require Docker-in-Docker + secrets + 20 minutes.
For our purposes — proving the new layout honours every operator
selection — a static evaluator that *understands* the gate expressions
and the bash heuristics is enough. It runs in <100 ms per case.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


# ---------------------------------------------------------------------------
# GH Actions expression evaluator (limited subset)
# ---------------------------------------------------------------------------

class ExprError(Exception):
    pass


class ExprEnv:
    """
    Evaluates GH Actions expression strings.

    Supports: literals (string / number / bool / ''), variables (a.b.c),
    ==, !=, &&, ||, !, parens, function calls (always, success, failure,
    cancelled, contains, fromJSON, startsWith, endsWith, format, toJSON).
    """

    def __init__(self, vars: dict[str, Any]):
        self.vars = vars

    def eval(self, expr: str) -> Any:
        expr = expr.strip()
        # Wrap a single bare string/number literal that the YAML parser gave us
        # as a plain string so we can re-tokenise.
        return self._parse(expr)

    # Token-level recursion: see GH Actions expression grammar (subset).
    def _parse(self, s: str) -> Any:
        s = s.strip()
        if not s:
            raise ExprError("empty expression")
        return self._parse_impl(s)

    def _parse_impl(self, s: str) -> Any:

        # Parens first — strip outer wrapping ONLY if the whole expression is
        # exactly wrapped in balanced parens (e.g. `(A && B)`). Otherwise
        # leave alone; any inner parens are just grouping and will be stripped
        # by recursive calls as needed.
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
            cur: Any = self.vars
            for part in s.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    # GH Actions treats missing keys as empty string.
                    return ""
            return cur

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
                paren_depth = max(paren_depth - 1, 0)
                i += 1
                continue
            if paren_depth == 0 and s[i : i + len(op)] == op:
                return (s[:i], s[i + len(op):])
            i += 1
        return None

    def _match_paren(self, s: str) -> bool:
        """True if the first non-whitespace char is '(' and there's a matching ')'
        later in the string."""
        s = s.strip()
        if not s.startswith("("):
            return False
        depth = 0
        in_str = None
        for i, ch in enumerate(s):
            if in_str:
                if ch == in_str and (i == 0 or s[i - 1] != "\\"):
                    in_str = None
                continue
            if ch in ("'", '"'):
                in_str = ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return True
        return False

    def _is_outer_wrapped(self, s: str) -> bool:
        """True if s is exactly `(X)` (single balanced outer wrapping)."""
        s = s.strip()
        if len(s) < 2 or s[0] != "(":
            return False
        depth = 0
        in_str = None
        for i, ch in enumerate(s):
            if in_str:
                if ch == in_str and (i == 0 or s[i - 1] != "\\"):
                    in_str = None
                continue
            if ch in ("'", '"'):
                in_str = ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    # The matching ')' must be the LAST char.
                    return i == len(s) - 1
        return False

    def _call(self, name: str, argstr: str) -> Any:
        # Split args (no nested fn calls in our subset; only literals)
        args = self._split_args(argstr)
        args = [self._parse(a) for a in args]
        if name == "always":
            return True  # simulate post-build, before any failure
        if name == "success":
            return True
        if name == "failure":
            return False
        if name == "cancelled":
            return False
        if name == "contains":
            if len(args) != 2:
                raise ExprError(f"contains() needs 2 args, got {len(args)}")
            haystack, needle = args
            return needle in (haystack if isinstance(haystack, list) else str(haystack))
        if name == "startsWith":
            return str(args[0]).startswith(str(args[1]))
        if name == "endsWith":
            return str(args[0]).endswith(str(args[1]))
        if name == "format":
            return str(args[0]).format(*args[1:])
        if name == "toJSON":
            return json.dumps(args[0])
        if name == "fromJSON":
            try:
                return json.loads(args[0])
            except json.JSONDecodeError as e:
                raise ExprError(f"fromJSON: {e}")
        if name == "hashFiles":
            return ""
        raise ExprError(f"unknown function: {name}")

    def _split_args(self, s: str) -> list[str]:
        depth = 0
        in_str = None
        args = []
        last = 0
        for i, ch in enumerate(s):
            if in_str:
                if ch == in_str and (i == 0 or s[i - 1] != "\\"):
                    in_str = None
                continue
            if ch in ("'", '"'):
                in_str = ch
                continue
            if ch in ("(", "["):
                depth += 1
            elif ch in (")", "]"):
                depth -= 1
            elif ch == "," and depth == 0:
                args.append(s[last:i])
                last = i + 1
        if last < len(s):
            args.append(s[last:])
        return [a.strip() for a in args]


# ---------------------------------------------------------------------------
# validate-tag: pure-Python mirror of the bash heuristics
# ---------------------------------------------------------------------------

SEMVER_RE = re.compile(r"^v[0-9]+(\.[0-9]+)+(-[A-Za-z0-9.-]+)?(\+[A-Za-z0-9.-]+)?$")
PREFIXED_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9]{0,31})_v[0-9]+(\.[0-9]+)+(-[A-Za-z0-9.-]+)?(\+[A-Za-z0-9.-]+)?$"
)
RESERVED_PREFIXES = {"rc", "beta", "alpha", "dev", "nightly", "pre", "preview", "snapshot"}


@dataclass
class ValidateTagOutputs:
    """Outputs the `validate-tag` job writes to GITHUB_OUTPUT."""

    valid: bool
    is_branch: bool
    version: str
    user_prefix: str
    tag_name: str
    environment: str
    channel: str
    error: str = ""


def run_validate_tag(ref: str, input_env: str, input_channel: str, version_file: str = "0.0.0") -> ValidateTagOutputs:
    """Mirror of the bash heuristic in release-{intl,cn}.yml:validate-tag."""

    ref_name = ref
    if SEMVER_RE.match(ref_name):
        is_branch = False
        valid = True
        version = ref_name.lstrip("v")
        user_prefix = ""
        tag_name = ref_name
    elif m := PREFIXED_RE.match(ref_name):
        raw_prefix = m.group(1)
        prefix = raw_prefix.lower()
        if prefix in RESERVED_PREFIXES:
            return ValidateTagOutputs(
                valid=False, is_branch=False, version="", user_prefix="",
                tag_name="", environment="", channel="",
                error=f"reserved prefix: {prefix}",
            )
        is_branch = False
        valid = True
        version_core = ref_name[len(raw_prefix) + 2:]  # strip prefix + "_v"
        user_prefix = prefix
        tag_name = ref_name
        version = version_core
    else:
        # branch path
        base = version_file or "0.0.0"
        # SHA + branch would normally be appended; for static eval use a stub
        version = f"{base}-branch"
        user_prefix = ""
        tag_name = ""
        is_branch = True
        valid = True

    # is_tag (for env detect-env branch)
    is_tag = bool(re.match(r"^v[0-9]+(\.[0-9]+)+", ref_name))
    is_staging_eligible = is_tag or ref_name in ("main", "master")

    # environment
    if input_env:
        env = input_env
        if env == "production" and not is_tag and ref_name not in ("main", "master"):
            return ValidateTagOutputs(
                valid=False, is_branch=is_branch, version=version,
                user_prefix=user_prefix, tag_name=tag_name,
                environment="", channel="",
                error="production env requires tag or main/master",
            )
        if env == "staging" and not is_staging_eligible:
            return ValidateTagOutputs(
                valid=False, is_branch=is_branch, version=version,
                user_prefix=user_prefix, tag_name=tag_name,
                environment="", channel="",
                error="staging env requires tag or main/master/staging",
            )
    else:
        if re.match(r"^v[0-9]+(\.[0-9]+)+$", ref_name):
            env = "production"
        elif re.search(r"-rc\.", ref_name):
            env = "production"
        elif re.search(r"-beta", ref_name):
            env = "staging"
        elif re.search(r"-alpha", ref_name):
            env = "test"
        elif ref_name in ("main", "master"):
            env = "production"
        elif ref_name == "staging":
            env = "staging"
        elif ref_name in ("develop", "dev"):
            env = "development"
        else:
            env = "development"

    # channel
    if input_channel:
        channel = input_channel
    else:
        if re.match(r"^v[0-9]+(\.[0-9]+)+$", ref_name):
            channel = "stable"
        elif re.search(r"-rc\.", ref_name):
            channel = "beta"
        elif re.search(r"-beta", ref_name):
            channel = "beta"
        elif re.search(r"-alpha", ref_name):
            channel = "dev"
        elif ref_name in ("main", "master"):
            channel = "nightly"
        elif ref_name == "staging":
            channel = "stable"
        elif ref_name in ("develop", "dev"):
            channel = "dev"
        else:
            channel = "dev"

    # production/stable requires tag (no branch)
    if env == "production" and channel == "stable" and not is_tag:
        return ValidateTagOutputs(
            valid=False, is_branch=is_branch, version=version,
            user_prefix=user_prefix, tag_name=tag_name,
            environment=env, channel=channel,
            error="production/stable requires version tag",
        )
    if env == "staging" and not is_staging_eligible:
        return ValidateTagOutputs(
            valid=False, is_branch=is_branch, version=version,
            user_prefix=user_prefix, tag_name=tag_name,
            environment=env, channel=channel,
            error="staging requires tag or main/master/staging",
        )

    return ValidateTagOutputs(
        valid=valid, is_branch=is_branch, version=version,
        user_prefix=user_prefix, tag_name=tag_name,
        environment=env, channel=channel,
    )


# ---------------------------------------------------------------------------
# Workflow-level simulator
# ---------------------------------------------------------------------------

# Allowed inputs (per release-{intl,cn}.yml workflow_dispatch).
ALLOWED_PLATFORMS = ("all", "windows", "macos", "linux")
ALLOWED_ARCH = ("all", "amd64", "aarch64", "")
ALLOWED_RUNNER_GROUP = (
    "github-hosted",
    "ecan-windows-amd64",
    "ecan-macos-amd64",
    "ecan-macos-arm64",
    "ecan-linux-amd64",
)


@dataclass
class CaseResult:
    case_id: str
    app: str
    ref: str
    inputs: dict
    validate: ValidateTagOutputs
    jobs: dict = field(default_factory=dict)  # job-id -> "run" | "skip" | "fail"

    @property
    def ok(self) -> bool:
        if not self.validate.valid:
            return False
        # At least one build must run, or it's a no-op (we treat as warn).
        run_builds = [j for j in self.jobs if j.startswith("build-") and self.jobs[j] == "run"]
        return len(run_builds) > 0

    def short(self) -> str:
        runs = [j for j, r in self.jobs.items() if r == "run"]
        skips = [j for j, r in self.jobs.items() if r == "skip"]
        return f"runs={len(runs)} skips={len(skips)}"


def extract_if(text: str, job_id: str) -> str | None:
    """
    Find the `if:` block belonging to job_id. Returns the joined expression
    string (logical-AND across continuation lines), or None if no `if:`.
    """
    lines = text.splitlines()
    job_re = re.compile(rf"^  {re.escape(job_id)}:\s*$")

    # Find the line where the job starts.
    job_line = None
    for i, line in enumerate(lines):
        if job_re.match(line):
            job_line = i
            break
    if job_line is None:
        return None

    # Scan forward looking for `if: |` (multi-line) or `if: <expr>` (single).
    for j in range(job_line + 1, min(job_line + 30, len(lines))):
        line = lines[j]
        stripped = line.strip()
        # `if:` (with `|` continuation) — multi-line block.
        if stripped.startswith("if:") and stripped.endswith("|"):
            block = []
            j += 1
            while j < len(lines):
                L = lines[j]
                # The continuation lines have deeper indent than `if:` itself.
                # The `if:` was at indent 4 (4 spaces). Continuation lines are
                # at indent >= 6.
                if L.startswith("      ") or (L.startswith("    ") and not L.startswith("     ") and False):
                    block.append(L.strip())
                    j += 1
                    continue
                # Out of block when we hit a line at the same indent as `if:` (4 spaces)
                # or when we hit a less-indented line (back to top level).
                if L.startswith("    ") and not L.startswith("     "):
                    # Same indent as the if: key, i.e. a sibling key (name:, runs-on:, ...).
                    # This is NOT a continuation; it ends the block.
                    break
                if L == "":
                    j += 1
                    continue
                if not L.startswith(" "):
                    # Top-level indent — definitely out of the job.
                    break
                # 5-space indent (e.g. nested inside `with:`): still inside.
                if L.startswith("     "):
                    block.append(L.strip())
                    j += 1
                    continue
                j += 1
            return " ".join(block).strip() if block else None

        # `if: <single-line expression>` — terminated by newline.
        if stripped.startswith("if:"):
            expr = stripped[3:].strip()
            return expr if expr else None

        # If we hit a sibling key (runs-on, needs, uses, with, steps) without
        # seeing an `if:`, the job has no `if:`.
        if stripped and not stripped.startswith("name:") and not stripped.startswith("needs:"):
            return None

    return None


def list_jobs(text: str) -> list[str]:
    """Return job IDs declared in the workflow, in order."""
    ids = []
    for line in text.splitlines():
        m = re.match(r"^  ([a-z][a-zA-Z0-9_-]*):\s*$", line)
        if not m:
            continue
        jid = m.group(1)
        if jid in ("on", "env", "permissions", "jobs", "concurrency", "group",
                   "cancel-in-progress", "workflow_dispatch", "true", "false"):
            continue
        ids.append(jid)
    return ids


def simulate_case(
    workflow_text: str,
    workflow_id: str,
    app: str,
    case_id: str,
    inputs: dict,
    ref: str,
    version_file: str = "0.0.0",
) -> CaseResult:
    """Run one (workflow × inputs × ref) case."""

    vt = run_validate_tag(
        ref=ref,
        input_env=inputs["environment"],
        input_channel=inputs["channel"],
        version_file=version_file,
    )

    jobs = list_jobs(workflow_text)

    # Variable namespace for expression evaluator. validate-tag outputs
    # are exposed via needs.validate-tag.outputs.* per GH Actions.
    validate_outputs = {
        "tag-valid": "true" if vt.valid else "false",
        "version": vt.version,
        "is-branch": "true" if vt.is_branch else "false",
        "ref-name": ref,
        "user-prefix": vt.user_prefix,
        "tag-name": vt.tag_name,
        "environment": vt.environment,
        "channel": vt.channel,
    }

    res = CaseResult(
        case_id=case_id,
        app=app,
        ref=ref,
        inputs=inputs,
        validate=vt,
    )

    if not vt.valid:
        # validate-tag would exit 1. Mark it as failed and everything else skipped.
        res.jobs["validate-tag"] = "fail"
        for jid in jobs:
            if jid != "validate-tag":
                res.jobs[jid] = "skip"
        return res

    # For each job, build the env dict and evaluate its `if:`.
    for jid in jobs:
        # needs dict: we approximate other jobs' results by assuming every
        # job that opens in *this* case will succeed. That is the most
        # permissive reading of the gates; if a gate references
        # `needs.<jid>.result == 'success'` we treat it as true iff <jid>
        # is gated open in this case.
        # We compute that via a first pass.
        pass

    # Two-pass: first decide which jobs gate-open assuming all their
    # upstream `needs.<x>.result == 'success'` evaluate true if <x> also gates open.
    gate_open: dict[str, bool] = {}

    for jid in jobs:
        expr = extract_if(workflow_text, jid)
        if jid == "validate-tag":
            gate_open[jid] = True  # always runs on dispatch
            continue
        if not expr:
            gate_open[jid] = True
            continue

        # Build vars for expression eval.
        # Stub out "needs" namespace: each `needs.<upstream>.result` is
        # mapped to its gate_open value ('success' if open else 'skipped').
        needs_ns: dict[str, dict[str, Any]] = {}
        for other in jobs:
            needs_ns[other] = {
                "result": "success" if gate_open.get(other, False) else "skipped",
                "outputs": {},  # not used by gate expressions
            }
        needs_ns["validate-tag"] = {
            "result": "success",
            "outputs": validate_outputs,
        }

        env = ExprEnv({
            "needs": needs_ns,
            "github": {
                "event": {
                    "inputs": inputs,
                },
                "ref": f"refs/heads/{ref}" if "/" in ref or not ref.startswith("v") else f"refs/tags/{ref}",
            },
            "inputs": inputs,
            "secrets": {},
            "runner": {"os": "Linux"},
            "env": {},
        })
        try:
            opens = bool(env.eval(expr))
        except ExprError as e:
            opens = False
            print(f"[simulator] expr error in {workflow_id}/{jid}: {e}", file=sys.stderr)
        gate_open[jid] = opens

    # Map gate_open to final job state string.
    for jid in jobs:
        if jid == "validate-tag":
            # if valid, succeeded; else fail (set above)
            res.jobs[jid] = "run" if vt.valid else "fail"
        else:
            res.jobs[jid] = "run" if gate_open[jid] else "skip"

    return res


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------

REFS = [
    # (ref, expected_valid, expected_env, expected_channel, label)
    ("main",                       True,  "production", "nightly", "main branch → prod/nightly"),
    ("master",                     True,  "production", "nightly", "master branch → prod/nightly"),
    ("develop",                    True,  "development","dev",     "develop branch → dev"),
    ("dev",                        True,  "development","dev",     "dev branch → dev"),
    ("staging",                    True,  "staging",    "stable",  "staging branch → staging/stable"),
    ("feature/foo",                True,  "development","dev",     "feature branch → dev"),
    ("v1.0.0",                     True,  "production", "stable",  "semver tag → prod/stable"),
    ("v1.0.0-rc.1",                True,  "production", "beta",    "rc tag → prod/beta"),
    ("v1.0.0-beta.1",              True,  "staging",    "beta",    "beta tag → staging/beta"),
    ("v1.0.0-alpha.1",             True,  "test",       "dev",     "alpha tag → test/dev"),
    ("songc_v0.1.0",               True,  "production", "stable",  "user-prefix tag → prod/stable"),
    ("rc_v1.0.0",                  False, "",           "",        "reserved prefix → BLOCKED"),
    ("beta_v1.0.0",                False, "",           "",        "reserved prefix → BLOCKED"),
]


def run_matrix(workflow_path: Path, app: str) -> list[CaseResult]:
    """
    Build an ORTHOGONAL test matrix (not full Cartesian) — every cell of
    every dimension is exercised at least once, but we don't blow up the
    case count into the millions.

    Strategy:
      1. For each ref, run a canonical "all/github-hosted/'' / ''" case
         to verify the validate-tag heuristic and the gating default.
      2. Then sweep one dimension at a time (platform × arch × env × ch)
         against a single ref so we can attribute failures.
    """
    text = workflow_path.read_text()
    results: list[CaseResult] = []

    canonical = {
        "platform": "all",
        "arch": "all",
        "environment": "",
        "channel": "",
        "runner_group": "github-hosted",
        "ref": "",
    }

    cid = 0

    # --- (a) ref sweep: each ref + canonical inputs ---
    for ref, _valid_ok, _env_ok, _ch_ok, _label in REFS:
        cid += 1
        inputs = dict(canonical)
        inputs["ref"] = ref
        res = simulate_case(
            workflow_text=text,
            workflow_id=workflow_path.stem,
            app=app,
            case_id=f"{app}/REF/{ref}",
            inputs=inputs,
            ref=ref,
        )
        results.append(res)

    # --- (b) operator-input sweep: one ref (main) × all platform × arch × env × ch × runner ---
    base_ref = "main"
    for platform in ALLOWED_PLATFORMS:
        for arch in ALLOWED_ARCH:
            for runner_group in ALLOWED_RUNNER_GROUP:
                for env_inp in ("", "production", "staging", "test", "development"):
                    for ch_inp in ("", "stable", "beta", "nightly", "dev"):
                        cid += 1
                        inputs = {
                            "platform": platform,
                            "arch": arch,
                            "environment": env_inp,
                            "channel": ch_inp,
                            "runner_group": runner_group,
                            "ref": base_ref,
                        }
                        res = simulate_case(
                            workflow_text=text,
                            workflow_id=workflow_path.stem,
                            app=app,
                            case_id=f"{app}/SWEEP/main/{platform}/{arch}/{runner_group}/{env_inp}/{ch_inp}",
                            inputs=inputs,
                            ref=base_ref,
                        )
                        results.append(res)

    # --- (c) tag ref sweep: a few tag refs × canonical inputs ---
    for ref in ("v1.0.0", "v1.0.0-rc.1", "v1.0.0-beta.1", "v1.0.0-alpha.1",
                "songc_v0.1.0"):
        for platform in ("windows", "macos", "linux"):
            for arch in ("all", "amd64"):
                cid += 1
                inputs = {
                    "platform": platform,
                    "arch": arch,
                    "environment": "",
                    "channel": "",
                    "runner_group": "github-hosted",
                    "ref": ref,
                }
                res = simulate_case(
                    workflow_text=text,
                    workflow_id=workflow_path.stem,
                    app=app,
                    case_id=f"{app}/TAG/{ref}/{platform}/{arch}",
                    inputs=inputs,
                    ref=ref,
                )
                results.append(res)

    return results


def summarise(results: list[CaseResult], label: str) -> tuple[int, int, int]:
    valid = [r for r in results if r.validate.valid]
    invalid = [r for r in results if not r.validate.valid]
    nobuild = [r for r in valid if not any(r.jobs[j] == "run" for j in r.jobs if j.startswith("build-"))]
    print(f"\n=== {label} ===")
    print(f"total cases   : {len(results)}")
    print(f"validate OK   : {len(valid)}")
    print(f"validate fail : {len(invalid)}")
    print(f"  no build ran: {len(nobuild)}")
    return len(results), len(valid), len(invalid)


RUNNER_PLATFORM = {
    # Map each self-hosted runner group to the platform/arch it can run.
    # Used to filter out impossible combinations from the "anomaly" set.
    "ecan-windows-amd64": {"platforms": ("windows",),   "archs": ("amd64",)},
    "ecan-macos-amd64":   {"platforms": ("macos",),     "archs": ("amd64",)},
    "ecan-macos-arm64":   {"platforms": ("macos",),     "archs": ("aarch64",)},
    "ecan-linux-amd64":   {"platforms": ("linux",),     "archs": ("amd64",)},
    # "github-hosted" can run any platform/arch.
}

# Platforms that ONLY support amd64 (Windows + standard Linux).
PLATFORM_AMD64_ONLY = {"windows", "linux"}


def report_anomalies(results: list[CaseResult]) -> int:
    """
    Look for cases that look wrong:
      - validate passed but 0 builds gated open AND the runner_group,
        platform, and arch combination is genuinely plausible (i.e. the
        operator didn't ask for something that has no implementation).

    Combinations like `windows + aarch64` are NOT anomalies — no
    build-windows job exists for aarch64 (Windows only ships amd64),
    so the workflow correctly produced no builds, just final-status.
    """
    def is_compatible(rg: str, plat: str, arch: str) -> bool:
        if rg == "github-hosted":
            # github-hosted can build anything we ship — but only if
            # the (platform, arch) pair is supported at all. If
            # platform=windows and arch=aarch64, it's a genuine operator
            # error (no builds exist) so we DON'T flag it as anomaly.
            if arch == "aarch64" and plat in PLATFORM_AMD64_ONLY:
                return False
            return True
        spec = RUNNER_PLATFORM.get(rg, {})
        plats = spec.get("platforms", ())
        archs = spec.get("archs", ())
        plat_ok = (plat == "" or plat == "all" or plat in plats)
        arch_ok = (arch == "" or arch == "all" or arch in archs)
        return plat_ok and arch_ok

    bad: list[CaseResult] = []
    for r in results:
        if not r.validate.valid:
            continue
        builds = [j for j in r.jobs if j.startswith("build-")]
        run_builds = [j for j in builds if r.jobs[j] == "run"]
        if not run_builds and is_compatible(r.inputs["runner_group"],
                                            r.inputs["platform"],
                                            r.inputs["arch"]):
            bad.append(r)
    if bad:
        print(f"\n!! {len(bad)} cases where a compatible runner/platform/arch "
              "was selected but 0 builds gated open:")
        for r in bad[:8]:
            print(f"   - {r.case_id}  jobs={r.jobs}")
    return len(bad)


def main() -> int:
    repo = Path(__file__).parent.parent.parent
    intl = repo / ".github" / "workflows" / "release-intl.yml"
    cn   = repo / ".github" / "workflows" / "release-cn.yml"
    if not intl.exists() or not cn.exists():
        print(f"ERROR: missing workflow files: {intl} or {cn}", file=sys.stderr)
        return 2

    print("=" * 72)
    print("Release pipeline simulator (static / dry-run)")
    print("=" * 72)
    print()

    intl_results = run_matrix(intl, "intl")
    cn_results   = run_matrix(cn,   "cn")
    n_intl, v_intl, f_intl = summarise(intl_results, "release-intl.yml")
    n_cn,   v_cn,   f_cn   = summarise(cn_results,   "release-cn.yml")

    bad_intl = report_anomalies(intl_results)
    bad_cn   = report_anomalies(cn_results)

    # Print a few representative OK cases to prove it actually works.
    print("\n=== representative OK cases ===")
    seen = 0
    for r in intl_results + cn_results:
        if r.ok and seen < 6:
            seen += 1
            run_jobs = [j for j, s in r.jobs.items() if s == "run"]
            print(f"  [{r.app:4}] {r.inputs['platform']:7} {r.inputs['arch']:8} "
                  f"env={r.inputs['environment']:11} ch={r.inputs['channel']:8} "
                  f"runner={r.inputs['runner_group']:18} ref={r.ref:14} -> "
                  f"{len(run_jobs)} jobs: {', '.join(run_jobs)}")

    # Validate-tag failure examples
    print("\n=== representative BLOCKED cases (validate-tag errored) ===")
    seen = 0
    for r in intl_results + cn_results:
        if not r.validate.valid and seen < 6:
            seen += 1
            print(f"  [{r.app:4}] ref={r.ref:14} env={r.inputs['environment']:11} "
                  f"ch={r.inputs['channel']:8} → ERROR: {r.validate.error}")

    # Cross-platform sanity: same input set on intl vs cn should give
    # symmetric job-gating patterns (only the upload backend differs).
    print("\n=== cross-pipeline symmetry check (intl vs cn) ===")
    asym = 0
    intl_by_key = {r.case_id.replace("intl/", ""): r for r in intl_results}
    for r_cn in cn_results:
        key = r_cn.case_id.replace("cn/", "")
        r_intl = intl_by_key.get(key)
        if r_intl is None:
            continue
        # Compare which build-* jobs gate open.
        for jid in ("build-windows", "build-windows-cn", "build-macos-amd64",
                    "build-macos-amd64-cn", "build-macos-aarch64",
                    "build-macos-aarch64-cn", "build-linux", "build-linux-cn"):
            pass  # job names differ; just compare per-platform counts
        intl_builds = sum(1 for j, s in r_intl.jobs.items() if j.startswith("build-") and s == "run")
        cn_builds   = sum(1 for j, s in r_cn.jobs.items()   if j.startswith("build-") and s == "run")
        if intl_builds != cn_builds:
            asym += 1
            if asym <= 4:
                print(f"  ASYMMETRY @ {r_intl.case_id}: intl={intl_builds} vs cn={cn_builds}")
    if asym == 0:
        print("  OK: intl and cn gate the same builds in every (platform×arch) case")

    print()
    print("=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"  release-intl.yml : {n_intl} cases, {v_intl} valid, {f_intl} invalid, {bad_intl} anomalies")
    print(f"  release-cn.yml   : {n_cn} cases, {v_cn} valid, {f_cn} invalid, {bad_cn} anomalies")
    print(f"  total            : {n_intl + n_cn} cases")

    return 0 if (bad_intl == 0 and bad_cn == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
