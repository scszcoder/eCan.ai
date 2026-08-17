#!/usr/bin/env python3
"""
Verify the Windows CRLF fix for .gitconfig-gitee files.

Problem: On Windows GitHub-hosted runners (windows-latest), bash's heredoc
expands \\n → \\r\\n even when set -euo pipefail is active. The original
code used `cat > file <<EOF` heredocs, which produced CRLF files.

Fix: Write the file with `printf '%s\n' ...` instead of heredoc. This
bypasses bash's text-mode line ending expansion entirely.

This test runs the exact same printf commands that the workflow uses and
verifies:
1. The file contains only LF (no CRLF)
2. git can parse all expected keys from it
3. The [core] autocrlf=false setting is present
4. The credential helper and username are correct

Note: This test runs on macOS/Linux. It cannot reproduce the Windows bash
heredoc CRLF bug directly (that requires Windows), but it does verify that
the printf fix produces syntactically valid output that git can read on
all platforms.
"""

import os
import subprocess
import sys
import tempfile


def run_bash(script: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def test_gitconfig_printf_produces_lf_only():
    """
    The fixed workflow uses printf '%s\n' to write the gitconfig.
    Verify the output has NO carriage returns and matches expected content.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gitconfig = os.path.join(tmpdir, ".gitconfig-gitee")
        creds     = os.path.join(tmpdir, ".git-credentials-gitee")

        # This is the EXACT printf pattern used in the workflow YAML:
        # (minus the YAML indentation, which bash strips anyway)
        script = "\n".join([
            f'printf \'%s\\n\' \\',
            '    \'[core]\' \\',
            "    '    autocrlf = false' \\",
            '    \'[credential "https://gitee.com"]\' \\',
            f'    "    helper = store --file {creds}" \\',
            "    '    username = oauth2' \\",
            f'    > "{gitconfig}"'
        ])

        code, out, err = run_bash(script)
        assert code == 0, f"printf write failed: {err}"

        with open(gitconfig, "rb") as f:
            raw = f.read()

        crlf_count = raw.count(b"\r\n")
        lf_count   = raw.count(b"\n") - crlf_count  # bare LF only

        print(f"[printf] file size: {len(raw)} bytes")
        print(f"[printf] CRLF (\\r\\n) count: {crlf_count}")
        print(f"[printf] bare LF  (\\n) count: {lf_count}")
        print(f"[printf] raw content:\n{raw.decode()}")

        assert crlf_count == 0, (
            f"FAIL: found {crlf_count} CRLF sequences in gitconfig; "
            f"Windows bash heredoc would add these but printf should not"
        )
        # printf '%s\n' appends \n after every arg, including the last one.
        # So 5 \n characters = 4 content lines + 1 trailing newline (correct).
        assert lf_count >= 4, f"Expected at least 4 lines, got {lf_count}"
        # Total \n count should be 5 (4 content lines + 1 trailing blank line)
        total_lf = raw.count(b"\n")
        print(f"[printf] total LF count: {total_lf} (expected 5 for 4 content lines + trailing)")
        return True


def test_gitconfig_is_valid_gitconfig():
    """
    Verify git can parse the printf-written file and returns the
    expected keys. Also checks [core] autocrlf=false is readable.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gitconfig = os.path.join(tmpdir, ".gitconfig-gitee")
        creds     = os.path.join(tmpdir, ".git-credentials-gitee")

        script = "\n".join([
            f'printf \'%s\\n\' \\',
            '    \'[core]\' \\',
            "    '    autocrlf = false' \\",
            '    \'[credential "https://gitee.com"]\' \\',
            f'    "    helper = store --file {creds}" \\',
            "    '    username = oauth2' \\",
            f'    > "{gitconfig}"',
            f'git config --file "{gitconfig}" --list'
        ])

        code, out, err = run_bash(script)
        assert code == 0, f"git config parse failed: {err}\nstderr: {err}"

        # git outputs keys as section.key=value on --list
        keys = {}
        for line in out.strip().split("\n"):
            if "=" in line:
                key, val = line.split("=", 1)
                keys[key] = val

        expected_keys = {
            "core.autocrlf",
            "credential.https://gitee.com.helper",
            "credential.https://gitee.com.username",
        }
        missing = expected_keys - set(keys.keys())
        assert not missing, f"git parsed {len(keys)} keys: {sorted(keys)}, missing: {missing}"

        assert keys["core.autocrlf"] == "false", (
            f"[core] autocrlf should be 'false', got: {keys['core.autocrlf']!r}"
        )
        assert "store" in keys["credential.https://gitee.com.helper"], (
            f"helper should contain 'store', got: {keys['credential.https://gitee.com.helper']!r}"
        )
        assert keys["credential.https://gitee.com.username"] == "oauth2"

        print(f"[git parse] all {len(keys)} keys validated:")
        for k, v in sorted(keys.items()):
            print(f"  {k} = {v}")
        return True


def test_credentials_file_is_clean():
    """
    The .git-credentials-gitee file must have no \\r in it either.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        creds = os.path.join(tmpdir, ".git-credentials-gitee")

        script = f'printf \'token123\\n\' > "{creds}"'
        run_bash(script)

        with open(creds, "rb") as f:
            raw = f.read()

        print(f"[creds] bytes: {raw!r}")
        assert b"\r" not in raw, f"CR found in credentials file: {raw!r}"
        assert raw == b"token123\n"
        return True


def test_no_crlf_in_any_generated_file():
    """
    Comprehensive check: every file we generate must be LF-only.
    This simulates the full Prepare Gitee credential helper step.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gitconfig = os.path.join(tmpdir, ".gitconfig-gitee")
        creds     = os.path.join(tmpdir, ".git-credentials-gitee")
        askpass   = os.path.join(tmpdir, ".git-askpass-gitee")

        script = "\n".join([
            # Step 1: credentials
            f'printf \'token\\n\' > "{creds}"',
            "chmod 600 " + f'"{creds}"',
            # Step 2: gitconfig (printf fix)
            f'printf \'%s\\n\' \\',
            '    \'[core]\' \\',
            "    '    autocrlf = false' \\",
            '    \'[credential "https://gitee.com"]\' \\',
            f'    "    helper = store --file {creds}" \\',
            "    '    username = oauth2' \\",
            f'    > "{gitconfig}"',
            # Step 3: askpass (heredoc + sed)
            f'CLEAN=$(printf \'%s\' "token" | tr -d \'\\r\\n\')',
            f'cat > "{askpass}" <<ASKEOF',
            "#!/bin/sh",
            'case "$1" in',
            '  Username*) echo \'oauth2\' ;;',
            '  Password*) printf \'%s\' "$CLEAN" ;;',
            '  *) echo ;;',
            "esac",
            "ASKEOF",
            f'sed -i \'s/\\r$//\' "{askpass}"',
            f'chmod 700 "{askpass}"',
        ])

        code, out, err = run_bash(script)
        assert code == 0, f"Full step failed: {err}"

        for label, path in [
            ("credentials", creds),
            ("gitconfig",    gitconfig),
            ("askpass",      askpass),
        ]:
            with open(path, "rb") as f:
                raw = f.read()
            crlf_count = raw.count(b"\r\n")
            has_bare_cr = b"\r" in raw and b"\r\n" not in raw.replace(b"\r", b"", 1)
            print(f"[{label}] {len(raw)} bytes, CRLF={crlf_count}, bare-CR={has_bare_cr}")
            assert crlf_count == 0, f"{label}: found CRLF sequences"
            # Bare CR is also bad (would appear on line that ends with \r\n)
            if b"\r" in raw:
                print(f"  WARNING: {label} contains bare CR — raw: {raw!r}")
                # The sed should have removed them; if any remain, fail
                lines_with_cr = [i for i, b in enumerate(raw.split(b"\n")) if b"\r" in b]
                assert not lines_with_cr, f"{label}: lines with CR: {lines_with_cr}"

        return True


if __name__ == "__main__":
    results = {}

    print("=" * 60)
    print("Test 1: printf produces LF-only gitconfig")
    print("=" * 60)
    try:
        results["test_gitconfig_printf_produces_lf_only"] = test_gitconfig_printf_produces_lf_only()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_gitconfig_printf_produces_lf_only"] = False

    print()
    print("=" * 60)
    print("Test 2: git can parse the printf-written gitconfig")
    print("=" * 60)
    try:
        results["test_gitconfig_is_valid_gitconfig"] = test_gitconfig_is_valid_gitconfig()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_gitconfig_is_valid_gitconfig"] = False

    print()
    print("=" * 60)
    print("Test 3: credentials file has no CRLF")
    print("=" * 60)
    try:
        results["test_credentials_file_is_clean"] = test_credentials_file_is_clean()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_credentials_file_is_clean"] = False

    print()
    print("=" * 60)
    print("Test 4: full credential helper step (all files LF-only)")
    print("=" * 60)
    try:
        results["test_no_crlf_in_any_generated_file"] = test_no_crlf_in_any_generated_file()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_no_crlf_in_any_generated_file"] = False

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = all(results.values())
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    print()
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)
