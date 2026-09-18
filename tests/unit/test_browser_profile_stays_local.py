"""A browser profile must not leave this machine on its own.

A profile is the most sensitive thing the app holds: a live logged-in session
for a real store account, the proxy credentials that identity egresses through,
and the fingerprint it presents. Losing one is not "leaked config" -- it is
someone else able to act as that seller.

So the rule is **local by default**, and going to the cloud is a decision the
user makes per profile, not something a sync path does on their behalf. That is
true today because nothing cloud-bound references the registry at all; this
guards it, because the failure mode is a well-meaning "sync everything" change
that nobody reads as a security decision.

If a legitimate cloud path is added later: the user commands it explicitly, it
names one profile, and it warns first. Add that module to ALLOWED below with a
comment saying which of those three it satisfies -- do not delete the test.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Anywhere a profile could get swept into an upload, a sync queue, or an image.
CLOUD_BOUND_DIRS = (
    "agent/cloud_api",
    "agent/cloud_worker",
    "utils/storage",
    "lambda_functions",
)

# Names that only appear when something is reaching for a profile.
PROFILE_REFERENCES = re.compile(
    r"browser_profiles\.json|profile_registry|fingerprint_browser|"
    r"ecan_browser_proxy|browser_data_root"
)

# Modules cleared to touch profiles despite living in a cloud-bound tree.
# Empty on purpose: there is no such path yet.
ALLOWED: set = set()


def _python_files(rel_dir):
    root = REPO / rel_dir
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_cloud_bound_module_reaches_for_a_browser_profile():
    offenders = []
    for rel_dir in CLOUD_BOUND_DIRS:
        for path in _python_files(rel_dir):
            rel = path.relative_to(REPO).as_posix()
            if rel in ALLOWED:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            hit = PROFILE_REFERENCES.search(text)
            if hit:
                offenders.append("{}: {}".format(rel, hit.group(0)))

    assert not offenders, (
        "Cloud-bound code is reaching for browser profiles:\n  "
        + "\n  ".join(offenders)
        + "\n\nA profile is a live logged-in session plus proxy credentials. "
          "If this is a deliberate, user-commanded path, add the module to "
          "ALLOWED in this test with a note on how the user authorises it."
    )


def test_the_registry_lives_outside_the_repo():
    """The session directory must never land somewhere that gets committed."""
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg

    root = reg.browser_data_root().resolve()
    assert REPO not in root.parents and root != REPO, (
        "browser_data_root() resolves inside the repo ({}); sessions and "
        "cookies would be one 'git add -A' from being committed.".format(root)
    )


def test_the_ipc_dto_cannot_carry_a_password_off_the_backend():
    """The GUI is told a password exists, never what it is."""
    try:
        from gui.ipc.w2p_handlers import browser_profile_handler as h
    except Exception as exc:                        # pragma: no cover
        pytest.skip("IPC handler stack unavailable: {}".format(exc))

    stored = {
        "id": "etsy",
        "label": "Etsy",
        "user_data_dir": r"C:\ecan_browser_data\etsy_ab12cd",
        "proxy": {
            "scheme": "socks5", "host": "p.example", "port": 1080,
            "username": "u",
            "password_ref": "ecan_browser_proxy/etsy",
            # Even if a stray literal ever got into the record, it must not
            # survive the trip to the front end.
            "password": "s3cret",
        },
    }
    dto = h._to_dto(stored)

    import json
    payload = json.dumps(dto)
    assert "s3cret" not in payload
    assert "password_ref" not in payload
    assert dto["proxy"]["has_password"] is True
