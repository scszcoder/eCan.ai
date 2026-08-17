#!/usr/bin/env python3
"""
Verify the Windows CRLF fix for .gitconfig-gitee files.

Problem: On Windows GitHub-hosted runners (windows-latest), bash's file I/O
translates \n → \r\n for ALL writes, regardless of whether you use
heredoc, printf redirect, or tee. The original code tried heredoc + sed
and printf + autocrlf=false — both insufficient on Windows.

Fix: Use `python -c "..."` to write the file. Python's file I/O
bypasses bash's text-mode layer entirely and writes raw bytes.

This test verifies:
1. The python-produced file has NO CRLF
2. git can parse all expected keys from it
3. All other generated files (credentials, askpass) are also clean
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


def test_gitconfig_via_python():
    """
    Verify the python -c approach from the workflow produces LF-only,
    git-readable gitconfig. This is the actual fix for the Windows bug.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gitconfig = os.path.join(tmpdir, ".gitconfig-gitee")
        creds     = os.path.join(tmpdir, ".git-credentials-gitee")

        # The EXACT python command from workflow YAML line 1040-1050
        # (single-quoted outer, double-quoted Python strings)
        bash_cmd = (
            "python -c '\n"
            "import os\n"
            f'cf = os.environ["GITCONFIG_FILE"]\n'
            f'cr = os.environ["CREDS_FILE"]\n'
            'with open(cf, "w", newline="\\n") as f:\n'
            '    f.write("[core]\\n")\n'
            '    f.write("    autocrlf = false\\n")\n'
            '    f.write("[credential \\"https://gitee.com\\"]\\n")\n'
            f'    f.write(f"    helper = store --file {{cr}}\\n")\n'
            '    f.write("    username = oauth2\\n")\n'
            "'"
        )
        bash_cmd = bash_cmd.replace("{cr}", creds)

        env = os.environ.copy()
        env["GITCONFIG_FILE"] = gitconfig
        env["CREDS_FILE"] = creds

        result = subprocess.run(["bash", "-c", bash_cmd],
                              capture_output=True, text=True, env=env)
        assert result.returncode == 0, (
            f"python write failed (rc={result.returncode}): {result.stderr}"
        )

        with open(gitconfig, "rb") as f:
            raw = f.read()

        crlf_count = raw.count(b"\r\n")
        bare_cr = raw.count(b"\r") - crlf_count

        print(f"[python] file size: {len(raw)} bytes")
        print(f"[python] CRLF count: {crlf_count}")
        print(f"[python] bare CR count: {bare_cr}")
        print(f"[python] raw:\n{raw.decode()}")

        assert crlf_count == 0 and bare_cr == 0, (
            f"FAIL: CRLF={crlf_count} bare-CR={bare_cr}; "
            f"python with newline='\\n' should produce LF-only output"
        )

        # git can parse all keys
        code, out, err = run_bash(f'git config --file "{gitconfig}" --list')
        assert code == 0, f"git parse failed: {err}\nstderr: {err}"

        keys = {}
        for line in out.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                keys[k] = v

        expected = {
            "core.autocrlf": "false",
            "credential.https://gitee.com.username": "oauth2",
        }
        for k, v in expected.items():
            assert keys.get(k) == v, f"key {k} should be {v!r}, got {keys.get(k)!r}"

        print(f"[python] all {len(keys)} keys validated: {sorted(keys)}")
        return True


def test_credentials_file_is_clean():
    """The .git-credentials-gitee file must be LF-only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        creds = os.path.join(tmpdir, ".git-credentials-gitee")

        script = f'printf \'token\\n\' > "{creds}"'
        run_bash(script)

        with open(creds, "rb") as f:
            raw = f.read()

        print(f"[creds] bytes: {raw!r}")
        assert b"\r" not in raw, f"CR found in credentials file: {raw!r}"
        assert raw == b"token\n"
        return True


def test_full_credential_helper_step():
    """
    Simulate the complete Prepare Gitee credential helper step.
    All generated files must be LF-only.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gitconfig = os.path.join(tmpdir, ".gitconfig-gitee")
        creds     = os.path.join(tmpdir, ".git-credentials-gitee")
        askpass   = os.path.join(tmpdir, ".git-askpass-gitee")

        # Python command from workflow YAML (single-quoted outer)
        python_script = (
            "python -c '\n"
            "import os\n"
            f'cf = os.environ["GITCONFIG_FILE"]\n'
            f'cr = os.environ["CREDS_FILE"]\n'
            'with open(cf, "w", newline="\\n") as f:\n'
            '    f.write("[core]\\n")\n'
            '    f.write("    autocrlf = false\\n")\n'
            '    f.write("[credential \\"https://gitee.com\\"]\\n")\n'
            '    f.write(f"    helper = store --file {cr}\\n")\n'
            '    f.write("    username = oauth2\\n")\n'
            "'"
        )
        python_script = python_script.replace("{cr}", creds)

        script = "\n".join([
            f"printf 'token\\n' > '{creds}'",
            f"chmod 600 '{creds}'",
            python_script,
            f"cat > '{askpass}' <<ASKEOF",
            "#!/bin/sh",
            "case \"$1\" in",
            "  Username*) echo 'oauth2' ;;",
            "  Password*) printf '%s' \"$CLEAN\" ;;",
            "  *) echo ;;",
            "esac",
            "ASKEOF",
            f"sed -i 's/\\r$//' '{askpass}'",
            f"chmod 700 '{askpass}'",
        ])

        env = os.environ.copy()
        env["GITCONFIG_FILE"] = gitconfig
        env["CREDS_FILE"] = creds

        code, out, err = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, env=env
        ).returncode, "", ""
        # Re-run for stdout/stderr
        proc = subprocess.run(["bash", "-c", script],
                            capture_output=True, text=True, env=env)
        code = proc.returncode
        out = proc.stdout
        err = proc.stderr

        assert code == 0, f"Full step failed: {err}"

        results = {}
        for label, path in [
            ("credentials", creds),
            ("gitconfig",    gitconfig),
            ("askpass",      askpass),
        ]:
            with open(path, "rb") as f:
                raw = f.read()
            crlf = raw.count(b"\r\n")
            bare_cr = raw.count(b"\r") - crlf
            ok = (crlf == 0 and bare_cr == 0)
            results[label] = ok
            print(f"[{label}] {len(raw)} bytes, CRLF={crlf}, bare-CR={bare_cr}: {'OK' if ok else 'FAIL'}")
            if not ok:
                print(f"  raw: {raw!r}")

        return all(results.values())


if __name__ == "__main__":
    results = {}

    print("=" * 60)
    print("Test 1: gitconfig via python (LF-only + git-parseable)")
    print("=" * 60)
    try:
        results["test_gitconfig_via_python"] = test_gitconfig_via_python()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_gitconfig_via_python"] = False

    print()
    print("=" * 60)
    print("Test 2: credentials file has no CRLF")
    print("=" * 60)
    try:
        results["test_credentials_file_is_clean"] = test_credentials_file_is_clean()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_credentials_file_is_clean"] = False

    print()
    print("=" * 60)
    print("Test 3: full credential helper step (all files LF-only)")
    print("=" * 60)
    try:
        results["test_full_credential_helper_step"] = test_full_credential_helper_step()
    except AssertionError as e:
        print(f"FAIL: {e}")
        results["test_full_credential_helper_step"] = False

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
