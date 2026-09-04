"""Tests for ``handle_get_parser_engines`` eCanAI-mode key sourcing.

When the user is on the eCanAI provider for MinerU or Docling, the active
API key (``MINERU_API_TOKEN`` / ``DOCLING_API_KEY``) is account-managed
and sourced from ``ECANAI_LLM_API_KEY`` in secure_store — NOT from the
``.env`` file. The save path (``resolve_ecanai_parser_secrets``) already
refreshes the env var from secure_store at write time; this handler
mirrors that on the read path so the UI field never displays a stale
env value (which can be a previous-mode Local key that happened to
live in the same env var).

Other modes (Local / Official) keep their ``.env`` value because that
IS where the user-typed credential is stored — no override happens.
"""

from __future__ import annotations

from unittest.mock import patch

from gui.ipc.w2p_handlers import lightrag_handler as lh


_REQ = {
    "id": "1",
    "method": "lightrag.getParserEngines",
    "params": {},
    "type": "request",
}


class _FakeConfigManager:
    """Minimal stand-in for knowledge.lightrag_config_manager.get_config_manager."""

    def __init__(self, settings: dict):
        self._settings = dict(settings)

    def get_effective_config(self) -> dict:
        return dict(self._settings)


def _call(settings: dict, *, username: str | None, account_key: str | None):
    """Invoke the handler with mocked config manager, username, and secure_store."""

    def fake_get_config_manager():
        return _FakeConfigManager(settings)

    def fake_get_username(request, params):
        return username or ""

    def fake_secure_store_get(key, username=None):
        assert key == "ECANAI_LLM_API_KEY"
        return account_key

    with patch.object(lh, "get_config_manager", fake_get_config_manager), \
         patch("gui.ipc.context_bridge.get_username", fake_get_username), \
         patch("utils.env.secure_store.secure_store") as mock_store:
        mock_store.get.side_effect = fake_secure_store_get
        resp = lh.handle_get_parser_engines(dict(_REQ), {})

    assert resp["status"] == "success", resp
    return resp["result"]


def test_ecanai_mineru_uses_account_key_not_env_value():
    """Mineru eCanAI: MINERU_API_TOKEN in the response is the live account
    key, ignoring whatever value .env currently holds for that env var."""
    result = _call(
        settings={
            "MINERU_API_MODE": "ecanai",
            # env holds a stale local key (e.g. from a previous-mode sync)
            "MINERU_API_TOKEN": "stale-local-key-from-env",
            "MINERU_LOCAL_API_KEY": "user-typed-local",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="alice",
        account_key="fresh-account-key",
    )

    assert result["current"]["MINERU_API_TOKEN"] == "fresh-account-key"
    # Local slot must NOT be touched — user-typed value preserved.
    assert result["current"]["MINERU_LOCAL_API_KEY"] == "user-typed-local"


def test_ecanai_docling_uses_account_key_not_env_value():
    """Docling eCanAI: DOCLING_API_KEY in the response is the live account key."""
    result = _call(
        settings={
            "DOCLING_PROVIDER": "ecanai",
            "DOCLING_API_KEY": "stale-local-key-from-env",
            "DOCLING_LOCAL_API_KEY": "user-typed-docling-local",
            "LIGHTRAG_PARSER": "docling:default",
        },
        username="bob",
        account_key="fresh-account-key",
    )

    assert result["current"]["DOCLING_API_KEY"] == "fresh-account-key"
    assert result["current"]["DOCLING_LOCAL_API_KEY"] == "user-typed-docling-local"


def test_ecanai_no_account_key_clears_field_instead_of_falling_back():
    """Mineru/Docling eCanAI without a provisioned account key must surface an
    empty field, NOT the stale .env value (which would mask the missing
    credential behind a value that no longer authenticates)."""
    result = _call(
        settings={
            "MINERU_API_MODE": "ecanai",
            "DOCLING_PROVIDER": "ecanai",
            "MINERU_API_TOKEN": "stale-env-value",
            "DOCLING_API_KEY": "another-stale-env-value",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="charlie",
        account_key=None,
    )

    assert result["current"]["MINERU_API_TOKEN"] == ""
    assert result["current"]["DOCLING_API_KEY"] == ""


def test_ecanai_signed_out_clears_field():
    """No signed-in username → empty field. secure_store is keyed by username
    so a missing username means we cannot read the credential at all."""
    result = _call(
        settings={
            "MINERU_API_MODE": "ecanai",
            "MINERU_API_TOKEN": "stale-env-value",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username=None,
        account_key=None,
    )

    assert result["current"]["MINERU_API_TOKEN"] == ""


def test_local_mode_keeps_env_value_for_mineru():
    """Local mode is user-typed-only; the handler MUST NOT overwrite the
    env key with the account key, even when an account key is provisioned."""
    result = _call(
        settings={
            "MINERU_API_MODE": "local",
            "MINERU_API_TOKEN": "user-typed-local-key",
            "MINERU_LOCAL_API_KEY": "user-typed-local-key",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="dave",
        account_key="should-not-leak-into-local",
    )

    assert result["current"]["MINERU_API_TOKEN"] == "user-typed-local-key"


def test_local_mode_keeps_env_value_for_docling():
    """Local mode is user-typed-only; the handler MUST NOT overwrite."""
    result = _call(
        settings={
            "DOCLING_PROVIDER": "local",
            "DOCLING_API_KEY": "user-typed-docling-local-key",
            "DOCLING_LOCAL_API_KEY": "user-typed-docling-local-key",
            "LIGHTRAG_PARSER": "docling:default",
        },
        username="dave",
        account_key="should-not-leak-into-local",
    )

    assert result["current"]["DOCLING_API_KEY"] == "user-typed-docling-local-key"


def test_official_mode_keeps_env_value():
    """Official mode is user-typed-only; the handler MUST NOT overwrite with
    the account key (different credentials — eCanAI account token != the
    user-purchased mineru.net / docling.ai API key)."""
    result = _call(
        settings={
            "MINERU_API_MODE": "official",
            "MINERU_API_TOKEN": "user-purchased-mineru-net-key",
            "MINERU_OFFICIAL_API_KEY": "user-purchased-mineru-net-key",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="eve",
        account_key="should-not-leak-into-official",
    )

    assert result["current"]["MINERU_API_TOKEN"] == "user-purchased-mineru-net-key"


def test_ecanai_secure_store_failure_clears_field_silently():
    """If secure_store.get raises, the field must end up empty (logged as
    DEBUG) — never propagate the error to the UI or fall back to a
    possibly-stale env value."""
    def fake_get_config_manager():
        return _FakeConfigManager({
            "MINERU_API_MODE": "ecanai",
            "MINERU_API_TOKEN": "stale-env-value",
            "LIGHTRAG_PARSER": "mineru:default",
        })

    def fake_get_username(request, params):
        return "frank"

    with patch.object(lh, "get_config_manager", fake_get_config_manager), \
         patch("gui.ipc.context_bridge.get_username", fake_get_username), \
         patch("utils.env.secure_store.secure_store") as mock_store:
        mock_store.get.side_effect = RuntimeError("keyring offline")
        resp = lh.handle_get_parser_engines(dict(_REQ), {})

    assert resp["status"] == "success", resp
    assert resp["result"]["current"]["MINERU_API_TOKEN"] == ""


def test_ecanai_marks_endpoint_and_token_as_system_managed():
    """When the active mode is eCanAI the UI must mark the ecanai endpoint
    + token fields as isSystemManaged (read-only). The handler still returns
    the live account key as the field value so the UI can display it."""
    result = _call(
        settings={
            "MINERU_API_MODE": "ecanai",
            "DOCLING_PROVIDER": "ecanai",
            "MINERU_API_TOKEN": "stale-env",
            "DOCLING_API_KEY": "stale-env",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="grace",
        account_key="live-account-key",
    )

    engines_by_id = {e["id"]: e for e in result["engines"]}

    mineru_token = next(f for f in engines_by_id["mineru"]["fields"] if f["key"] == "MINERU_API_TOKEN")
    assert mineru_token.get("isSystemManaged") is True

    docling_token = next(f for f in engines_by_id["docling"]["fields"] if f["key"] == "DOCLING_API_KEY")
    assert docling_token.get("isSystemManaged") is True

    # Local slots are NOT system-managed even when an account key exists.
    mineru_local = next(f for f in engines_by_id["mineru"]["fields"] if f["key"] == "MINERU_LOCAL_API_KEY")
    assert not mineru_local.get("isSystemManaged")


def test_local_mode_does_not_mark_token_as_system_managed():
    """Local mode token stays editable; only eCanAI mode locks the field."""
    result = _call(
        settings={
            "MINERU_API_MODE": "local",
            "MINERU_API_TOKEN": "user-typed-local",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="henry",
        account_key="live-account-key",
    )

    engines_by_id = {e["id"]: e for e in result["engines"]}
    mineru_token = next(f for f in engines_by_id["mineru"]["fields"] if f["key"] == "MINERU_API_TOKEN")
    assert not mineru_token.get("isSystemManaged")


# ── handle_get_parser_engines — mode inference ───────────────────
# Older .env files do not always set MINERU_API_MODE / DOCLING_PROVIDER.
# The handler infers the UI mode from the configured endpoint so a
# legacy self-hosted-eCanAI deployment still surfaces the eCanAI lock
# badge instead of being mistaken for an unrelated "local" service.
# These cases must be pinned: a regression here would silently change
# the field from read-only to editable in the UI.


def test_inferred_ecanai_mode_for_mineru_from_endpoint():
    """Empty MINERU_API_MODE + eCanAI endpoint → handler must treat
    MinerU as ecanai and overlay the account key into MINERU_API_TOKEN.
    Without this inference, legacy .env files leak the stale token
    value into the read-only ecanai field."""
    from knowledge.lightrag_parser_config import ECANAI_PARSER_BASE_URL

    result = _call(
        settings={
            # MINERU_API_MODE intentionally missing
            "MINERU_LOCAL_ENDPOINT": ECANAI_PARSER_BASE_URL,
            "MINERU_API_TOKEN": "stale-env-value",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="ivy",
        account_key="live-account-key",
    )

    assert result["current"]["MINERU_API_TOKEN"] == "live-account-key"
    engines_by_id = {e["id"]: e for e in result["engines"]}
    mineru_token = next(f for f in engines_by_id["mineru"]["fields"] if f["key"] == "MINERU_API_TOKEN")
    assert mineru_token.get("isSystemManaged") is True


def test_inferred_ecanai_mode_for_mineru_when_mode_is_local_with_ecanai_endpoint():
    """LightRAG persists eCanAI as a special-case local mode that
    talks to the fixed eCanAI proxy. The handler must reconstruct the
    UI's eCanAI view from this on-disk shape so the locked-field badge
    and the account-key overlay both apply."""
    from knowledge.lightrag_parser_config import ECANAI_PARSER_BASE_URL

    result = _call(
        settings={
            "MINERU_API_MODE": "local",
            "MINERU_LOCAL_ENDPOINT": ECANAI_PARSER_BASE_URL,
            "MINERU_API_TOKEN": "stale-env-value",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="jack",
        account_key="live-account-key",
    )

    # The override happens in-memory; the ecanai overlay must apply.
    assert result["current"]["MINERU_API_TOKEN"] == "live-account-key"
    engines_by_id = {e["id"]: e for e in result["engines"]}
    mineru_token = next(f for f in engines_by_id["mineru"]["fields"] if f["key"] == "MINERU_API_TOKEN")
    assert mineru_token.get("isSystemManaged") is True


def test_inferred_ecanai_mode_for_docling_from_endpoint():
    """Docling has the same legacy-endpoint inference path."""
    from knowledge.lightrag_parser_config import ECANAI_PARSER_BASE_URL

    result = _call(
        settings={
            # DOCLING_PROVIDER intentionally missing
            "DOCLING_ENDPOINT": ECANAI_PARSER_BASE_URL,
            "DOCLING_API_KEY": "stale-env-value",
            "LIGHTRAG_PARSER": "docling:default",
        },
        username="kate",
        account_key="live-account-key",
    )

    assert result["current"]["DOCLING_API_KEY"] == "live-account-key"
    engines_by_id = {e["id"]: e for e in result["engines"]}
    docling_token = next(f for f in engines_by_id["docling"]["fields"] if f["key"] == "DOCLING_API_KEY")
    assert docling_token.get("isSystemManaged") is True


def test_local_endpoint_inferred_as_local_mode():
    """If the configured endpoint is NOT the eCanAI proxy the handler
    must default to 'local' so the user sees an editable local-mode UI
    rather than the locked eCanAI view."""
    result = _call(
        settings={
            # MINERU_API_MODE missing, endpoint is some user's self-hosted MinerU
            "MINERU_LOCAL_ENDPOINT": "https://user-mineru.example.com/api",
            "MINERU_API_TOKEN": "user-typed-local",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        username="liam",
        account_key="should-not-leak",
    )

    # Mode inferred as local → the user-typed value wins, the account
    # key MUST NOT replace it.
    assert result["current"]["MINERU_API_TOKEN"] == "user-typed-local"
    engines_by_id = {e["id"]: e for e in result["engines"]}
    mineru_token = next(f for f in engines_by_id["mineru"]["fields"] if f["key"] == "MINERU_API_TOKEN")
    assert not mineru_token.get("isSystemManaged")


# ── handle_get_ecanai_api_key — read path ─────────────────────────
# The parser UI uses ``handle_get_ecanai_api_key`` to auto-fill the
# field on demand. The semantics are: success-with-None when no key is
# provisioned (the UI then shows an empty field) and success-with-the
# key when secure_store has one. Errors must NOT propagate — the UI
# would otherwise fail to render the field for a transient keyring
# glitch.


def _call_get_ecanai_api_key(*, username: str | None, side_effect=None, return_value=None):
    """Invoke ``handle_get_ecanai_api_key`` with the given secure_store
    behavior. ``side_effect``/``return_value`` are forwarded to the
    mocked ``secure_store.get``."""
    def fake_get_username(request, params):
        return username or ""

    with patch("gui.ipc.context_bridge.get_username", fake_get_username), \
         patch("utils.env.secure_store.secure_store") as mock_store:
        if side_effect is not None:
            mock_store.get.side_effect = side_effect
        else:
            mock_store.get.return_value = return_value
        resp = lh.handle_get_ecanai_api_key(dict(_REQ), {})

    return resp


def test_get_ecanai_api_key_returns_key_when_signed_in():
    """Happy path: signed-in user with a provisioned account key gets
    the key back as a string. The handler must never leak the
    raw secure_store sentinel (None / empty) as a string."""
    resp = _call_get_ecanai_api_key(
        username="alice", return_value="live-account-key-1234567890"
    )
    assert resp["status"] == "success"
    assert resp["result"]["apiKey"] == "live-account-key-1234567890"


def test_get_ecanai_api_key_returns_none_when_not_signed_in():
    """Without a username, secure_store is keyed by 'default' and would
    leak another tenant's value, so the handler MUST return None
    instead of looking up the store at all."""
    resp = _call_get_ecanai_api_key(username=None, return_value="WRONG-USER-KEY")
    assert resp["status"] == "success"
    assert resp["result"]["apiKey"] is None


def test_get_ecanai_api_key_returns_none_when_key_is_missing():
    """Provisioned user, no key yet → None (not empty string, not an
    error). The Account page renders the generate button when this
    response comes back."""
    resp = _call_get_ecanai_api_key(username="bob", return_value=None)
    assert resp["status"] == "success"
    assert resp["result"]["apiKey"] is None


def test_get_ecanai_api_key_swallows_secure_store_errors():
    """A transient keyring error must NOT surface as a failed IPC
    response — the Settings UI would lose its field entirely. The
    handler logs at DEBUG and returns None so the UI degrades to an
    empty field instead of a stack-trace dialog."""
    resp = _call_get_ecanai_api_key(
        username="carol",
        side_effect=RuntimeError("keyring offline"),
    )
    assert resp["status"] == "success"
    assert resp["result"]["apiKey"] is None


def test_get_ecanai_api_key_normalizes_empty_string_to_none():
    """A secure_store entry of "" (or whitespace) is "not provisioned".
    Returning "" would render an empty password input that pretends to
    be filled; the UI contract is None for that state."""
    resp = _call_get_ecanai_api_key(username="dave", return_value="   ")
    assert resp["status"] == "success"
    assert resp["result"]["apiKey"] is None