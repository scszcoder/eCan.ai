#!/usr/bin/env python3
"""
Compare release-intl.yml vs release-cn.yml structurally: collapse every
backend-specific *value* into a placeholder and assert the remaining
*structure* is byte-equal.

This is the source of truth for "intl/cn are the same shape".

Backend markers we collapse (a-priori known to be runtime-distinguishing):
  - `ECAN_APP_ID: intl|cn`                       → `ECAN_APP_ID: <APP>`
  - `ECAN_APP_NAME: eCan|eCan.cn`               → `ECAN_APP_NAME: <NAME>`
  - `DIST_APP: eCan|eCan.cn`                    → `DIST_APP: <NAME>`
  - `requirements-intl.txt|requirements-cn.txt`  → `requirements-<APP>.txt`
  - `--app intl|cn`                              → `--app <APP>`
  - AWS_* / ECAN_TENCENT_* / COS_BUCKET secrets   → `APP_<KEY>: ...`
  - Region defaults                              → `<REGION>`
  - artifact names `eCan-windows-amd64-*`       → `<NAME>-<PLATFORM>-*`
  - dist paths `dist\eCan-*` vs `dist\eCan.cn-*` → same canonical form
  - Job IDs `build-windows` vs `build-windows-cn` → `<JID>`
  - Job display names (`Build Windows amd64 CN`) → without ` CN`
  - Workflow name / concurrency group identifier  → `<KEY>`
  - `app: intl|cn` input                        → `app: <APP>`
  - Header comment block (lines 1–20)           → collapsed

After collapse the two files MUST be byte-equal.
"""
import difflib
import os
import re
import sys
from pathlib import Path

REPO = Path(os.environ.get("REPO_ROOT", Path.cwd()))


def normalize(text: str) -> str:
    out = text

    # ── Step 1: static env / runtime values. ───────────────────────────────
    out = re.sub(r"^\s*ECAN_APP_ID:\s*\S+\s*$",
                  "ECAN_APP_ID: <APP>", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*ECAN_APP_NAME:\s*\S+\s*$",
                  "ECAN_APP_NAME: <NAME>", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*DIST_APP:\s*\S+\s*$",
                  "DIST_APP: <NAME>", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*app:\s+(?:intl|cn)\s*$",
                  "app: <APP>", out, flags=re.MULTILINE | re.IGNORECASE)

    out = out.replace("requirements-intl.txt", "requirements-<APP>.txt")
    out = out.replace("requirements-cn.txt",   "requirements-<APP>.txt")
    out = re.sub(r"--app\s+(intl|cn)\b", "--app <APP>", out, flags=re.IGNORECASE)

    # ── Step 2: secrets (collapse to APP_{KEY_ID,KEY_SECRET,REGION,BUCKET})
    for old, new in (
        ("AWS_ACCESS_KEY_ID",          "APP_KEY_ID"),
        ("AWS_SECRET_ACCESS_KEY",      "APP_KEY_SECRET"),
        ("AWS_REGION",                 "APP_REGION"),
        ("ECAN_TENCENT_SECRET_ID",     "APP_KEY_ID"),
        ("ECAN_TENCENT_SECRET_KEY",    "APP_KEY_SECRET"),
        ("ECAN_TENCENT_REGION",        "APP_REGION"),
        ("COS_BUCKET",                 "APP_BUCKET"),
    ):
        out = out.replace(old, new)

    # ── Step 3: region defaults (string literals).
    out = out.replace("'us-east-1'",   "'<REGION>'")
    out = out.replace("'ap-guangzhou'", "'<REGION>'")

    # ── Step 4: dist filenames and artifact names.
    # `dist\eCan-${{...}}-windows-amd64.exe` ↔ `dist\eCan.cn-${{...}}-...`
    out = re.sub(r"dist\\eCan\.cn-", r'dist\\<NAME>-', out)
    out = re.sub(r"dist\\eCan-",     r'dist\\<NAME>-', out)
    out = re.sub(r'"dist\\eCan\.cn-', r'"dist\\<NAME>-', out)
    out = re.sub(r'"dist\\eCan-',     r'"dist\\<NAME>-', out)
    # Strip the `<NAME>-` prefix inside Test-Path quotes so the intl/cn
    # collapsing yields the same `dist\<NAME>-...` form on both sides.
    out = re.sub(r'"dist\\<NAME>-(\$\{\{)', r'"\1', out)

    # Linux: `dist/eCan-...deb` ↔ `dist/eCan.cn-...deb` (no backslash in YAML).
    out = re.sub(r'dist/eCan\.cn-', r'dist/<NAME>-', out)
    out = re.sub(r'dist/eCan-',     r'dist/<NAME>-', out)
    out = re.sub(r'eCan\.cn-',     r'<NAME>-', out)
    out = re.sub(r'eCan-',         r'<NAME>-', out)

    # Per-job artifact names: `eCan-windows-amd64-*` (and `.cn` forms) → neutral.
    out = re.sub(r'"eCan\.cn-',  r'"<NAME>-', out)
    out = re.sub(r'"eCan-',      r'"<NAME>-', out)

    # The CN pipeline pulls source from the Gitee mirror while INTL
    # pulls from GitHub. Both sides must collapse to the same
    # canonical form so the symmetry check doesn't false-fail on the
    # backend-specific source repository.
    #
    # INTL has no `repository:`/`token:` lines (defaults to GitHub
    # via the implicit `github.repository` context). CN has them
    # pointing at the Gitee mirror. Strip BOTH sides to a single
    # canonical `<REPOSITORY>` placeholder so the two workflows
    # collapse to the same form.
    out = re.sub(r"^(\s*)repository:\s*\S+\s*\n",
                  "", out, flags=re.MULTILINE)
    # `actions/checkout@v6` defaults to github.com. The CN workflow
    # overrides it with `github-server-url: https://gitee.com` so the
    # fetch URL lands on the Gitee mirror rather than a GitHub 404.
    # INTL has no such override. Strip the line on whichever side
    # has it so the two canonical forms collapse identically.
    out = re.sub(r"^(\s*)github-server-url:\s*\S+\s*\n",
                  "", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*)token:\s*\$\{\{\s*secrets\.\S+\s*\}\}\s*\n",
                  "", out, flags=re.MULTILINE)
    # Step name in CN reads "Checkout from Gitee mirror" because the
    # source is non-default. Collapse to the INTL form so the symmetry
    # check doesn't trip on the cosmetic difference.
    out = re.sub(r'name: Checkout from Gitee mirror',
                  'name: Checkout', out)

    # The windows-build pwsh Test-Path has `dist\eCan-${version}-...`
    # (intl) ↔ `dist\eCan.cn-${version}-...` (cn). Strip the `dist\<NAME>-`
    # or `<NAME>-` prefix inside quoted `${{…}}` Test-Path arguments so the
    # two pipelines collapse to the same canonical form.
    out = re.sub(r'"dist\\<NAME>-(\$\{\{)', r'"\1', out)
    out = re.sub(r'"\s*<NAME>-(\$\{\{)',  r'"\1', out)

    # ── Step 5: job IDs. Order matters: do `-cn` FIRST so bare regex
    # doesn't eat the suffix.
    for jid in ("build-windows-cn",          "build-macos-amd64-cn",
                "build-macos-aarch64-cn",    "build-linux-cn",
                "build-windows",             "build-macos-amd64",
                "build-macos-aarch64",       "build-linux",
                "upload-to-s3",              "upload-to-cos"):
        # Match `jid` only as a whole token: next char is end-of-line, `:`,
        # space, `]`, `,`, etc. — NOT a `-` followed by more alnum.
        pattern = re.escape(jid) + r"(?![-A-Za-z0-9_])"
        out = re.sub(pattern, "<JID>", out)

    # ── Step 6: workflow display name + concurrency group.
    out = re.sub(r"^name: Release \((?:Intl|CN|intl|cn)\)\s*$",
                  "name: Release (<KEY>)", out, flags=re.MULTILINE)
    out = re.sub(
        r"^(  group:\s*)release-(?:intl|cn)-",
        r"\1release-<KEY>-",
        out, flags=re.MULTILINE,
    )

    # ── Step 7: header comment block (intentional human text).
    # Collapse every comment line to `#` so both files produce the same.
    out = re.sub(r"^#.*$", "#", out, flags=re.MULTILINE)

    # ── Step 8: stage banner with `Intl` / `CN` literal.
    out = re.sub(
        r"^# Stage \d+ — Build matrix \((?:Intl|CN)\):.*$",
        "# Stage 2 — Build matrix (X):",
        out, flags=re.MULTILINE,
    )

    # ── Step 9: per-job display name differences.
    out = re.sub(r"^(\s*name:\s+)Build Windows amd64 CN\s*$",
                  r"\1Build Windows amd64", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*name:\s+)Build macOS amd64 CN\s*$",
                  r"\1Build macOS amd64", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*name:\s+)Build macOS aarch64 CN\s*$",
                  r"\1Build macOS aarch64", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*name:\s+)Build Linux amd64 CN\s*$",
                  r"\1Build Linux amd64", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*name:\s+)Upload to S3\s*$",
                  r"\1Upload to <BACKEND>", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*name:\s+)Upload to COS\s*$",
                  r"\1Upload to <BACKEND>", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s*name:\s+)Generate Appcast \(all platforms × archs\) CN\s*$",
                  r"\1Generate Appcast (all platforms × archs)",
                  out, flags=re.MULTILINE)

    # Final collapse so `<KEY>` is the universal name (avoid mixing <APP>
    # vs <KEY> tokens).
    out = out.replace("<KEY>", "<APP>")

    # `uses: ./.github/workflows/shared-(s3|cos)-*.yml` (canonical form)
    # OR `shared-{appcast,download,…}-generation.yml` (intl legacy form).
    out = re.sub(r"shared-(?:s3|cos)-",
                  "shared-<BACKEND>-", out)
    out = re.sub(r"shared-appcast-generation\.yml",
                  "shared-<BACKEND>-appcast-generation.yml", out)
    out = re.sub(r"shared-download-links\.yml",
                  "shared-<BACKEND>-download-links.yml", out)
    out = re.sub(r"shared-latest-json\.yml",
                  "shared-<BACKEND>-latest-json.yml", out)
    # Final status block — normalize backend mentions in `echo` lines.
    out = re.sub(
        r"^(\s*)echo \"================ Release \((?:Intl|CN)\) Summary ================\"$",
        r'\1echo "================ Release (<APP>) Summary ================"',
        out, flags=re.MULTILINE,
    )
    out = re.sub(r"echo \"  S3 upload:",
                  'echo "  <BACKEND> upload:', out)
    out = re.sub(r"echo \"  COS upload:",
                  'echo "  <BACKEND> upload:', out)

    out = re.sub(r"until S3 upload is fixed", "until <BACKEND> upload is fixed", out)
    out = re.sub(r"until COS upload is fixed", "until <BACKEND> upload is fixed", out)
    # Comment inside the new fallback job's `if:` block — strip the
    # backend noun so symmetry isn't broken by the literal.
    out = re.sub(r"# Only run when S3 upload did not actually succeed",
                  "# Only run when <BACKEND> upload did not actually succeed", out)
    out = re.sub(r"# Only run when COS upload did not actually succeed",
                  "# Only run when <BACKEND> upload did not actually succeed", out)
    # Fallback-downloads job title also mentions S3 / COS — collapse
    # the noun so the symmetry check doesn't trip on it.
    out = re.sub(r"S3 upload failed",
                  "<BACKEND> upload failed", out)
    out = re.sub(r"COS upload failed",
                  "<BACKEND> upload failed", out)
    # Fallback-downloads job text mentions the backend by name
    # (Tencent Cloud COS / AWS S3). Normalise the backend noun so the
    # symmetry check doesn't false-fail on those literals.
    out = re.sub(r"<BACKEND> upload failed",
                  "GHA fallback download (upload failed)", out)
    out = re.sub(r"The AWS S3 upload step failed",
                  "The CDN upload step failed", out)
    out = re.sub(r"The Tencent Cloud COS upload step failed",
                  "The CDN upload step failed", out)
    out = re.sub(r"for INTL internal use only",
                  "for <APP> internal use only", out)
    out = re.sub(r"for CN internal use only",
                  "for <APP> internal use only", out)

    # The cn's `app: intl/cn` line is missing in some places where the
    # intl version has it. We already collapsed `app: intl|cn` to
    # `app: <APP>`; if either side has the line and the other doesn't,
    # delete the line so they match.
    # (Implementation: count occurrences of `app: <APP>` per "with:"
    # block — but the simpler fix is: append a sentinel on both sides.)

    # ── Step 10: cosmetic whitespace alignment. ────────────────────────────
    # Inside `with:` blocks, lines like `windows-build-result: ${...}` are
    # YAML-in-yaml in literal blocks but GitHub Actions parses them as
    # plain strings, so alignment is purely cosmetic. Collapse any
    # run of ≥1 spaces between `: ` to exactly 1 space; that way any
    # column-alignment drift won't show up in the symmetry diff.
    out = re.sub(r":\s+(\${{)", r": \1", out)
    # `:` followed by literal text — collapse multi-space to single.
    out = re.sub(r":\s\s+", ": ", out)

    # ── Step 11: collapse runs of `=` to a single canonical length.
    out = re.sub(r"={3,}", "==========", out)

    # ── Step 12: blank/`#` comment-line deduplication at the top.
    out = re.sub(r"^#\s*$", "#", out, flags=re.MULTILINE)
    # Squash runs of `#` lines to a single `#` line — the count of header
    # comment lines legitimately differs between intl/cn (cn has the same
    # info written in fewer sentences). After squashing, both files
    # should look identical in the header.
    out = re.sub(r"(?:^#\n)+", "#\n", out, flags=re.MULTILINE)

    return out


def main() -> int:
    # Resolve the workflow paths explicitly so a FileNotFoundError
    # surfaces as a clear "wrong REPO_ROOT" message rather than a bare
    # Python traceback at exit code 1 (which is what the CI gate
    # expects on failure, but the traceback makes the failure mode
    # confusing).
    intl_path = REPO / ".github/workflows/release-intl.yml"
    cn_path = REPO / ".github/workflows/release-cn.yml"
    try:
        intl = intl_path.read_text()
        cn = cn_path.read_text()
    except FileNotFoundError as e:
        print(
            f"ERROR: cannot locate release workflow files.\n"
            f"  REPO_ROOT = {REPO}\n"
            f"  expected: {intl_path} and {cn_path}\n"
            f"  hint: set REPO_ROOT=<repo-root> or run from the repo root.\n"
            f"  ({e})",
            file=sys.stderr,
        )
        return 2

    ni = normalize(intl)
    nc = normalize(cn)

    if ni == nc:
        print("OK: release-intl.yml and release-cn.yml are byte-equal after normalization.")
        print(f"  ({len(ni)} chars)")
        return 0

    diff = list(difflib.unified_diff(
        ni.splitlines(keepends=False),
        nc.splitlines(keepends=False),
        fromfile="release-intl.yml (normalized)",
        tofile="release-cn.yml (normalized)",
        lineterm="",
        n=2,
    ))
    diff_count = sum(1 for l in diff if l.startswith("+") or l.startswith("-"))
    print(f"DIFFERS: NOT byte-equal after normalization.")
    print(f"  ({diff_count} diff lines)")
    print()
    print("\n".join(diff[:100]))
    return 1


if __name__ == "__main__":
    sys.exit(main())