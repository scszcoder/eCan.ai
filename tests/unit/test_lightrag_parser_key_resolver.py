"""Tests for ``resolve_ecanai_parser_secrets`` — the save-time resolver
that pins parser credentials into ``lightrag.env`` correctly for every
mode combination.

The function is the single source of truth for the ``MINERU_API_TOKEN``
and ``DOCLING_API_KEY`` env values that LightRAG reads at startup. It
sits on the save path of ``lightrag.saveSettings`` and is the only
chance we get to refuse a save that would leave LightRAG pointing at
the wrong credential. The handler-level tests in
``test_lightrag_get_parser_engines.py`` cover the read path; this file
covers the write-path invariants that the save path depends on.

Contract (read each test docstring for the exact rule):

- eCanAI mode: account key is authoritative. A user-typed value is
  treated as a self-hosted ecanai-proxy custom key and preserved only
  when no account key is provisioned.
- Local mode: ``MINERU_LOCAL_API_KEY`` / ``DOCLING_LOCAL_API_KEY`` copy
  into the active env var verbatim. The endpoint mirror
  (``MINERU_LOCAL_ENDPOINT_SETTING`` → ``MINERU_LOCAL_ENDPOINT``) is
  applied so LightRAG reads the value the user actually typed.
- Official mode: ``MINERU_OFFICIAL_API_KEY`` / ``DOCLING_OFFICIAL_API_KEY``
  copy into the active env var verbatim.
- Per-mode keys MUST NOT leak across modes (a local key MUST NOT
  end up in ``MINERU_API_TOKEN`` when the user is in eCanAI mode).
"""

from __future__ import annotations

import pytest

from knowledge.lightrag_parser_config import (
    ECANAI_PARSER_BASE_URL,
    LIGHTRAG_PARSER_KEY,
    resolve_ecanai_parser_secrets,
    validate_parser_endpoints,
)


ECANAI_KEY = "live-account-key-9876543210"


# ── MinerU eCanAI ─────────────────────────────────────────────────


def test_mineru_ecanai_with_account_key_overrides_user_typed_value():
    """Account key is the authoritative credential in eCanAI mode. A
    stale user-typed value coming from a previous Local save MUST be
    replaced, not preserved."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "ecanai",
            "MINERU_API_TOKEN": "stale-local-key",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        ECANAI_KEY,
    )
    assert out["MINERU_API_TOKEN"] == ECANAI_KEY
    # The ecanai endpoint slot is always written to the canonical
    # eCanAI proxy URL so LightRAG never inherits a stale value.
    assert out["MINERU_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL


def test_mineru_ecanai_without_account_key_preserves_user_typed_value():
    """No account key, but the user typed a value into the dedicated
    eCanAI field — this is a self-hosted ecanai proxy and MUST be
    preserved verbatim."""
    user_key = "self-hosted-ecanai-proxy-key"
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "ecanai",
            "MINERU_API_TOKEN": user_key,
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["MINERU_API_TOKEN"] == user_key


def test_mineru_ecanai_without_any_key_returns_empty_token():
    """No account key AND no user-typed value: the field is set to
    empty string so the downstream ``handle_save_settings`` validation
    can refuse the save with a clear ``PARSER_CONFIG_ERROR`` instead
    of silently leaving LightRAG without a credential."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "ecanai",
            # No MINERU_API_TOKEN
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["MINERU_API_TOKEN"] == ""


def test_mineru_ecanai_does_not_leak_local_key():
    """A MINERU_LOCAL_API_KEY that the user typed before flipping the
    mode to ecanai MUST NOT appear in MINERU_API_TOKEN. Otherwise the
    local credential would silently leak into the ecanai path."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "ecanai",
            "MINERU_LOCAL_API_KEY": "user-local-key",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        ECANAI_KEY,
    )
    assert out["MINERU_API_TOKEN"] == ECANAI_KEY
    # The local key itself is left untouched; only the active env var
    # is rewritten.
    assert out["MINERU_LOCAL_API_KEY"] == "user-local-key"


# ── MinerU local ──────────────────────────────────────────────────


def test_mineru_local_copies_user_typed_local_key_into_active_env():
    """In local mode the per-mode key MUST be copied into
    ``MINERU_API_TOKEN`` so LightRAG reads the right credential after
    restart. The per-mode key is preserved so the user can switch
    back later."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "local",
            "MINERU_LOCAL_API_KEY": "user-local-key",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["MINERU_API_TOKEN"] == "user-local-key"
    assert out["MINERU_LOCAL_API_KEY"] == "user-local-key"


def test_mineru_local_mirrors_endpoint_setting_into_legacy_field():
    """The new UI writes the endpoint into
    ``MINERU_LOCAL_ENDPOINT_SETTING`` while LightRAG 1.5.x still reads
    ``MINERU_LOCAL_ENDPOINT``. The resolver MUST mirror them so
    LightRAG receives the user-typed value on the next start."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "local",
            "MINERU_LOCAL_ENDPOINT_SETTING": "https://user-mineru.example.com/api",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["MINERU_LOCAL_ENDPOINT"] == "https://user-mineru.example.com/api"
    # The new setting slot is preserved so the UI can keep using it.
    assert out["MINERU_LOCAL_ENDPOINT_SETTING"] == "https://user-mineru.example.com/api"


def test_mineru_local_without_user_typed_key_does_not_overwrite_existing_token():
    """If neither the per-mode key nor the active env var is set, the
    resolver MUST NOT inject an empty string into MINERU_API_TOKEN
    (that would silently delete a previously-saved credential coming
    from a legacy .env file). The dict simply doesn't include the key
    in that case."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "local",
            # Neither MINERU_LOCAL_API_KEY nor MINERU_API_TOKEN
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert "MINERU_API_TOKEN" not in out


# ── MinerU official ───────────────────────────────────────────────


def test_mineru_official_copies_user_typed_official_key_into_active_env():
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "official",
            "MINERU_OFFICIAL_API_KEY": "user-purchased-mineru-net-key",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["MINERU_API_TOKEN"] == "user-purchased-mineru-net-key"
    # Official key must not leak into ecanai or local slots.
    assert out.get("MINERU_ECANAI_API_KEY", "") == "" or "MINERU_ECANAI_API_KEY" not in out


# ── Docling: mirrors the MinerU contract for every mode ───────────


def test_docling_ecanai_with_account_key_overrides_user_typed_value():
    out = resolve_ecanai_parser_secrets(
        {
            "DOCLING_PROVIDER": "ecanai",
            "DOCLING_API_KEY": "stale-local-key",
            "LIGHTRAG_PARSER": "docling:default",
        },
        ECANAI_PARSER_BASE_URL,
        ECANAI_KEY,
    )
    assert out["DOCLING_API_KEY"] == ECANAI_KEY
    assert out["DOCLING_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL


def test_docling_ecanai_without_account_key_preserves_user_typed_value():
    user_key = "self-hosted-docling-proxy-key"
    out = resolve_ecanai_parser_secrets(
        {
            "DOCLING_PROVIDER": "ecanai",
            "DOCLING_API_KEY": user_key,
            "LIGHTRAG_PARSER": "docling:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["DOCLING_API_KEY"] == user_key


def test_docling_local_copies_user_typed_local_key_into_active_env():
    out = resolve_ecanai_parser_secrets(
        {
            "DOCLING_PROVIDER": "local",
            "DOCLING_LOCAL_API_KEY": "user-local-docling-key",
            "LIGHTRAG_PARSER": "docling:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["DOCLING_API_KEY"] == "user-local-docling-key"


def test_docling_official_copies_user_typed_official_key_into_active_env():
    out = resolve_ecanai_parser_secrets(
        {
            "DOCLING_PROVIDER": "official",
            "DOCLING_OFFICIAL_API_KEY": "user-purchased-docling-ai-key",
            "LIGHTRAG_PARSER": "docling:default",
        },
        ECANAI_PARSER_BASE_URL,
        "",
    )
    assert out["DOCLING_API_KEY"] == "user-purchased-docling-ai-key"


def test_docling_ecanai_does_not_leak_local_key():
    """The local-mode key MUST NOT cross into the ecanai active env."""
    out = resolve_ecanai_parser_secrets(
        {
            "DOCLING_PROVIDER": "ecanai",
            "DOCLING_LOCAL_API_KEY": "user-local-docling-key",
            "LIGHTRAG_PARSER": "docling:default",
        },
        ECANAI_PARSER_BASE_URL,
        ECANAI_KEY,
    )
    assert out["DOCLING_API_KEY"] == ECANAI_KEY
    assert out["DOCLING_LOCAL_API_KEY"] == "user-local-docling-key"


# ── Cross-engine isolation ────────────────────────────────────────


def test_mineru_and_docling_keys_do_not_leak_across_engines():
    """The resolver must be independent per engine: a MinerU value
    MUST NOT end up in DOCLING_API_KEY and vice versa, even when one
    engine is in ecanai and the other in local."""
    out = resolve_ecanai_parser_secrets(
        {
            "MINERU_API_MODE": "ecanai",
            "DOCLING_PROVIDER": "local",
            "MINERU_API_TOKEN": "stale-shared-env-value",
            "DOCLING_API_KEY": "stale-shared-env-value",
            "DOCLING_LOCAL_API_KEY": "user-local-docling-key",
            "LIGHTRAG_PARSER": "mineru:default,docling:default",
        },
        ECANAI_PARSER_BASE_URL,
        ECANAI_KEY,
    )
    # MinerU ecanai gets the account key.
    assert out["MINERU_API_TOKEN"] == ECANAI_KEY
    # Docling local gets its own per-mode key.
    assert out["DOCLING_API_KEY"] == "user-local-docling-key"


def test_resolver_is_pure_does_not_mutate_input():
    """The resolver must not mutate the caller's dict in place. The
    save path in ``handle_save_settings`` keeps using the input
    settings for logging and routing decisions, so a mutation here
    would be a foot-gun."""
    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_API_TOKEN": "stale",
        "LIGHTRAG_PARSER": "mineru:default",
    }
    snapshot = dict(settings)
    resolve_ecanai_parser_secrets(settings, ECANAI_PARSER_BASE_URL, ECANAI_KEY)
    assert settings == snapshot


@pytest.mark.parametrize(
    "settings",
    [
        # Missing mode defaults to ecanai (the schema's default) so the
        # resolver MUST classify the save as ecanai and use the account
        # key — otherwise legacy saves would silently land in the
        # ecanai branch but get treated as local.
        {
            "MINERU_API_TOKEN": "stale",
            "LIGHTRAG_PARSER": "mineru:default",
        },
        {
            "DOCLING_API_KEY": "stale",
            "LIGHTRAG_PARSER": "docling:default",
        },
    ],
)
def test_missing_mode_string_defaults_to_ecanai(settings):
    """A legacy .env file with no ``MINERU_API_MODE`` / ``DOCLING_PROVIDER``
    must be classified as ecanai (matching the UI default) and use the
    account key. Otherwise a fresh save on top of a legacy .env would
    silently leave a local-mode field in place."""
    out = resolve_ecanai_parser_secrets(
        settings, ECANAI_PARSER_BASE_URL, ECANAI_KEY
    )
    if "MINERU_API_MODE" in settings or "MINERU_API_TOKEN" in settings:
        assert out["MINERU_API_TOKEN"] == ECANAI_KEY
    if "DOCLING_PROVIDER" in settings or "DOCLING_API_KEY" in settings:
        assert out["DOCLING_API_KEY"] == ECANAI_KEY


# ── validate_parser_endpoints — final save-time gate ──────────────
# This runs AFTER resolve_ecanai_parser_secrets. It catches saves
# that would leave LightRAG pointing at a parser it cannot start. A
# regression here would either let a half-configured save through
# (LightRAG then refuses to start) or block a valid one.


def test_mineru_ecanai_validates_mineru_api_token_must_be_set():
    """After the resolver runs, an empty MINERU_API_TOKEN in ecanai
    mode is a hard error. The earlier save handler rejects this with
    a clearer PARSER_CONFIG_ERROR; this test pins the validator so a
    caller that bypasses the handler still cannot write a broken
    config."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "ecanai",
        # MINERU_API_TOKEN intentionally empty
    })
    assert errors, "ecanai mode with empty token must error"
    assert any("mineru" in e.lower() and "API Key" in e for e in errors)


def test_mineru_ecanai_accepts_filled_token():
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "ecanai",
        "MINERU_API_TOKEN": "live-account-key",
    })
    assert errors == []


def test_mineru_local_does_not_check_mineru_api_token():
    """Local mode owns the credential separately, so an empty
    ``MINERU_API_TOKEN`` is fine as long as the per-mode key is set.
    The validator must not leak the ecanai-mode check into local."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "https://user-mineru.example.com/api",
        "MINERU_LOCAL_API_KEY": "user-typed-local",
        # MINERU_API_TOKEN intentionally empty
    })
    assert errors == []


def test_mineru_local_rejects_missing_per_mode_credentials():
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "local",
        # Both endpoint and per-mode key missing
    })
    assert errors, "local mode without endpoint+key must error"
    assert any("MINERU_LOCAL_ENDPOINT" in e and "MINERU_LOCAL_API_KEY" in e for e in errors)


def test_mineru_official_rejects_missing_official_credentials():
    """Official mode requires the user-purchased mineru.net key. The
    official endpoint is a fixed URL baked into the client, so only
    the key is validated here."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "official",
        # No MINERU_OFFICIAL_API_KEY
    })
    assert errors, "official mode without key must error"
    assert any("MINERU_OFFICIAL_API_KEY" in e for e in errors)


def test_mineru_local_key_does_not_satisfy_ecanai_requirement():
    """Critical isolation test: a user with leftover MINERU_LOCAL_API_KEY
    flipping to ecanai must NOT pass validation. Otherwise the local
    credential would silently leak into the ecanai runtime."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "ecanai",
        "MINERU_LOCAL_API_KEY": "user-local-key",
        # No MINERU_API_TOKEN
    })
    assert errors, "ecanai mode must NOT accept MINERU_LOCAL_API_KEY as the active token"


def test_docling_ecanai_validates_both_endpoint_and_api_key():
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "docling:default",
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_ECANAI_ENDPOINT": ECANAI_PARSER_BASE_URL,
        # DOCLING_API_KEY intentionally empty
    })
    assert errors
    assert any("DOCLING_API_KEY" in e and "API Key" in e for e in errors)


def test_docling_ecanai_rejects_missing_endpoint_even_with_key():
    """DOCLING_ECANAI_ENDPOINT is always required in ecanai mode —
    a token without the canonical URL still leaves LightRAG with a
    default-base-url fallback that the proxy cannot reach."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "docling:default",
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_API_KEY": "live-account-key",
        # DOCLING_ECANAI_ENDPOINT intentionally empty
    })
    assert errors
    assert any("DOCLING_ECANAI_ENDPOINT" in e for e in errors)


def test_mineru_ecanai_does_not_require_mineru_local_endpoint():
    """A common foot-gun: someone migrating from local to ecanai
    leaves the old ``MINERU_LOCAL_ENDPOINT`` value in .env. The
    validator must not treat this as a config error in ecanai mode."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "ecanai",
        "MINERU_API_TOKEN": "live-account-key",
        "MINERU_LOCAL_ENDPOINT": "https://user-mineru.example.com/api",  # leftover
    })
    assert errors == []


def test_routing_referencing_no_parser_engine_is_a_noop():
    """A ``LIGHTRAG_PARSER`` rule with only native rules means
    neither mineru nor docling validation runs."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "native:default",
        # No MINERU_API_MODE / DOCLING_PROVIDER needed
    })
    assert errors == []


def test_invalid_mineru_mode_value_is_rejected():
    """A typo in the mode value (e.g. 'ECANAI' vs 'ecanai' is OK
    because the resolver normalizes, but 'made-up-mode' is not).
    The validator must surface this as a hard error instead of
    silently defaulting to ecanai."""
    errors = validate_parser_endpoints({
        LIGHTRAG_PARSER_KEY: "mineru:default",
        "MINERU_API_MODE": "made-up-mode",
    })
    assert errors
    assert any("MINERU_API_MODE" in e and "official / local / ecanai" in e for e in errors)
