"""
Contract tests for setup-prerequisites.ps1's Gitee network reachability
step (step 7).

Background: release-cn.yml's self-hosted jobs fetch source from the
Gitee mirror (https://gitee.com/songszchen/eCan.ai). On a China-based
runner, gitee.com is frequently unreachable: DNS resolves to a
poisoned CNAME (gitee.com-XXXX.baiduads.com), outbound TCP:443 is
sometimes blocked, and the Smart-HTTP endpoint 401s because the
baiduads node doesn't proxy Git. None of these are fixable from
inside a workflow step — the runner's host DNS, routing, and egress
policy are set before GHA ever starts.

This test pins that setup-prerequisites.ps1 has a step that refuses
to declare the runner ready when gitee.com is unreachable, instead
of letting every build silently time out at the same wall.

If a future PR removes or weakens the gate, this test fails so the
operator knows why. Without it, the regression would only surface
hours later as another opaque 401 from a self-hosted release-cn job.
"""
import re
from pathlib import Path

import pytest

SETUP = Path("build_system/scripts/runner/setup-prerequisites.ps1")


@pytest.fixture(scope="module")
def setup_text() -> str:
    if not SETUP.exists():
        pytest.skip(f"{SETUP} not present")
    return SETUP.read_text()


def test_step_7_gitee_reachability_exists(setup_text: str) -> None:
    """setup-prerequisites.ps1 must have a step numbered [7] that
    probes Gitee reachability. Step numbering is visible to operators
    in the setup log — a missing or renumbered step silently downgrades
    the gate (no probe at all)."""
    assert re.search(
        r"\[7\]\s+Gitee network reachability",
        setup_text,
    ), (
        "setup-prerequisites.ps1 must have a `[7] Gitee network "
        "reachability` step. Without it, self-hosted runners with "
        "broken gitee.com egress silently pass setup and every "
        "release-cn job hangs at git fetch."
    )


def test_step_7_uses_doh_to_bypass_local_dns(setup_text: str) -> None:
    """The probe must use DNS-over-HTTPS, not the local resolver.
    On a runner where local DNS is hijacked to a baiduads.com CNAME
    sink, a normal nslookup returns the poisoned IP — useless. DoH
    asks a public resolver directly and bypasses the hijack."""
    # Match the call site that actually issues the DoH request.
    assert "https://1.1.1.1/dns-query" in setup_text, (
        "Step 7 must issue a DoH query to a public resolver (1.1.1.1) "
        "to bypass any local-DNS hijack. Using nslookup/dig against "
        "the local resolver returns the poisoned baiduads.com CNAME "
        "sink — useless for reachability decisions."
    )


def test_step_7_probes_git_smart_http(setup_text: str) -> None:
    """The probe must hit the Git Smart-HTTP /info/refs endpoint,
    not just DNS or bare HTTPS. A clean DNS answer does not mean
    gitee.com's Git Smart-HTTP endpoint is reachable — that is what
    `git ls-remote` and `git fetch` actually hit, and the failure
    mode the operator cares about."""
    assert "git-upload-pack" in setup_text, (
        "Step 7 must probe the Git Smart-HTTP endpoint "
        "(/info/refs?service=git-upload-pack). DNS + TCP probes "
        "alone miss Smart-HTTP-specific failures (auth, protocol "
        "mismatch, endpoint routing)."
    )


def test_step_7_fail_message_mentions_fix_paths(setup_text: str) -> None:
    """When any probe (DoH, TCP, Smart-HTTP) fails, the step must
    call Fail() with a message that lists concrete fix paths
    (DoH/dnscrypt-proxy, hosts file, VPN, GitHub-hosted runner).
    Without these, the operator hitting this gate doesn't know
    what to do next.

    The Fail() call uses PowerShell string-concat syntax — multiple
    adjacent string literals joined by `+`. We grab a generous
    window after the `Fail (` opening so the test still passes if
    the message grows or shrinks by a few concatenated literals.
    """
    fail_start = setup_text.find('Fail (')
    assert fail_start >= 0, (
        "Step 7 must call Fail() so the runner setup exits non-zero. "
        "Failing open (Warn-and-continue) silently regresses the gate."
    )
    # Grab everything from Fail ( to the next unmatched closing paren
    # at end-of-line. PowerShell's Fail() always closes with `)` on
    # its own line; grabbing 4 KiB is plenty for the documented
    # message and tolerant of future length changes.
    msg_window = setup_text[fail_start:fail_start + 4096]
    # Stop at the first closing `)` that's at end of a line —
    # matches the Fail() call boundary without false-matching
    # balanced parens inside string literals.
    msg = re.split(r'\)\s*$', msg_window, maxsplit=1, flags=re.MULTILINE)[0]

    for hint in ("dnscrypt-proxy", "hosts", "VPN", "github-hosted"):
        assert hint.lower() in msg.lower(), (
            f"Fail() message must mention '{hint}' as a fix path. "
            f"Without it, operators hitting this failure don't know "
            f"what to do next. Current message:\n{msg[:500]}..."
        )


def test_step_7_runs_in_check_mode(setup_text: str) -> None:
    """Network reachability is part of the "is this runner usable"
    check, so step 7 must run in -Check (dry-run) mode too. -Check
    means "don't install"; it does NOT mean "skip network". A runner
    that is healthy on disk but off-net should still fail -Check
    so an operator preflighting their setup sees the same error
    they'd get from a real run."""
    # The explicit comment is the contract; if a refactor drops it,
    # the operator stops seeing the network error in dry-run.
    assert (
        "-Check mode" in setup_text
        and "network is part of the" in setup_text
    ), (
        "Step 7's comments must explicitly state that -Check (dry-run) "
        "still runs the network probe. Without this contract, a "
        "refactor that wraps step 7 in 'if (-not $Check)' silently "
        "downgrades the preflight."
    )