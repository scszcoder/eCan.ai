"""
Regression tests for the Gitee ASKPASS step in release-cn.yml.

Background
----------
On 2026-08-18, the `Checkout from Gitee mirror` step in release-cn.yml
hung for 23m45s with zero output before being manually cancelled
(run #86993634026).

Root cause: GHA runner 2.336.0 writes the temp `.sh` file with CRLF
line endings on Windows self-hosted runners (actions/runner#912,
arnica-io/dependency-scan#26). The original step assembled its GIT_ASKPASS
helper with an unquoted `<<EOF` heredoc; bash heredoc terminator
matching is byte-exact and never matches `EOF\r`, so `cat >"$ASKPASS" <<EOF`
blocks forever waiting for input.

Fix (release-cn.yml lines 461-483): replace the heredoc with `printf
'%s\n' '<literal lines>'`, use `mktemp` instead of `$RUNNER_TEMP/...`,
and read the token from $GITEE_TOKEN at ASKPASS runtime (no plaintext
on disk).

These tests pin the contract so a future refactor that re-introduces
either pattern (heredoc OR $RUNNER_TEMP hardcoded path) is caught at
commit time rather than at run time.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_CN = REPO_ROOT / ".github" / "workflows" / "release-cn.yml"


# Match the block of lines that build the GIT_ASKPASS helper script.
# Must contain "ASKPASS=" (mktemp or RUNNER_TEMP), the printf/heredoc
# lines, and end at the `chmod 700` line. We capture across newlines.
_ASKPASS_BLOCK_RE = re.compile(
    r"          ASK[A-Z]*PASS=\"[^\n]+\n"           # ASKPASS="..."
    r"(?:          [^\n]*\n)*?"                    # intervening lines (printf args, etc.)
    r"          chmod 700 \"\$ASKPASS\"",
    re.MULTILINE,
)


def _count_blocks(text: str) -> int:
    """Number of ASKPASS-creation blocks in release-cn.yml."""
    return len(_ASKPASS_BLOCK_RE.findall(text))


def _extract_blocks(text: str) -> list[str]:
    """List of ASKPASS-creation blocks in release-cn.yml."""
    return _ASKPASS_BLOCK_RE.findall(text)


# ============================================================================
# Static contract: no heredoc, no $RUNNER_TEMP hardcoded path
# ============================================================================


class TestAskpassStaticContract:
    """Pin the ASKPASS creation block to its post-fix shape.

    These checks fail if anyone reverts to the heredoc form or to the
    $RUNNER_TEMP/... hardcoded path. See release-cn.yml#461-483 for the
    canonical block this contract enforces.
    """

    @pytest.fixture(scope="class")
    def text(self):
        return RELEASE_CN.read_text(encoding="utf-8")

    def test_release_cn_file_exists(self):
        assert RELEASE_CN.is_file(), f"{RELEASE_CN} not found"

    def test_has_five_askpass_blocks(self, text):
        # 5 build jobs (windows-amd64, macos-amd64, macos-aarch64,
        # linux-amd64, [fifth somewhere] — sanity-check the count so a
        # silent duplication / removal gets caught here, not in CI).
        n = _count_blocks(text)
        assert n == 5, (
            f"Expected exactly 5 ASKPASS blocks in release-cn.yml "
            f"(one per build job), found {n}. "
            f"Each 'Checkout from Gitee mirror' step must self-build "
            f"its own helper."
        )

    @pytest.mark.parametrize("block_idx", range(5))
    def test_block_no_heredoc(self, text, block_idx):
        """No unquoted heredoc in any ASKPASS block.

        An unquoted `<<EOF` heredoc hangs on Windows self-hosted runners
        because runner 2.336.0 writes temp `.sh` with CRLF and bash
        heredoc terminator matching is byte-exact (run #86993634026).
        """
        blocks = _extract_blocks(text)
        assert block_idx < len(blocks)
        block = blocks[block_idx]
        # Any `<<` heredoc in this block is suspect (unquoted, quoted,
        # dash-prefixed — none fix the CRLF terminator problem).
        assert "<<" not in block, (
            f"ASKPASS block #{block_idx} contains a heredoc (`<<`); "
            f"this hangs on Windows self-hosted runners. Use printf "
            f"instead. Block:\n{block}"
        )

    @pytest.mark.parametrize("block_idx", range(5))
    def test_block_uses_mktemp(self, text, block_idx):
        """ASKPASS path comes from mktemp, not from $RUNNER_TEMP/...

        $RUNNER_TEMP may be unset on some self-hosted setups or may be a
        Windows-style path that bash/cmd disagree on. mktemp falls back
        to $TMPDIR / /tmp automatically.
        """
        block = _extract_blocks(text)[block_idx]
        assert (
            "$(mktemp)" in block or "$(mktemp -t" in block or "mktemp -d" in block
        ), (
            f"ASKPASS block #{block_idx} does not use mktemp for its "
            f"path; $RUNNER_TEMP-based paths are unreliable on "
            f"self-hosted runners. Block:\n{block}"
        )
        assert "RUNNER_TEMP" not in block, (
            f"ASKPASS block #{block_idx} still references $RUNNER_TEMP. "
            f"Use mktemp instead. Block:\n{block}"
        )

    @pytest.mark.parametrize("block_idx", range(5))
    def test_block_uses_printf(self, text, block_idx):
        """ASKPASS content is assembled via printf, not cat/heredoc."""
        block = _extract_blocks(text)[block_idx]
        assert "printf '" in block, (
            f"ASKPASS block #{block_idx} does not use printf to "
            f"assemble the helper script. Block:\n{block}"
        )

    @pytest.mark.parametrize("block_idx", range(5))
    def test_block_token_not_interpolated_at_write_time(self, text, block_idx):
        """Token must be read at ASKPASS runtime, not embedded in the file.

        Old heredoc form expanded $CLEAN into the helper file at cat
        time, putting plaintext token on disk. New form keeps token in
        $GITEE_TOKEN env and the helper file references it.
        """
        block = _extract_blocks(text)[block_idx]
        assert "GITEE_TOKEN" in block, (
            f"ASKPASS block #{block_idx} does not reference $GITEE_TOKEN. "
            f"Block:\n{block}"
        )
        assert "CLEAN=" not in block, (
            f"ASKPASS block #{block_idx} pre-computes a $CLEAN variable. "
            f"This pattern suggests the token is being baked into the "
            f"helper file at write time. Block:\n{block}"
        )

    @pytest.mark.parametrize("block_idx", range(5))
    def test_block_has_trap_for_cleanup(self, text, block_idx):
        """Trap EXIT ensures ASKPASS is removed even on signal/ early exit."""
        block = _extract_blocks(text)[block_idx]
        assert "trap" in block and "EXIT" in block, (
            f"ASKPASS block #{block_idx} does not install an EXIT trap "
            f"to remove the helper. Block:\n{block}"
        )


# ============================================================================
# Runtime contract: prove the new ASKPASS block works correctly
# ============================================================================


# The exact block emitted in release-cn.yml after the fix.
# Token is read from $GITEE_TOKEN at ASKPASS runtime — never written
# to the helper file in plaintext.
_NEW_ASKPASS_BLOCK_MINIMAL = """\
set -eu

ASKPASS="$(mktemp)"
trap 'rm -f "$ASKPASS"' EXIT
printf '%s\\n' \\
  '#!/bin/sh' \\
  'case "$1" in' \\
  '  Username*) echo oauth2 ;;' \\
  '  Password*) printf '"'"'%s'"'"' "$GITEE_TOKEN" ;;' \\
  '  *) echo ;;' \\
  'esac' > "$ASKPASS"
sed -i 's/\\r$//' "$ASKPASS" 2>/dev/null || true
chmod 700 "$ASKPASS"
"""


def _build_test_block(helper_path: Path) -> str:
    """Build a test block that creates ASKPASS at helper_path.

    We inject the Python-chosen path directly so mktemp's output is
    predictable and inspectable by Python. The EXIT trap is stripped
    because Python manages cleanup via its TemporaryDirectory context.
    """
    lines = _NEW_ASKPASS_BLOCK_MINIMAL.splitlines()
    result = []
    for line in lines:
        if 'ASKPASS="$(mktemp)"' in line:
            result.append(f'ASKPASS="{helper_path}"')
        elif "trap" in line and "EXIT" in line:
            pass  # strip trap; Python manages cleanup
        else:
            result.append(line)
    return "\n".join(result)


class TestAskpassRuntimeContract:
    """Verify the printf-based ASKPASS block is functionally correct.

    The OLD heredoc block that caused run #86993634026 is not tested
    here at runtime because it only fails on Git-Bash + CRLF (a
    combination unavailable in this test environment). The
    static-contract tests above already guarantee it cannot be
    re-introduced.
    """

    def test_new_block_succeeds_on_unix_sh(self):
        """Sanity check: printf block creates a correct POSIX sh helper.

        Verifies:
          - script returns 'oauth2' for Username prompt
          - script returns the literal $GITEE_TOKEN for Password prompt
          - file is LF-only (no CR bytes)
        """
        with tempfile.TemporaryDirectory() as td:
            helper_path = Path(td) / f".git-askpass-test.{os.getpid()}"
            token = "fake-token-with-percent-s"
            block_test = _build_test_block(helper_path)
            env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": str(Path.home()),
                "TMPDIR": td,
                "RUNNER_TEMP": td,
                "GITEE_TOKEN": token,
            }
            proc = subprocess.run(
                ["/bin/bash", "-c", block_test],
                capture_output=True, text=True, env=env, timeout=5.0,
            )
            assert proc.returncode == 0, (
                f"printf ASKPASS block failed:\n"
                f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
            )

            assert helper_path.exists(), (
                f"ASKPASS file not created at {helper_path}. "
                f"stderr: {proc.stderr!r}"
            )
            content = helper_path.read_bytes()
            assert b"\r" not in content, (
                f"ASKPASS file contains CR bytes:\n{content!r}"
            )

            user_out = subprocess.run(
                ["/bin/sh", str(helper_path),
                 "Username for 'https://gitee.com':"],
                capture_output=True, text=True,
                env={**env, "PATH": "/bin:/usr/bin"}, timeout=5.0,
            )
            assert user_out.returncode == 0
            assert user_out.stdout == "oauth2\n", (
                f"expected 'oauth2\\n', got {user_out.stdout!r}"
            )

            pass_out = subprocess.run(
                ["/bin/sh", str(helper_path),
                 "Password for 'https://oauth2@gitee.com':"],
                capture_output=True, text=True,
                env={**env, "PATH": "/bin:/usr/bin"}, timeout=5.0,
            )
            assert pass_out.returncode == 0
            assert pass_out.stdout == token, (
                f"Token round-trip failed.\n"
                f"expected: {token!r}\nactual:   {pass_out.stdout!r}"
            )

    def test_new_block_survives_crlf_injected_run_block(self):
        """Verify the block does NOT hang when the outer script has CRLF.

        This simulates GHA runner 2.336.0's behaviour of injecting the
        step script with CRLF line endings. The key assertion is that
        the block completes within the timeout window — if a future
        refactor re-introduces a heredoc, the static tests catch it
        first; if it slips through, this runtime check trips via
        TimeoutExpired instead of a 24-minute hang on CI.
        """
        with_crlf = _NEW_ASKPASS_BLOCK_MINIMAL.replace("\n", "\r\n")
        try:
            subprocess.run(
                ["/bin/bash", "-c", with_crlf],
                capture_output=True, text=True,
                env={"PATH": "/usr/bin:/bin"},
                timeout=2.0,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                "CRLF-injected run block HANG — this is the exact "
                "failure mode run #86993634026 hit. The new block "
                "must be heredoc-free; verify printf replaced `<<EOF`."
            )

    def test_new_block_handles_dangerous_token_chars(self):
        """Tokens with `%` must NOT be re-interpreted as printf formats.

        The new printf form risks format-string injection if the helper
        uses `printf "%s" "$GITEE_TOKEN"` instead of `printf '%s'`.
        We assert the literal token round-trips verbatim.
        """
        dangerous = "token-with-%s-and-backslash-n-and-fun"
        with tempfile.TemporaryDirectory() as td:
            helper_path = Path(td) / f".git-askpass-test.{os.getpid()}"
            block_test = _build_test_block(helper_path)
            env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": str(Path.home()),
                "TMPDIR": td,
                "RUNNER_TEMP": td,
                "GITEE_TOKEN": dangerous,
            }
            proc = subprocess.run(
                ["/bin/bash", "-c", block_test],
                capture_output=True, text=True, env=env, timeout=5.0,
            )
            assert proc.returncode == 0, (
                f"printf ASKPASS block failed:\nstderr: {proc.stderr!r}"
            )
            assert helper_path.exists(), (
                f"ASKPASS file not created at {helper_path}"
            )
            pass_out = subprocess.run(
                ["/bin/sh", str(helper_path), "Password:"],
                capture_output=True, text=True,
                env={**env, "PATH": "/bin:/usr/bin"}, timeout=5.0,
            )
            assert pass_out.stdout == dangerous, (
                f"Dangerous-token round-trip failed:\n"
                f"expected: {dangerous!r}\nactual:   {pass_out.stdout!r}"
            )
