#!/usr/bin/env python3
"""Read / validate / write the OTA grayscale rollout control file.

The rollout file lives next to the appcast inside the OTA bucket:

    {env_prefix}/channels/{channel}/rollout.json

It is the single control plane for *who* is offered an update:

    {"schema": 1, "version": "0.8.0", "percent": 20, "paused": false,
     "cohort_include_prefix": [], "updated_at": "2026-10-01T10:00:00+00:00"}

Client side (``ota/core/rollout.py``) reads it on every update check:

    * ``paused``             → nobody is prompted (kill switch)
    * ``cohort`` whitelist   → matching login-email prefixes always pass
    * ``bucket < percent``   → sha256(install_id@version) % 100 < percent

A missing / unreadable file means FULLY OPEN (percent 100) so the control
plane can never become a single point of failure for updates. That is also
the default posture: promote with ``--percent 100`` and nothing changes
versus the pre-rollout behaviour.

Modes
-----

    # status only (used by ota-status.yml and the promote resolve step)
    python3 set_rollout.py --app cn --env production --channel stable --status

    # guard a change without writing (exit 3 on violation)
    python3 set_rollout.py --app cn --env production --action ramp --percent 50

    # guard + write
    python3 set_rollout.py --app cn --env production \
        --action promote --percent 100 --version 0.8.0 --apply

Stdout carries a single JSON document; human-readable lines go to stderr.
A markdown summary is appended to ``--summary <path>`` when given (the
promote workflow points this at ``$GITHUB_STEP_SUMMARY``).

Exit codes
----------
0  OK
1  config / storage error
3  guard violation (nothing written)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from generate_appcast import AppcastGenerator, _split_release_dir  # noqa: E402

ROLLOUT_SCHEMA = 1
ROLLOUT_FILENAME = "rollout.json"
DEFAULT_PERCENT = 100  # fully open

ACTIONS = ("promote", "ramp", "reduce", "pause", "resume", "rollback")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested without storage)
# ---------------------------------------------------------------------------

def normalize_version(version: Optional[str]) -> str:
    """Return the bare version core ('0.8.0') or '' for empty input.

    Rejects user-prefixed release dirs by returning the raw core — the
    caller (plan) validates universal-only membership against the bucket.
    """
    if not version:
        return ""
    raw = str(version).strip()
    if not raw:
        return ""
    _prefix, core = _split_release_dir(raw)
    return core or raw


def normalize_cohort(text: Optional[str]) -> List[str]:
    """'Alice, bob ,alice' -> ['alice', 'bob'] (lower-cased, deduped)."""
    if not text:
        return []
    out: List[str] = []
    for part in str(text).replace(" ", ",").split(","):
        p = part.strip().lower()
        if p and p not in out:
            out.append(p)
    return out


def normalize_exclude(text: Optional[str]) -> List[str]:
    """'v0.9.0, 0.9.0 ,0.8.0' -> ['0.9.0', '0.8.0'] (bare cores, deduped).

    Versions normalize through :func:`normalize_version` so a manual
    ``v0.9.0`` and an auto-derived ``0.9.0`` collapse to one entry.
    """
    out: List[str] = []
    if not text:
        return out
    for part in str(text).replace(" ", ",").split(","):
        core = normalize_version(part)
        if core and core not in out:
            out.append(core)
    return out


def normalize_rollout(raw: Optional[dict]) -> Dict[str, Any]:
    """Fill defaults / clamp fields. Never raises — invalid ⇒ open default."""
    out: Dict[str, Any] = {
        "schema": ROLLOUT_SCHEMA,
        "version": "",
        "percent": DEFAULT_PERCENT,
        "paused": False,
        "cohort_include_prefix": [],
        "updated_at": "",
    }
    if not isinstance(raw, dict):
        return out
    try:
        out["version"] = str(raw.get("version") or "").strip()
    except Exception:
        out["version"] = ""
    try:
        pct = int(raw.get("percent", DEFAULT_PERCENT))
        out["percent"] = max(0, min(100, pct))
    except Exception:
        out["percent"] = DEFAULT_PERCENT
    out["paused"] = bool(raw.get("paused", False))
    cohort = raw.get("cohort_include_prefix")
    if isinstance(cohort, list):
        out["cohort_include_prefix"] = [
            str(c).strip().lower() for c in cohort if str(c).strip()
        ]
    out["updated_at"] = str(raw.get("updated_at") or "")
    if isinstance(raw.get("schema"), int):
        out["schema"] = raw["schema"]
    return out


def plan(
    action: str,
    percent: Optional[int],
    version: Optional[str],
    cohort: Optional[str],
    status: Dict[str, Any],
    store: Any = None,
    exclude: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide what an action would change. Returns the plan dict.

    ``store`` is only consulted for the release-exists/signed probe
    (promote / rollback); tests pass a fake. Never writes anything.

    ``exclude`` is the operator's manual comma-separated list of
    versions to drop from the feeds. For ``rollback`` the bad version
    is additionally derived automatically (latest.json's current
    version + the current rollout's version, minus the rollback
    target) so a forgotten ``--exclude`` cannot silently turn the
    rollback into a no-op. The union lands in ``resolved["exclude"]``
    for the workflow's feed-regeneration steps.
    """
    errors: List[str] = []
    warnings: List[str] = []
    cur: Dict[str, Any] = status["rollout"]
    exists: bool = status["rollout_exists"]
    available: List[Dict[str, str]] = status.get("available") or []
    available_versions = {a["version"] for a in available}
    published = status.get("published_version") or ""
    manual_exclude = normalize_exclude(exclude)

    resolved: Dict[str, Any] = {
        "target_version": "",
        "publish": action in ("promote", "rollback"),
        "write": True,
        "smoke": action in ("promote", "rollback"),
        "exclude": "",
    }
    result = dict(cur)

    # Which version does this action operate on?
    target = ""
    if action in ("promote", "rollback"):
        if version:
            target = normalize_version(version)
        elif action == "promote":
            target = available[0]["version"] if available else ""
        if not target:
            if action == "rollback":
                errors.append(
                    "action=rollback requires --version (the version to roll back TO)"
                )
            else:
                errors.append(
                    "no --version given and no releases found under "
                    f"{status.get('env_prefix', '')}/releases/"
                )
        else:
            if target not in available_versions:
                errors.append(
                    f"version {target} is not a universal release under "
                    f"{status.get('env_prefix', '')}/releases/ "
                    f"(available: {', '.join(sorted(available_versions)) or 'none'})"
                )
            elif store is not None:
                release_dir = next(
                    (a["dir"] for a in available if a["version"] == target), ""
                )
                if not store.release_has_sha256(release_dir):
                    errors.append(
                        f"version {target} has no .sha256 under "
                        f"releases/{release_dir}/ — upload incomplete, "
                        "refusing to publish"
                    )
        resolved["target_version"] = target

    if action == "promote":
        if percent is None:
            percent = DEFAULT_PERCENT
        percent = max(0, min(100, int(percent)))
        if exists and bool(cur.get("paused")):
            warnings.append(
                "current rollout is paused — promote resumes it "
                "(writes paused=false)"
            )
        if target and published and target == published:
            warnings.append(
                f"target {target} is already the published version "
                "(idempotent re-publish)"
            )
        result = {
            "schema": ROLLOUT_SCHEMA,
            "version": target,
            "percent": percent,
            "paused": False,
            "cohort_include_prefix": normalize_cohort(cohort),
            "updated_at": _now(),
        }
        resolved["exclude"] = ",".join(manual_exclude)
        if percent == 0 and not result["cohort_include_prefix"]:
            warnings.append(
                "percent=0 with an empty cohort: nobody will be offered the "
                "update (internal-verification mode)"
            )
        if percent == DEFAULT_PERCENT and result["cohort_include_prefix"]:
            warnings.append(
                "cohort has no effect at percent=100 (everyone passes the "
                "percentage gate)"
            )

    elif action == "rollback":
        if percent is not None:
            warnings.append("percent is ignored for rollback (kept as-is)")
        if cohort:
            warnings.append("cohort is ignored for rollback (kept as-is)")
        result = dict(cur)
        result["version"] = target
        result["updated_at"] = _now()

        # Auto-derive the versions to drop from the feeds: whatever
        # latest.json currently advertises plus whatever the current
        # rollout governs, minus the rollback target. Without this a
        # forgotten --exclude re-lists the bad version as the newest
        # appcast item and the rollback silently stops rolling back.
        derived: List[str] = []
        if target:
            for cand in (published, normalize_version(cur.get("version"))):
                if cand and cand != target and cand not in derived:
                    derived.append(cand)
        merged = list(derived)
        for core in manual_exclude:
            if core not in merged:
                merged.append(core)
        resolved["exclude"] = ",".join(merged)
        if target and not merged:
            warnings.append(
                "no versions to exclude (latest.json and the current "
                "rollout already point at the target?) — regenerating the "
                "feeds will keep offering the newest release; pass "
                "--exclude explicitly if a version must be dropped"
            )
        kept_percent = int(cur.get("percent", DEFAULT_PERCENT))
        if kept_percent < DEFAULT_PERCENT:
            warnings.append(
                f"rollback keeps percent={kept_percent} — clients below "
                f"{target or 'the target'} remain gated at that percent; "
                "use action=ramp to widen"
            )
        if bool(cur.get("paused")):
            warnings.append(
                "rollout is currently paused — rollback keeps it paused; "
                "use action=resume when the fleet should move again"
            )

    elif action in ("ramp", "reduce"):
        if percent is None:
            errors.append(f"action={action} requires --percent")
        elif not exists:
            errors.append(
                f"no {ROLLOUT_FILENAME} at {status.get('rollout_key', '')} — "
                "run action=promote first (ramp/reduce only adjust an "
                "existing rollout)"
            )
        else:
            percent = max(0, min(100, int(percent)))
            current = int(cur["percent"])
            if action == "ramp" and percent < current:
                errors.append(
                    f"percent {percent} < current {current} — ramp only "
                    f"moves upward; use action=reduce to shrink the rollout"
                )
            if action == "reduce" and percent > current:
                errors.append(
                    f"percent {percent} > current {current} — reduce only "
                    f"moves downward; use action=ramp to widen the rollout"
                )
        if version:
            warnings.append("percent-only actions ignore --version")
        if cohort:
            warnings.append("percent-only actions ignore --cohort")
        result = dict(cur)
        if percent is not None and not errors:
            result["percent"] = int(percent)
            result["updated_at"] = _now()

    elif action in ("pause", "resume"):
        if percent is not None:
            warnings.append(f"{action} ignores --percent")
        if version:
            warnings.append(f"{action} ignores --version")
        if cohort:
            warnings.append(f"{action} ignores --cohort")
        want_paused = action == "pause"
        if exists and bool(cur["paused"]) == want_paused:
            warnings.append(f"already {'paused' if want_paused else 'running'}")
        if not exists and not want_paused:
            warnings.append(
                f"no {ROLLOUT_FILENAME} — nothing is paused; writing an "
                "open record anyway"
            )
        result = dict(cur)
        result["paused"] = want_paused
        if not exists:
            # pause with no prior record must still gate every version:
            # version='' + paused=true means "hold everything".
            result["version"] = ""
        result["updated_at"] = _now()

    else:
        errors.append(f"unknown action: {action!r}")

    if manual_exclude and action not in ("promote", "rollback"):
        warnings.append(
            "exclude is ignored for this action (feeds are not regenerated)"
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "resolved": resolved,
        "result_rollout": result,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Storage (real bucket via AppcastGenerator; faked in tests)
# ---------------------------------------------------------------------------

class BucketStore:
    """get/put/list over the OTA bucket, keys relative to the env prefix."""

    def __init__(self, generator: AppcastGenerator):
        self.gen = generator
        self.backend = generator.storage_backend

    @property
    def prefix(self) -> str:
        bp = self.gen.base_path
        p = self.gen.prefix
        return f"{bp}/{p}" if bp else p

    def _key(self, rel: str) -> str:
        return f"{self.prefix}/{rel}"

    def get(self, rel: str) -> Optional[bytes]:
        key = self._key(rel)
        try:
            if self.backend == "cos":
                resp = self.gen.cos.get_object(Bucket=self.gen.bucket, Key=key)
            else:
                resp = self.gen.s3.get_object(Bucket=self.gen.bucket, Key=key)
            return resp["Body"].read()
        except Exception:
            return None

    def put(self, rel: str, body: bytes, content_type: str) -> None:
        key = self._key(rel)
        if self.backend == "cos":
            self.gen.cos.put_object(
                Bucket=self.gen.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        else:
            self.gen.s3.put_object(
                Bucket=self.gen.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                # Rollout must propagate fast — operators use it as a
                # kill switch. Short cache, mirroring appcast's pattern.
                CacheControl="max-age=60",
            )

    def list_release_dirs(self) -> List[str]:
        prefix = self._key("releases/") + "/"
        dirs: List[str] = []
        try:
            if self.backend == "cos":
                resp = self.gen.cos.list_objects(
                    Bucket=self.gen.bucket, Prefix=prefix, Delimiter="/"
                )
                entries = resp.get("CommonPrefixes", [])
            else:
                resp = self.gen.s3.list_objects_v2(
                    Bucket=self.gen.bucket, Prefix=prefix, Delimiter="/"
                )
                entries = resp.get("CommonPrefixes", [])
            for e in entries:
                name = e.get("Prefix", "").rstrip("/").split("/")[-1]
                if not name or name.lower() == "latest":
                    continue
                if self.gen.environment != "simulation" and "-sim" in name:
                    continue
                dirs.append(name)
        except Exception as exc:
            _log(f"[WARN] failed to list releases/: {exc}")
        return dirs

    def release_has_sha256(self, release_dir: str) -> bool:
        prefix = self._key(f"releases/{release_dir}/")
        try:
            if self.backend == "cos":
                resp = self.gen.cos.list_objects(
                    Bucket=self.gen.bucket, Prefix=prefix
                )
                keys = [o.get("Key", "") for o in resp.get("Contents", [])]
            else:
                resp = self.gen.s3.list_objects_v2(
                    Bucket=self.gen.bucket, Prefix=prefix
                )
                keys = [o.get("Key", "") for o in resp.get("Contents", [])]
            return any(k.endswith(".sha256") for k in keys)
        except Exception as exc:
            _log(f"[WARN] sha256 probe failed for {release_dir}: {exc}")
            return False

    parse_version = property(lambda self: self.gen.parse_version)


def build_store(app: str, env: str, channel: str) -> BucketStore:
    gen = AppcastGenerator(environment=env, channel=channel, app_id=app)
    return BucketStore(gen)


# ---------------------------------------------------------------------------
# Status + execute
# ---------------------------------------------------------------------------

def collect_status(store: Any, app: str, env: str, channel: str) -> Dict[str, Any]:
    rollout_key = f"channels/{channel}/{ROLLOUT_FILENAME}"
    raw = store.get(rollout_key)
    rollout_exists = raw is not None
    rollout_raw: Optional[dict] = None
    if raw is not None:
        try:
            parsed = json.loads(raw.decode("utf-8"))
            rollout_raw = parsed if isinstance(parsed, dict) else None
        except Exception as exc:
            _log(f"[WARN] {rollout_key} unreadable ({exc}); treating as open")
    rollout = normalize_rollout(rollout_raw)

    published: Optional[str] = None
    latest_raw = store.get("latest.json")
    if latest_raw is not None:
        try:
            latest = json.loads(latest_raw.decode("utf-8"))
            if isinstance(latest, dict):
                v = str(latest.get("version") or "").strip()
                published = normalize_version(v) or None
        except Exception:
            published = None

    dirs = store.list_release_dirs()
    universal = [d for d in dirs if _split_release_dir(d)[0] is None]
    try:
        universal.sort(key=store.parse_version, reverse=True)
    except Exception:
        universal.sort(reverse=True)
    available = [
        {"version": _split_release_dir(d)[1], "dir": d} for d in universal
    ]

    return {
        "app": app,
        "env": env,
        "channel": channel,
        "env_prefix": store.prefix,
        "rollout_key": rollout_key,
        "rollout": rollout,
        "rollout_exists": rollout_exists,
        "published_version": published,
        "available": available,
    }


def execute(
    store: Any,
    app: str,
    env: str,
    channel: str,
    action: Optional[str] = None,
    percent: Optional[int] = None,
    version: Optional[str] = None,
    cohort: Optional[str] = None,
    apply: bool = False,
    exclude: Optional[str] = None,
) -> Dict[str, Any]:
    status = collect_status(store, app, env, channel)
    if not action:
        return status

    pl = plan(
        action, percent, version, cohort, status, store=store, exclude=exclude
    )
    result: Dict[str, Any] = dict(status)
    result["requested"] = {
        "action": action,
        "percent": percent,
        "version": version,
        "cohort": normalize_cohort(cohort),
        "exclude": normalize_exclude(exclude),
    }
    result["resolved"] = pl["resolved"]
    result["guard_errors"] = pl["errors"]
    result["guard_warnings"] = pl["warnings"]
    result["written"] = False
    result["result_rollout"] = pl["result_rollout"]

    if pl["errors"]:
        return result

    if apply:
        body = json.dumps(
            pl["result_rollout"], indent=2, ensure_ascii=False
        ).encode("utf-8")
        store.put(status["rollout_key"], body, "application/json; charset=utf-8")
        result["written"] = True
        _log(
            f"[OK] wrote {status['rollout_key']}: "
            f"version={pl['result_rollout'].get('version')!r} "
            f"percent={pl['result_rollout'].get('percent')} "
            f"paused={pl['result_rollout'].get('paused')} "
            f"cohort={pl['result_rollout'].get('cohort_include_prefix')}"
        )
    else:
        _log(
            f"[DRY-RUN] would write {status['rollout_key']} "
            f"-> {json.dumps(pl['result_rollout'], ensure_ascii=False)}"
        )
    return result


def write_summary(path: str, result: Dict[str, Any]) -> None:
    """Append a markdown section describing status/plan to ``path``."""
    try:
        rollout = result.get("rollout", {})
        resolved = result.get("resolved") or {}
        requested = result.get("requested") or {}
        lines = [
            f"## OTA rollout — `{result.get('app')}` / `{result.get('env')}` / `{result.get('channel')}`",
            "",
            "| Field | Value |",
            "|---|---|",
        ]
        if requested:
            lines.append(f"| Action | `{requested.get('action')}` |")
        lines += [
            f"| Current rollout | "
            f"version=`{rollout.get('version') or '—'}` · "
            f"percent=`{rollout.get('percent')}` · "
            f"paused=`{rollout.get('paused')}` · "
            f"cohort=`{','.join(rollout.get('cohort_include_prefix') or []) or '—'}` |",
            f"| Rollout record exists | {'yes' if result.get('rollout_exists') else 'no (default = fully open)'} |",
            f"| Published (latest.json) | `{result.get('published_version') or '—'}` |",
        ]
        if resolved:
            lines += [
                f"| Target version | `{resolved.get('target_version') or '—'}` |",
                f"| Publish appcast/latest.json | {'yes' if resolved.get('publish') else 'no'} |",
            ]
            if resolved.get("exclude"):
                lines.append(f"| Feed exclusions | `{resolved['exclude']}` |")
        avail = result.get("available") or []
        if avail:
            shown = ", ".join(a["version"] for a in avail[:8])
            more = "" if len(avail) <= 8 else f" (+{len(avail) - 8} more)"
            lines.append(f"| Available releases | {shown}{more} |")
        errors = result.get("guard_errors") or []
        warnings = result.get("guard_warnings") or []
        if errors:
            lines.append("| Guard | ❌ **blocked** |")
        elif warnings:
            lines.append(f"| Guard | ⚠️ {'; '.join(warnings)} |")
        else:
            lines.append("| Guard | ✅ OK |")
        if "written" in result:
            lines.append(f"| Rollout written | {'yes' if result.get('written') else 'no (dry-run or blocked)'} |")
        if errors:
            lines += ["", "**Guard errors:**"] + [f"- {e}" for e in errors]
        lines.append("")
        p = Path(path)
        with p.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as exc:  # summary must never fail the run
        _log(f"[WARN] failed to write summary: {exc}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read/validate/write the OTA rollout control file"
    )
    parser.add_argument("--app", choices=["intl", "cn"], default="intl")
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "development", "test", "staging", "production", "simulation"],
    )
    parser.add_argument(
        "--channel",
        choices=["dev", "beta", "stable", "lts", "simulation"],
        default="stable",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="print current status only (no guard, no write)",
    )
    parser.add_argument("--action", choices=list(ACTIONS))
    parser.add_argument("--percent", type=int, default=None)
    parser.add_argument("--version", default=None)
    parser.add_argument("--cohort", default=None)
    parser.add_argument(
        "--exclude",
        default=None,
        help=(
            "Comma-separated versions to drop from the feeds when "
            "regenerating (promote/rollback). For rollback the bad "
            "version is also derived automatically from latest.json + "
            "the current rollout; this list is merged in."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write rollout.json after the guard passes",
    )
    parser.add_argument("--summary", default=None, help="append markdown to this path")
    args = parser.parse_args(argv)

    if not args.status and not args.action:
        parser.error("either --status or --action is required")

    if args.percent is not None and not (0 <= args.percent <= 100):
        parser.error("--percent must be between 0 and 100")

    # build_store may sys.exit(1) itself (missing credentials / config) —
    # SystemExit propagates and becomes the process exit code.
    store = build_store(args.app, args.env, args.channel)

    result = execute(
        store,
        app=args.app,
        env=args.env,
        channel=args.channel,
        action=None if args.status else args.action,
        percent=args.percent,
        version=args.version,
        cohort=args.cohort,
        apply=args.apply and not args.status,
        exclude=args.exclude,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.summary:
        write_summary(args.summary, result)

    errors = result.get("guard_errors")
    if errors:
        for e in errors:
            _log(f"[GUARD] {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
