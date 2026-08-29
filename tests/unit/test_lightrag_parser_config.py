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
    assert [option["value"] for option in language_field["options"]] == [
        "ch",
        "ch_server",
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
                "MINERU_API_TOKEN": "local-secret",
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


def test_validate_docling_requires_endpoint_and_api_key():
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
                "DOCLING_API_KEY": "secret",
            }
        )
        == []
    )
