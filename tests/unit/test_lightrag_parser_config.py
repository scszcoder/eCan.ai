"""Unit tests for the LightRAG document parsing engine configuration."""

from knowledge.lightrag_parser_config import (
    DEFAULT_MINERU_OFFICIAL_ENDPOINT,
    LIGHTRAG_PARSER_KEY,
    PARSER_PRESETS,
    derive_mineru_provider,
    derive_parsing_engine,
    normalize_parser_routing,
    validate_parser_endpoints,
)


# -- derive_parsing_engine ---------------------------------------------------


def test_derive_engine_from_presets():
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["native"]}) == "native"
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"]}) == "mineru"
    assert derive_parsing_engine({LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"]}) == "docling"


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
    errors = validate_parser_endpoints(
        {LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"]}
    )
    assert any("MINERU_LOCAL_ENDPOINT" in e for e in errors)

    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
            "MINERU_API_MODE": "official",
            "MINERU_OFFICIAL_ENDPOINT": DEFAULT_MINERU_OFFICIAL_ENDPOINT,
        }
    )
    assert any("MINERU_API_TOKEN" in e for e in errors)

    assert (
        validate_parser_endpoints(
            {
                LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
                "MINERU_API_MODE": "local",
                "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000",
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
                "MINERU_API_TOKEN": "tk_test",
            }
        )
        == []
    )


# -- derive_mineru_provider / derive_mineru_runtime_env ----------------------


def test_derive_mineru_provider_uses_native_api_mode():
    assert derive_mineru_provider({}) == "local"
    assert derive_mineru_provider({"MINERU_API_MODE": "official"}) == "official"
    assert derive_mineru_provider({"MINERU_API_MODE": "gateway"}) == "local"


def test_validate_mineru_rejects_non_native_api_mode():
    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["mineru"],
            "MINERU_API_MODE": "gateway",
            "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:8000",
        }
    )
    assert any("official 或 local" in error for error in errors)


def test_validate_docling_requires_native_endpoint():
    errors = validate_parser_endpoints(
        {
            LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
        }
    )
    assert any("DOCLING_ENDPOINT" in e for e in errors)

    assert (
        validate_parser_endpoints(
            {
                LIGHTRAG_PARSER_KEY: PARSER_PRESETS["docling"],
                "DOCLING_ENDPOINT": "http://docling.internal:5001",
            }
        )
        == []
    )
