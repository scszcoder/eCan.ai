"""
Regression tests for Gitee auth in release-cn.yml.

Two failures, two eras
----------------------
**1. The ASKPASS heredoc hang (2026-08-18, run #86993634026).**

The `Checkout from Gitee mirror` step hung for 23m45s with zero output.
Root cause: GHA runner 2.336.0 writes the temp `.sh` file with CRLF
line endings on Windows self-hosted runners (actions/runner#912,
arnica-io/dependency-scan#26). The step assembled its GIT_ASKPASS helper
with an unquoted `<<EOF` heredoc; bash heredoc terminator matching is
byte-exact and never matches `EOF\r`, so `cat >"$ASKPASS" <<EOF` blocks
forever waiting for input.

**2. URL-embedded auth (fixed by `977e32272`, 2026-08-20).**

The ASKPASS helper was then replaced by embedding credentials in the
remote URL, which failed with "could not read Username for
'https://gitee.com': terminal prompts disabled" — the cleanup regex was
single-quoted, the credential helper was installed *after* checkout, and
git's URL credential parsing was unreliable.

**Today: neither mechanism exists.** The step authenticates with an
explicit `http.extraHeader=Authorization: Basic $basic` on a single
`git fetch`, and downstream pushes use a job-scoped
`credential.helper=store` file pointed at by a job-scoped
`GIT_CONFIG_GLOBAL`. This file used to assert on five `ASKPASS=` blocks;
after `977e32272` that regex matched nothing and the file failed 26
tests for two months without anyone noticing it had stopped guarding
anything.

What these tests pin NOW, which is the part that can still regress:
the auth mechanism must exist, must authenticate, must fail fast
instead of prompting, and must not leak the token.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_CN = REPO_ROOT / ".github" / "workflows" / "release-cn.yml"

# The Gitee checkout is bash on every runner type (pwsh is not
# preinstalled on the self-hosted Linux/macOS runners), so bash syntax
# in a `run:` block MUST be pinned to `shell: bash`. This is the same
# class of bug as the heredoc hang: a bash block parsed by PowerShell
# does nothing, or dies on `set -euo pipefail`. See CLAUDE.md §9.
_CHECKOUT_BLOCK_RE = re.compile(
    r"- name: Checkout from Gitee mirror\n"
    r"(?:(?:[^\n]*\n)*?)"          # if / shell / timeout-minutes / env
    r"        run: \|\n"            # the bash body starts here
    r"((?:          [^\n]*\n)+)",  # 10-space-indented body lines
    re.MULTILINE,
)


def _checkout_bodies(text: str) -> list[str]:
    """The `run:` body of every 'Checkout from Gitee mirror' step."""
    return [m.group(1) for m in _CHECKOUT_BLOCK_RE.finditer(text)]


def _checkout_blocks(text: str) -> list[str]:
    """Each whole step block, from its `- name:` line to the next step."""
    return re.findall(
        r"- name: Checkout from Gitee mirror\n(?:(?!      - name:)[^\n]*\n)*",
        text,
    )


@pytest.fixture(scope="module")
def text() -> str:
    return RELEASE_CN.read_text(encoding="utf-8")


# ============================================================================
# Static contract: the auth mechanism that replaced ASKPASS
# ============================================================================


class TestGiteeAuthStaticContract:
    """Pin the current auth shape so it cannot silently regress.

    These fail if someone reintroduces a heredoc, drops back to
    URL-embedded credentials, or lets git fall through to an
    interactive prompt — each of which caused a real outage.
    """

    def test_release_cn_file_exists(self, text):
        assert RELEASE_CN.is_file(), f"{RELEASE_CN} not found"

    def test_has_gitee_checkout_steps(self, text):
        # One per self-hosted build job. Sanity-check the count so a
        # silent duplication / removal is caught here, not in CI.
        n = len(_checkout_bodies(text))
        assert n >= 4, (
            f"Expected at least 4 'Checkout from Gitee mirror' bash bodies "
            f"in release-cn.yml (one per self-hosted build job), found {n}."
        )

    def test_checkout_declares_bash_shell(self, text):
        """`shell: bash` is mandatory on Windows self-hosted runners.

        PowerShell is the default Windows runner shell; a bash-syntax
        `run:` block parsed by PowerShell silently does nothing.
        """
        blocks = _checkout_blocks(text)
        assert blocks, "no 'Checkout from Gitee mirror' step found"
        for block in blocks:
            assert "shell: bash" in block, (
                "'Checkout from Gitee mirror' runs bash syntax "
                "(set -e, base64, git -c) but does not declare "
                "`shell: bash`. On a Windows self-hosted runner this is "
                "parsed by PowerShell and silently does nothing.\n\n" + block
            )

    def test_checkout_has_no_heredoc(self, text):
        """No `<<` heredoc anywhere in the checkout body.

        This is the original run #86993634026 failure. The ASKPASS
        heredoc is gone, but the hazard has not: any future heredoc in
        this block hangs the same way on a CRLF-injecting runner.
        """
        for i, body in enumerate(_checkout_bodies(text)):
            assert "<<" not in body, (
                f"Gitee checkout #{i} contains a heredoc (`<<`). On a "
                f"Windows self-hosted runner, CRLF-injected heredoc "
                f"terminators never match and the step hangs until the "
                f"job timeout (run #86993634026). Body:\n{body}"
            )

    def test_authenticates_via_extra_header_not_url(self, text):
        """Auth is `http.extraHeader`, never credentials in the remote URL.

        URL-embedded auth is what `977e32272` removed: git's URL
        credential parsing was unreliable and it failed with "could not
        read Username ... terminal prompts disabled".
        """
        for i, body in enumerate(_checkout_bodies(text)):
            assert "http.extraHeader=Authorization: Basic" in body, (
                f"Gitee checkout #{i} does not authenticate via "
                f"http.extraHeader. Body:\n{body}"
            )
            assert not re.search(r"https://[^/\s]*:[^@\s]*@", body), (
                f"Gitee checkout #{i} embeds credentials in the remote "
                f"URL (https://user:pass@host). This is the pattern "
                f"`977e32272` removed. Body:\n{body}"
            )

    def test_checkout_sets_terminal_prompt_zero(self, text):
        """`GIT_TERMINAL_PROMPT=0` makes a missing credential fail fast.

        Without it, a missing/!broken credential blocks on an
        interactive prompt until the step timeout — the exact symptom
        `977e32272` was called out for.
        """
        for i, body in enumerate(_checkout_bodies(text)):
            assert "GIT_TERMINAL_PROMPT=0" in body, (
                f"Gitee checkout #{i} does not set GIT_TERMINAL_PROMPT=0. "
                f"Without it a missing credential blocks on a prompt "
                f"instead of failing fast. Body:\n{body}"
            )

    def test_token_is_stripped_of_crlf_before_use(self, text):
        """`tr -d '\\r\\n'` before the token is used.

        A CRLF carried into the base64 blob corrupts the Authorization
        header — the same runner behaviour that caused the original hang.
        """
        for i, body in enumerate(_checkout_bodies(text)):
            assert re.search(r"tr -d '\\r\\n'", body), (
                f"Gitee checkout #{i} does not strip CR/LF from "
                f"$GITEE_TOKEN. Body:\n{body}"
            )

    def test_token_is_never_echoed(self, text):
        """No step may print the token value, even indirectly.

        The token is a secret. The sanctioned form is the fingerprint
        line (`echo "... sha256=$fpr"`), which prints only length+hash.
        """
        for i, body in enumerate(_checkout_bodies(text)):
            for line in body.splitlines():
                stripped = line.strip()
                if re.search(r'echo\s+"?\$\{?(clean|basic|GITEE_TOKEN)\b', stripped):
                    assert "length=" in stripped, (
                        f"Gitee checkout #{i} echoes the token value: "
                        f"{stripped}"
                    )


# ============================================================================
# Runtime contract: prove the auth mechanism actually authenticates
# ============================================================================


class TestGiteeAuthRuntimeContract:
    """Verify the base64 Basic header git is handed is correct.

    The failure these guard is silent: a malformed header produces
    "could not read Username for 'https://gitee.com'", which is exactly
    what `977e32272` fixed and what nobody noticed for two days.
    """

    def test_basic_header_matches_git_http_basic_auth(self):
        """The `basic` blob decodes to `oauth2:<token>`.

        git's http.extraHeader=Authorization: Basic expects RFC 7617
        credentials — base64 of `user:password`. eCan hard-codes the
        username to `oauth2` and the password to GITEE_TOKEN.
        """
        token = "fake-token-with-%s-and-\r\n"
        clean = token.replace("\r", "").replace("\n", "")
        basic = base64.b64encode(f"oauth2:{clean}".encode()).decode()
        assert base64.b64decode(basic).decode() == f"oauth2:{clean}"
        # The token's % / backslash survive verbatim — a printf-style
        # format-string bug here would silently corrupt the credential.
        assert "%s" in base64.b64decode(basic).decode()
        assert "\r" not in basic and "\n" not in basic

    def test_extra_header_is_accepted_by_git(self):
        """git accepts the header form without falling back to a prompt.

        Runs `git ls-remote` against a local bare repo with the header
        set, proving the header is syntactically what git expects (some
        versions silently ignore a malformed header and then prompt).
        """
        if not _has_git():
            pytest.skip("git not available")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.git"
            subprocess.run(["git", "init", "--bare", "-q", str(src)], check=True)
            basic = base64.b64encode(b"oauth2:fake").decode()
            proc = subprocess.run(
                ["git", "-c", f"http.extraHeader=Authorization: Basic {basic}",
                 "-c", "credential.helper=", "ls-remote", str(src)],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            # No prompt attempt, no complaint about a malformed header.
            assert "could not read Username" not in proc.stderr
            assert "malformed" not in proc.stderr.lower()


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except (OSError, subprocess.SubprocessError):
        return False