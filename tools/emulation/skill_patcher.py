"""
Skill-config patcher for the flood-test harness (2026-06-02).

The Feige front-desk skill's detection knobs live inside the skill's diagram
JSON (and its ``_bundle`` twin):

  * ``domCheckIntervalMs`` — the EventMonitor DOM poll cadence (e.g. 250 vs 750)
  * ``cdpFilterExpr``      — a JSON-as-string blob with ``roots`` /
                            ``item_selector`` / ``fields`` selectors used for
                            new-message detection.

The round-controller patches these per round so we can bisect e.g. the
250→750 interval question directly. The keys can sit at any depth in the
diagram graph, so we recurse and patch every dict that carries them.

Always ``backup`` before the first patch and ``restore`` after the run so the
operator's real skill files are left untouched. Backups live in
``<diagram_dir>/.harness_bak/``. ``old*.json`` files are skipped (they're
retired copies the loader ignores).

CLI:
  python skill_patcher.py backup  <skill_dir>
  python skill_patcher.py restore <skill_dir>
  python skill_patcher.py patch   <skill_dir> --interval 250 \
        --cdp-root ".list_items" \
        --cdp-item "[data-qa-id='qa-conversation-chat-item']" \
        --cdp-field customer_name="[class*='NameContent']" \
        --cdp-field last_message="[class*='msgContent']"

<skill_dir> may be the skill folder (containing diagram_dir/) or the
diagram_dir itself.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

BAK_DIRNAME = ".harness_bak"


def _diagram_dir(skill_dir: Path) -> Path:
    skill_dir = Path(skill_dir)
    if (skill_dir / "diagram_dir").is_dir():
        return skill_dir / "diagram_dir"
    if skill_dir.name == "diagram_dir":
        return skill_dir
    return skill_dir  # treat as already-pointing-at-the-json dir


def _target_jsons(ddir: Path):
    """Diagram JSONs to patch: every *.json except backups and old* copies."""
    out = []
    for p in sorted(ddir.glob("*.json")):
        if p.parent.name == BAK_DIRNAME:
            continue
        if p.name.startswith("old"):
            continue
        out.append(p)
    return out


def backup(skill_dir):
    ddir = _diagram_dir(skill_dir)
    bak = ddir / BAK_DIRNAME
    bak.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in _target_jsons(ddir):
        dest = bak / p.name
        if not dest.exists():  # don't clobber an existing pristine backup
            shutil.copy2(p, dest)
        n += 1
    print(f"[skill_patcher] backed up {n} file(s) into {bak}")
    return n


def restore(skill_dir):
    ddir = _diagram_dir(skill_dir)
    bak = ddir / BAK_DIRNAME
    if not bak.is_dir():
        print(f"[skill_patcher] no backup dir at {bak} — nothing to restore")
        return 0
    n = 0
    for p in sorted(bak.glob("*.json")):
        shutil.copy2(p, ddir / p.name)
        n += 1
    print(f"[skill_patcher] restored {n} file(s) from {bak}")
    return n


def _walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _patch_cdp_expr(expr_str, roots=None, item_selector=None, fields=None):
    """Parse the cdpFilterExpr JSON-string, apply overrides, re-serialise."""
    try:
        expr = json.loads(expr_str)
    except Exception:
        return expr_str, False  # leave untouched if unparseable
    changed = False
    if roots is not None:
        expr["roots"] = [roots] if isinstance(roots, str) else list(roots)
        changed = True
    if item_selector is not None:
        expr["item_selector"] = item_selector
        changed = True
    if fields:
        expr.setdefault("fields", {})
        for fname, sel in fields.items():
            slot = expr["fields"].setdefault(fname, {})
            slot["selector"] = sel
        changed = True
    if not changed:
        return expr_str, False
    return json.dumps(expr, ensure_ascii=False, indent=2), True


def patch(skill_dir, interval=None, cdp_roots=None, cdp_item=None, cdp_fields=None):
    ddir = _diagram_dir(skill_dir)
    touched_files = 0
    hits = {"interval": 0, "cdp": 0}
    for p in _target_jsons(ddir):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[skill_patcher] skip {p.name}: {exc}")
            continue
        file_changed = False
        for d in _walk_dicts(data):
            if interval is not None and "domCheckIntervalMs" in d:
                if d["domCheckIntervalMs"] != interval:
                    d["domCheckIntervalMs"] = interval
                    file_changed = True
                hits["interval"] += 1
            if "cdpFilterExpr" in d and (cdp_roots or cdp_item or cdp_fields):
                new_expr, ch = _patch_cdp_expr(
                    d["cdpFilterExpr"], cdp_roots, cdp_item, cdp_fields
                )
                if ch:
                    d["cdpFilterExpr"] = new_expr
                    file_changed = True
                    hits["cdp"] += 1
        if file_changed:
            p.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            touched_files += 1
    print(f"[skill_patcher] patched {touched_files} file(s) "
          f"(interval sites={hits['interval']}, cdp sites={hits['cdp']}) in {ddir}")
    return touched_files


def _parse_field(kv):
    if "=" not in kv:
        raise argparse.ArgumentTypeError("expected name=selector")
    name, sel = kv.split("=", 1)
    return name.strip(), sel


def main():
    ap = argparse.ArgumentParser(description="Patch Feige skill detection knobs for flood tests.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("backup", "restore"):
        sp = sub.add_parser(name)
        sp.add_argument("skill_dir")

    pp = sub.add_parser("patch")
    pp.add_argument("skill_dir")
    pp.add_argument("--interval", type=int, default=None,
                    help="domCheckIntervalMs value, e.g. 250 or 750")
    pp.add_argument("--cdp-root", default=None, help="cdpFilterExpr roots[0] selector")
    pp.add_argument("--cdp-item", default=None, help="cdpFilterExpr item_selector")
    pp.add_argument("--cdp-field", action="append", default=[], type=_parse_field,
                    metavar="name=selector",
                    help="override a field selector (repeatable)")

    args = ap.parse_args()
    if args.cmd == "backup":
        backup(args.skill_dir)
    elif args.cmd == "restore":
        restore(args.skill_dir)
    elif args.cmd == "patch":
        fields = dict(args.cdp_field) if args.cdp_field else None
        patch(args.skill_dir, interval=args.interval,
              cdp_roots=args.cdp_root, cdp_item=args.cdp_item, cdp_fields=fields)


if __name__ == "__main__":
    sys.exit(main())
