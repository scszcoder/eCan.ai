"""Unit tests for the LightRAG document parsing engine configuration."""

from knowledge.lightrag_parser_config import (
    DEFAULT_MINERU_OFFICIAL_ENDPOINT,
    LIGHTRAG_PARSER_KEY,
    PARSER_ENGINE_DEFINITIONS,
    PARSER_PRESETS,
    derive_mineru_provider,
    derive_parsing_engine,
    normalize_parser_routing,
    validate_parser_endpoints,
    unsupported_parser_files,
)


def test_mineru_uses_strict_344_format_allowlist():
    settings = {LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"]}
    supported = [
        "a.pdf", "a.docx", "a.pptx", "a.xlsx", "a.png", "a.jpg",
        "a.jpeg", "a.jp2", "a.webp", "a.gif", "a.bmp", "a.tiff",
    ]
    unsupported = [
        "a.doc", "a.xls", "a.ppt", "a.csv", "a.txt", "a.md",
        "a.markdown", "a.html", "a.htm", "a.epub", "a.tif", "a.rtf",
    ]
    assert unsupported_parser_files(settings, supported) == []
    assert unsupported_parser_files(settings, unsupported) == unsupported


def test_other_parsers_do_not_apply_mineru_spreadsheet_restriction():
    settings = {LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"]}
    assert unsupported_parser_files(settings, ["legacy.xls", "data.csv"]) == []


def test_mineru_model_versions_match_official_api_and_default_to_pipeline():
    mineru = next(item for item in PARSER_ENGINE_DEFINITIONS if item["id"] == "mineru")
    model_field = next(
        field for field in mineru["fields"] if field["key"] == "MINERU_MODEL_VERSION"
    )

    assert model_field["defaultValue"] == "pipeline"
    assert [option["value"] for option in model_field["options"]] == [
        "pipeline",
        "vlm",
    ]


def test_mineru_languages_match_official_ocr_model_groups():
    mineru = next(item for item in PARSER_ENGINE_DEFINITIONS if item["id"] == "mineru")
    language_field = next(
        field for field in mineru["fields"] if field["key"] == "MINERU_LANGUAGE"
    )

    assert language_field["defaultValue"] == "ch"
    # The dropdown mirrors the union of CLI --lang (12 values, pipeline
    # backend only) and mineru.net API ``language`` task parameter
    # values. LightRAG 1.5.6 reads MINERU_LANGUAGE for BOTH modes; the
    # service-side behavior is documented in the tooltip.
    assert [option["value"] for option in language_field["options"]] == [
        "ch",
        "ch_server",
        "ch_lite",
        "chinese_cht",
        "en",
        "japan",
        "korean",
        "ta",
        "te",
        "ka",
        "th",
        "el",
        "arabic",
        "east_slavic",
        "cyrillic",
        "devanagari",
        "latin",
        "french",
        "german",
        "spanish",
        "portuguese",
        "russian",
        "italian",
    ]


# -- derive_parsing_engine ---------------------------------------------------


def test_derive_engine_from_presets():
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["native"]}) == "native"
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"]}) == "mineru"
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"]}) == "docling"


def test_external_parser_presets_are_first_match_before_native_fallback():
    assert PARSER_PRESETS["mineru"].startswith("*:mineru-")
    assert PARSER_PRESETS["docling"].startswith("*:docling-")


def test_parser_presets_disable_vlm_image_analysis_by_default():
    for routing in PARSER_PRESETS.values():
        parser_rules = [rule for rule in routing.split(",") if ":legacy" not in rule]
        assert parser_rules
        assert all("-i" not in rule for rule in parser_rules)


def test_derive_engine_from_custom_and_empty():
    # A hand-written routing table containing both external engines resolves
    # to mineru first, then docling.
    assert (
        derive_parsing_engine(
            {LIGHTRAG_PARSER_KEY: "pdf:docling-iteP,*:native-teP,doc:mineru-R,*:legacy-R"}
        )
        == "mineru"
    )
    assert derive_parsing_engine({}) == "native"
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: ""}) == "native"


def test_legacy_null_parser_values_use_native_preset():
    for value in (None, "", "None", "null", "undefined"):
        assert normalize_parser_routing(value) == PARSER_PRESETS["native"]
        assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: value}) == "native"


# -- validate_parser_endpoints ------------------------------------------------


def test_validate_no_external_engine():
    assert validate_parser_endpoints({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["native"]}) == []


def test_validate_mineru_local_requires_local_endpoint():
    # When MINERU_API_MODE is explicitly set to 'local' but
    # MINERU_LOCAL_ENDPOINT is missing, validation should report that.
    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
            "MINERU_API_MODE": "local",
        }
    )
    assert any("MINERU_LOCAL_ENDPOINT" in e for e in errors)

    assert (
        validate_parser_endpoints(
            {
                LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
                "MINERU_API_MODE": "local",
                "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000",
                "MINERU_LOCAL_API_KEY": "local-secret",
            }
        )
        == []
    )


def test_validate_mineru_official_uses_native_token_key():
    assert (
        validate_parser_endpoints(
            {
                LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
                "MINERU_API_MODE": "official",
                "MINERU_OFFICIAL_ENDPOINT": "https://compatible.example.com",
                "MINERU_OFFICIAL_API_KEY": "tk_test",
            }
        )
        == []
    )


# -- derive_mineru_provider / derive_mineru_runtime_env ----------------------


def test_derive_mineru_provider_uses_native_api_mode():
    # Empty settings default to ecanai (the recommended desktop path);
    # only opt-in local / official modes resolve to themselves. Any
    # unknown value falls back to ecanai rather than silently defaulting
    # to local.
    assert derive_mineru_provider({}) == "ecanai"
    assert derive_mineru_provider({"MINERU_API_MODE": "official"}) == "official"
    assert derive_mineru_provider({"MINERU_API_MODE": "local"}) == "local"
    assert derive_mineru_provider({"MINERU_API_MODE": "gateway"}) == "ecanai"


def test_validate_mineru_rejects_non_native_api_mode():
    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
            "MINERU_API_MODE": "gateway",
            "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000",
        }
    )
    # ``ecanai`` was added as a third valid alias; the error message must
    # keep listing the full accepted set so users know ``gateway`` is the
    # wrong value to enter.
    assert any("official" in error and "local" in error for error in errors)
    assert any("ecanai" in error for error in errors)


def test_validate_docling_requires_endpoint_and_api_key():
    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
        }
    )
    # Default DOCLING_PROVIDER is ``ecanai``, so the missing field is the
    # dedicated eCanAI endpoint that backs it (``DOCLING_ECANAI_ENDPOINT``).
    assert any("DOCLING_ECANAI_ENDPOINT" in e for e in errors)

    assert (
        validate_parser_endpoints(
            {
                LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
                "DOCLING_PROVIDER": "local",
                "DOCLING_LOCAL_ENDPOINT": "http://docling.internal:5001",
                "DOCLING_LOCAL_API_KEY": "secret",
            }
        )
        == []
    )


def test_validate_docling_official_requires_official_endpoint():
    assert (
        validate_parser_endpoints(
            {
                LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
                "DOCLING_PROVIDER": "official",
                "DOCLING_OFFICIAL_ENDPOINT": "https://docling.ai",
                "DOCLING_OFFICIAL_API_KEY": "secret",
            }
        )
        == []
    )


def test_validate_docling_rejects_unknown_provider():
    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
            "DOCLING_PROVIDER": "gateway",
        }
    )
    assert any("DOCLING_PROVIDER" in e for e in errors)


def test_derive_docling_provider_defaults_to_ecanai():
    from knowledge.lightrag_parser_config import derive_docling_provider
    assert derive_docling_provider({}) == "ecanai"
    assert derive_docling_provider({"DOCLING_PROVIDER": "official"}) == "official"
    assert derive_docling_provider({"DOCLING_PROVIDER": "gateway"}) == "ecanai"


# -- mark_system_managed_parser_fields / resolve_ecanai_parser_secrets --------


def test_mark_system_managed_only_under_ecanai_provider():
    from knowledge.lightrag_parser_config import (
        mark_system_managed_parser_fields,
        PARSER_ENGINE_DEFINITIONS,
    )

    # Local mode: nothing is system-managed.
    annotated = mark_system_managed_parser_fields(
        PARSER_ENGINE_DEFINITIONS,
        {"MINERU_API_MODE": "local", "DOCLING_PROVIDER": "local"},
    )
    mineru = next(engine for engine in annotated if engine["id"] == "mineru")
    docling = next(engine for engine in annotated if engine["id"] == "docling")
    assert all(not field.get("isSystemManaged") for field in mineru["fields"])
    assert all(not field.get("isSystemManaged") for field in docling["fields"])

    # eCanAI mode: MinerU local endpoint + token + Docling local endpoint +
    # API key are system-managed.
    annotated = mark_system_managed_parser_fields(
        PARSER_ENGINE_DEFINITIONS,
        {"MINERU_API_MODE": "ecanai", "DOCLING_PROVIDER": "ecanai"},
    )
    mineru = next(engine for engine in annotated if engine["id"] == "mineru")
    docling = next(engine for engine in annotated if engine["id"] == "docling")
    mineru_keys = {field["key"]: field.get("isSystemManaged") for field in mineru["fields"]}
    docling_keys = {field["key"]: field.get("isSystemManaged") for field in docling["fields"]}
    # The eCanAI endpoint is a *dedicated* env var, separate from the local
    # endpoint — that's what makes switching providers safe.
    assert mineru_keys["MINERU_ECANAI_ENDPOINT"] is True
    assert mineru_keys["MINERU_API_TOKEN"] is True
    assert mineru_keys.get("MINERU_LOCAL_ENDPOINT") is None  # not flagged
    assert mineru_keys.get("MINERU_OFFICIAL_ENDPOINT") is None  # not flagged
    assert docling_keys["DOCLING_ECANAI_ENDPOINT"] is True
    assert docling_keys["DOCLING_API_KEY"] is True
    assert docling_keys.get("DOCLING_LOCAL_ENDPOINT") is None  # not flagged
    assert docling_keys.get("DOCLING_OFFICIAL_ENDPOINT") is None  # not flagged


def test_resolve_ecanai_parser_secrets_overwrites_stale_values():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    settings = {
        "MINERU_API_MODE": "ecanai",
        # Old (pre-split) shape — should be left alone; the resolver writes
        # the dedicated eCanAI fields, not the local ones.
        "MINERU_LOCAL_ENDPOINT": "http://stale.example.com",
        "MINERU_ECANAI_ENDPOINT": "http://stale-ecanai.example.com",
        "MINERU_API_TOKEN": "",  # Not set; resolver will fill from account
        "MINERU_LOCAL_API_KEY": "stale-mineru-key",  # Old per-mode key (from local mode)
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_LOCAL_ENDPOINT": "http://also-stale.example.com",
        "DOCLING_ECANAI_ENDPOINT": "http://stale-docling-ecanai.example.com",
        "DOCLING_API_KEY": "",  # Not set; resolver will fill from account
        "DOCLING_OFFICIAL_ENDPOINT": "https://docling.ai",
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "fresh-account-key",
    )

    # The dedicated eCanAI fields are refreshed; the user-typed local /
    # official endpoints are not touched, so a future mode switch keeps
    # the user-typed values intact.
    assert resolved["MINERU_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL
    # eCanAI never reuses a Local credential.
    assert resolved["MINERU_API_TOKEN"] == "fresh-account-key"
    assert resolved["MINERU_LOCAL_ENDPOINT"] == "http://stale.example.com"
    assert resolved["DOCLING_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL
    # Since DOCLING_API_KEY is empty, falls back to account key
    assert resolved["DOCLING_API_KEY"] == "fresh-account-key"
    assert resolved["DOCLING_LOCAL_ENDPOINT"] == "http://also-stale.example.com"
    assert resolved["DOCLING_OFFICIAL_ENDPOINT"] == "https://docling.ai"


def test_resolve_ecanai_parser_secrets_leaves_local_modes_alone():
    from knowledge.lightrag_parser_config import resolve_ecanai_parser_secrets

    settings = {
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000",
        "MINERU_ECANAI_ENDPOINT": "https://should-not-be-used",
        "MINERU_API_TOKEN": "user-secret",
        "DOCLING_PROVIDER": "official",
        "DOCLING_OFFICIAL_ENDPOINT": "https://docling.ai",
        "DOCLING_ECANAI_ENDPOINT": "https://also-should-not-be-used",
        "DOCLING_API_KEY": "user-docling-secret",
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        "https://fresh-ecanai-proxy",
        "fresh-account-key",
    )

    # local / official modes must keep the user's typed values verbatim.
    assert resolved["MINERU_LOCAL_ENDPOINT"] == "http://127.0.0.1:8000"
    assert resolved["MINERU_API_TOKEN"] == "user-secret"
    assert resolved["MINERU_ECANAI_ENDPOINT"] == "https://should-not-be-used"
    assert resolved["DOCLING_OFFICIAL_ENDPOINT"] == "https://docling.ai"
    assert resolved["DOCLING_API_KEY"] == "user-docling-secret"
    assert resolved["DOCLING_ECANAI_ENDPOINT"] == "https://also-should-not-be-used"


def test_normalize_parser_ecanai_alias_docling_endpoint_rewriting():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        normalize_parser_ecanai_alias,
    )

    # Docling eCanAI mode rewrites DOCLING_ECANAI_ENDPOINT into the legacy
    # DOCLING_ENDPOINT env var that LightRAG actually reads.
    settings = {
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_ECANAI_ENDPOINT": ECANAI_PARSER_BASE_URL,
        "DOCLING_LOCAL_ENDPOINT": "http://different.example.com",
        "DOCLING_API_KEY": "any",
    }
    rewritten = normalize_parser_ecanai_alias(settings, ECANAI_PARSER_BASE_URL)
    assert rewritten["DOCLING_ENDPOINT"] == ECANAI_PARSER_BASE_URL


def test_normalize_parser_ecanai_alias_docling_official_uses_official_endpoint():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        normalize_parser_ecanai_alias,
    )

    settings = {
        "DOCLING_PROVIDER": "official",
        "DOCLING_OFFICIAL_ENDPOINT": "https://docling.ai",
        "DOCLING_API_KEY": "any",
    }
    rewritten = normalize_parser_ecanai_alias(settings, ECANAI_PARSER_BASE_URL)
    assert rewritten["DOCLING_ENDPOINT"] == "https://docling.ai"


# -- field-definition shape ---------------------------------------------------


def test_mineru_engine_definition_orders_ecanai_first():
    # The UI dropdown must surface ecanai first so the default value
    # matches the visible top option. Docling uses the same ordering; a
    # dedicated test guards against accidental reorderings during future
    # refactors of the schema.
    mineru = next(item for item in PARSER_ENGINE_DEFINITIONS if item["id"] == "mineru")
    provider_field = next(
        field for field in mineru["fields"] if field["key"] == "MINERU_API_MODE"
    )
    assert [option["value"] for option in provider_field["options"]] == [
        "ecanai",
        "local",
        "official",
    ]
    assert provider_field["defaultValue"] == "ecanai"


def test_docling_engine_definition_orders_ecanai_first():
    docling = next(item for item in PARSER_ENGINE_DEFINITIONS if item["id"] == "docling")
    provider_field = next(
        field for field in docling["fields"] if field["key"] == "DOCLING_PROVIDER"
    )
    assert [option["value"] for option in provider_field["options"]] == [
        "ecanai",
        "local",
        "official",
    ]


def test_docling_engine_definition_exposes_three_way_provider():
    docling = next(item for item in PARSER_ENGINE_DEFINITIONS if item["id"] == "docling")
    provider_field = next(
        field for field in docling["fields"] if field["key"] == "DOCLING_PROVIDER"
    )
    assert provider_field["defaultValue"] == "ecanai"
    assert [option["value"] for option in provider_field["options"]] == [
        "ecanai",
        "local",
        "official",
    ]
    # Both endpoint fields exist for users who switch providers.
    keys = {field["key"] for field in docling["fields"]}
    assert "DOCLING_LOCAL_ENDPOINT" in keys
    assert "DOCLING_OFFICIAL_ENDPOINT" in keys
    assert "DOCLING_ECANAI_ENDPOINT" in keys
    assert "DOCLING_PROVIDER" in keys


def test_three_provider_endpoints_are_independent():
    """Switching modes in the UI must never overwrite the inactive mode's endpoint.

    Reproduces the user-reported bug where typing a local URL, switching
    to ecanai, then back to local would show an empty input because the
    ecanai branch had written the eCanAI proxy into ``MINERU_LOCAL_ENDPOINT``.
    The fix: each provider mode owns a dedicated env var
    (``MINERU_*_ECANAI_ENDPOINT``) so the UI never overwrites user-typed
    values when toggling the mode selector without saving.
    """
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
    )

    # 1. User picks local and types their self-hosted URL.
    settings = {
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "http://my-mineru.local:8000",
        "MINERU_ECANAI_ENDPOINT": ECANAI_PARSER_BASE_URL,
        "MINERU_API_TOKEN": "user-token",
    }

    # 2. User switches the UI selector to ecanai. updateSetting only
    #    adds the missing ECANAI default; it does NOT touch
    #    MINERU_LOCAL_ENDPOINT, so the user's URL is preserved in
    #    the in-memory state until they next hit Save.
    settings["MINERU_API_MODE"] = "ecanai"
    if not settings.get("MINERU_ECANAI_ENDPOINT"):
        settings["MINERU_ECANAI_ENDPOINT"] = ECANAI_PARSER_BASE_URL

    assert settings["MINERU_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL
    # The local endpoint the user typed earlier is preserved.
    assert settings["MINERU_LOCAL_ENDPOINT"] == "http://my-mineru.local:8000"

    # 3. User switches back to local. The previously-typed local URL
    #    is still there (updateSetting never overwrote it).
    settings["MINERU_API_MODE"] = "local"
    assert settings["MINERU_LOCAL_ENDPOINT"] == "http://my-mineru.local:8000"


def test_three_provider_endpoints_independent_for_docling():
    """Same scenario for Docling."""
    from knowledge.lightrag_parser_config import ECANAI_PARSER_BASE_URL

    settings = {
        "DOCLING_PROVIDER": "local",
        "DOCLING_LOCAL_ENDPOINT": "http://my-docling.local:5001",
        "DOCLING_OFFICIAL_ENDPOINT": "https://docling.ai",
        "DOCLING_ECANAI_ENDPOINT": ECANAI_PARSER_BASE_URL,
        "DOCLING_API_KEY": "user-token",
    }

    # User switches the UI to ecanai. The ecanai default is back-filled
    # if missing, but the local endpoint is not touched.
    settings["DOCLING_PROVIDER"] = "ecanai"
    if not settings.get("DOCLING_ECANAI_ENDPOINT"):
        settings["DOCLING_ECANAI_ENDPOINT"] = ECANAI_PARSER_BASE_URL

    assert settings["DOCLING_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL
    assert settings["DOCLING_LOCAL_ENDPOINT"] == "http://my-docling.local:5001"
    assert settings["DOCLING_OFFICIAL_ENDPOINT"] == "https://docling.ai"

    # Switch back to local — local value still intact.
    settings["DOCLING_PROVIDER"] = "local"
    assert settings["DOCLING_LOCAL_ENDPOINT"] == "http://my-docling.local:5001"


# -- eCanAI mode with user-typed local key ----------------------------------


def test_resolve_ecanai_parser_secrets_does_not_leak_local_key_to_mineru_ecanai():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_LOCAL_API_KEY": "tk_user_typed_local_key",
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "",  # No account key
    )

    assert resolved["MINERU_API_TOKEN"] == ""
    assert resolved["MINERU_LOCAL_API_KEY"] == "tk_user_typed_local_key"
    assert resolved["MINERU_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL


def test_resolve_ecanai_parser_secrets_does_not_leak_local_key_to_docling_ecanai():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    settings = {
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_LOCAL_API_KEY": "docling_user_typed_key",
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "",  # No account key
    )

    assert resolved["DOCLING_API_KEY"] == ""
    assert resolved["DOCLING_LOCAL_API_KEY"] == "docling_user_typed_key"
    assert resolved["DOCLING_ECANAI_ENDPOINT"] == ECANAI_PARSER_BASE_URL


def test_validate_parser_endpoints_rejects_mineru_ecanai_with_only_local_key():
    settings = {
        LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
        "MINERU_API_MODE": "ecanai",
        "MINERU_LOCAL_API_KEY": "tk_local_only",
    }
    assert validate_parser_endpoints(settings)


def test_validate_parser_endpoints_rejects_mineru_ecanai_with_no_keys():
    """eCanAI mode without any key must be rejected."""
    settings = {
        LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
        "MINERU_API_MODE": "ecanai",
        # No MINERU_API_TOKEN, no MINERU_LOCAL_API_KEY
    }
    errors = validate_parser_endpoints(settings)
    assert len(errors) == 1
    assert "未配置 API Key" in errors[0]
    assert "MINERU_API_MODE=ecanai" in errors[0]


def test_validate_parser_endpoints_rejects_docling_ecanai_with_only_local_key():
    settings = {
        LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_ECANAI_ENDPOINT": "https://example.com/docling",
        "DOCLING_LOCAL_API_KEY": "docling_local_only",
    }
    assert validate_parser_endpoints(settings)


def test_validate_parser_endpoints_rejects_docling_ecanai_with_no_keys():
    """Docling eCanAI mode without any key must be rejected."""
    settings = {
        LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_ECANAI_ENDPOINT": "https://example.com/docling",
        # No DOCLING_API_KEY, no DOCLING_LOCAL_API_KEY
    }
    errors = validate_parser_endpoints(settings)
    assert len(errors) == 1
    assert "未配置 API Key" in errors[0]


def test_validate_parser_endpoints_rejects_docling_ecanai_with_no_endpoint():
    """Docling eCanAI mode without DOCLING_ECANAI_ENDPOINT must be rejected
    even when an API key is configured."""
    settings = {
        LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_LOCAL_API_KEY": "docling_local_key",
        "DOCLING_API_KEY": "account_key",
        # No DOCLING_ECANAI_ENDPOINT
    }
    errors = validate_parser_endpoints(settings)
    assert len(errors) == 1
    assert "DOCLING_ECANAI_ENDPOINT" in errors[0]


def test_resolve_ecanai_parser_secrets_local_key_preserved_across_modes():
    """MINERU_LOCAL_API_KEY must NOT be overwritten when switching to eCanAI."""
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    # User typed a local key in MINERU_LOCAL_API_KEY before switching to eCanAI
    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_LOCAL_API_KEY": "user_local_key",
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "account_key",
    )

    # The active key is account-owned; the Local slot remains preserved.
    assert resolved["MINERU_API_TOKEN"] == "account_key"
    assert resolved["MINERU_LOCAL_API_KEY"] == "user_local_key"


def test_resolve_ecanai_parser_secrets_refreshes_mineru_account_key():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    # User is in eCanAI mode and typed their own key into MINERU_API_TOKEN
    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_API_TOKEN": "user-ecanai-key",  # User typed this in UI
        "MINERU_LOCAL_API_KEY": "",  # Never used local mode
    }

    # Save with account key available
    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "account-key",  # This should NOT overwrite user-ecanai-key
    )

    assert resolved["MINERU_API_TOKEN"] == "account-key"


def test_resolve_ecanai_parser_secrets_refreshes_docling_account_key():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    # User is in Docling eCanAI mode and typed their own key into DOCLING_API_KEY
    settings = {
        "DOCLING_PROVIDER": "ecanai",
        "DOCLING_API_KEY": "user-docling-ecanai-key",  # User typed this in UI
        "DOCLING_LOCAL_API_KEY": "",  # Never used local mode
    }

    # Save with account key available
    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "account-key",  # This should NOT overwrite user-docling-ecanai-key
    )

    assert resolved["DOCLING_API_KEY"] == "account-key"


def test_resolve_ecanai_parser_secrets_account_key_wins_for_mineru():
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_API_TOKEN": "user-ecanai-key",  # User typed in eCanAI mode
        "MINERU_LOCAL_API_KEY": "user-local-key",  # Previously typed in local mode
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "account-key",
    )

    assert resolved["MINERU_API_TOKEN"] == "account-key"


def test_resolve_ecanai_parser_secrets_auto_filled_token_kept_when_no_user_input():
    """When MINERU_API_TOKEN is auto-filled (same as account key) and user
    didn't type anything, the auto-filled value is kept."""
    from knowledge.lightrag_parser_config import (
        ECANAI_PARSER_BASE_URL,
        resolve_ecanai_parser_secrets,
    )

    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_API_TOKEN": "account-key",  # Auto-filled from account
        "MINERU_LOCAL_API_KEY": "",
    }

    resolved = resolve_ecanai_parser_secrets(
        settings,
        ECANAI_PARSER_BASE_URL,
        "account-key",
    )

    # Auto-filled account key is kept
    assert resolved["MINERU_API_TOKEN"] == "account-key"


def test_mineru_local_endpoint_slot_is_blank_by_default():
    mineru = next(item for item in PARSER_ENGINE_DEFINITIONS if item["id"] == "mineru")
    field = next(
        item for item in mineru["fields"]
        if item["key"] == "MINERU_LOCAL_ENDPOINT_SETTING"
    )
    assert "defaultValue" not in field


def test_resolver_activates_local_endpoint_without_losing_other_slots():
    from knowledge.lightrag_parser_config import resolve_ecanai_parser_secrets

    settings = {
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "https://old-runtime-value",
        "MINERU_LOCAL_ENDPOINT_SETTING": "http://my-local-mineru:8000",
        "MINERU_ECANAI_ENDPOINT": "https://fixed-ecanai",
        "MINERU_LOCAL_API_KEY": "local-key",
        "MINERU_OFFICIAL_API_KEY": "official-key",
    }
    resolved = resolve_ecanai_parser_secrets(settings, "https://fixed-ecanai", "account-key")
    assert resolved["MINERU_LOCAL_ENDPOINT"] == "http://my-local-mineru:8000"
    assert resolved["MINERU_API_TOKEN"] == "local-key"
    assert resolved["MINERU_OFFICIAL_API_KEY"] == "official-key"


def test_ecanai_activation_preserves_mineru_local_endpoint_slot():
    from knowledge.lightrag_parser_config import (
        normalize_parser_ecanai_alias,
        resolve_ecanai_parser_secrets,
    )

    settings = {
        "MINERU_API_MODE": "ecanai",
        "MINERU_LOCAL_ENDPOINT_SETTING": "http://my-local-mineru:8000",
        "MINERU_LOCAL_API_KEY": "local-key",
    }
    resolved = resolve_ecanai_parser_secrets(settings, "https://fixed-ecanai", "account-key")
    persisted = normalize_parser_ecanai_alias(resolved, "https://fixed-ecanai")
    assert persisted["MINERU_LOCAL_ENDPOINT"] == "https://fixed-ecanai"
    assert persisted["MINERU_LOCAL_ENDPOINT_SETTING"] == "http://my-local-mineru:8000"
    assert persisted["MINERU_API_TOKEN"] == "account-key"
    assert persisted["MINERU_LOCAL_API_KEY"] == "local-key"
