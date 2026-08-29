"""
LightRAG Document Parsing Engine Configuration

Canonical home for the document parsing engine settings exposed in the
LightRAG settings UI. LightRAG 1.5+ routes each ingested file to a
content-extraction engine through the ``LIGHTRAG_PARSER`` rule table
(rules are evaluated left to right, the first usable rule wins):

    - ``native``   : built-in structured extractor (docx / md / textpack),
                     fully local, no external service required.
    - ``mineru``   : external MinerU service (PDF / Office / images), using
                     LightRAG's native ``official`` / ``local`` API modes and
                     environment variable names without translation.
    - ``docling``  : external docling-serve service (PDF / Office / images),
                     configured with LightRAG's native ``DOCLING_ENDPOINT``.

There is no separate "engine" env var: the engine selection is UI-only and is
derived from the persisted ``LIGHTRAG_PARSER`` value (never written to
lightrag.env). Switching the engine in the UI writes the matching upstream
preset routing table (docs/FileProcessingPipeline.md §1.3) into
``LIGHTRAG_PARSER``.

IMPORTANT startup constraint (verified against LightRAG
``lightrag/parser/routing.py`` / ``registry.py``): if ``LIGHTRAG_PARSER``
contains a rule referencing ``mineru`` / ``docling``, the corresponding
endpoint MUST be configured or the server refuses to start.

MinerU fields use the exact names consumed by LightRAG. A compatible custom
endpoint changes only the appropriate endpoint value; it does not introduce
a new environment-variable name.

Docling likewise keeps ``DOCLING_ENDPOINT`` unchanged; a custom deployment
changes only that variable's value.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Canonical variable name
# ---------------------------------------------------------------------------

LIGHTRAG_PARSER_KEY = "LIGHTRAG_PARSER"

# Default endpoint for the official MinerU provider (pre-filled in the UI).
DEFAULT_MINERU_OFFICIAL_ENDPOINT = "https://mineru.net"
DEFAULT_MINERU_LOCAL_ENDPOINT = "http://127.0.0.1:8000"
DEFAULT_DOCLING_ENDPOINT = "http://localhost:5001"

# Every env var the parsing engines touch, used to return the current
# values to the UI without leaking unrelated settings.
PARSER_SETTINGS_KEYS: Tuple[str, ...] = (
    LIGHTRAG_PARSER_KEY,
    "MINERU_API_MODE",
    "MINERU_OFFICIAL_ENDPOINT",
    "MINERU_LOCAL_ENDPOINT",
    "MINERU_API_TOKEN",
    "MINERU_MODEL_VERSION",
    "MINERU_IS_OCR",
    "MINERU_LANGUAGE",
    "MINERU_ENABLE_TABLE",
    "MINERU_ENABLE_FORMULA",
    "MINERU_LOCAL_BACKEND",
    "MINERU_LOCAL_PARSE_METHOD",
    "MINERU_LOCAL_IMAGE_ANALYSIS",
    "MINERU_ADDITIONAL_SUFFIXES",
    "MAX_PARALLEL_PARSE_MINERU",
    "DOCLING_ENDPOINT",
    "DOCLING_ADDITIONAL_SUFFIXES",
    "MAX_PARALLEL_PARSE_DOCLING",
)

# ---------------------------------------------------------------------------
# Preset routing tables (canonical upstream rules)
# ---------------------------------------------------------------------------

PARSER_PRESETS: Dict[str, str] = {
    # Recommended starting behavior, no external services (§1.2)
    "native": "*:native-teP,*:legacy-R",
    # Multimodal: native handles docx/md/textpack, MinerU picks up
    # pdf/office/images because native is skipped for those suffixes (§1.3)
    "mineru": "*:native-iteP,*:mineru-iteP,*:legacy-R",
    # Same shape with Docling as the external engine
    "docling": "*:native-iteP,*:docling-iteP,*:legacy-R",
}

PARSER_ENGINE_IDS = tuple(PARSER_PRESETS.keys())


def normalize_parser_routing(value: Any) -> str:
    """Return a valid routing value for legacy empty/null sentinels.

    Older settings flows serialized a missing JavaScript/Python value as the
    literal string ``None``.  LightRAG treats every non-empty string as a rule
    table and refuses to start when it encounters that sentinel.
    """
    routing = str(value or "").strip()
    if not routing or routing.lower() in {"none", "null", "undefined"}:
        return PARSER_PRESETS["native"]
    return routing

# ---------------------------------------------------------------------------
# Per-engine endpoint requirements (mirrors LightRAG registry.py closures)
# ---------------------------------------------------------------------------

# Required variables are the exact names consumed by LightRAG.
_MINERU_MODE_REQUIREMENTS = {
    "official": ("MINERU_API_TOKEN",),
    "local": ("MINERU_LOCAL_ENDPOINT",),
}


# ---------------------------------------------------------------------------
# Field definitions served to the UI (the backend is the source of truth for
# variable names, defaults, options and endpoint requirements).
# ---------------------------------------------------------------------------

PARSER_ENGINE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "native",
        "name": "providers.parserNative",
        "description": "LightRAG built-in native parser (default, no external service required)",
        "fields": [
            {
                "key": LIGHTRAG_PARSER_KEY,
                "label": "fields.parserRouting",
                "type": "textarea",
                "defaultValue": PARSER_PRESETS["native"],
                "tooltip": "tooltips.parserRouting",
            },
        ],
    },
    {
        "id": "mineru",
        "name": "providers.parserMineru",
        "description": "MinerU multimodal parser service (PDF / Office / images)",
        "fields": [
            {
                "key": "MINERU_API_MODE",
                "label": "fields.mineruProvider",
                "type": "select",
                "defaultValue": "local",
                "tooltip": "tooltips.mineruProvider",
                "options": [
                    {"value": "local", "label": "fields.providerLocal"},
                    {"value": "official", "label": "fields.providerOfficial"},
                ],
            },
            {
                "key": "MINERU_OFFICIAL_ENDPOINT",
                "label": "fields.mineruEndpoint",
                "type": "text",
                "defaultValue": DEFAULT_MINERU_OFFICIAL_ENDPOINT,
                "placeholder": DEFAULT_MINERU_OFFICIAL_ENDPOINT,
                "tooltip": "tooltips.mineruEndpoint",
            },
            {
                "key": "MINERU_LOCAL_ENDPOINT",
                "label": "fields.mineruLocalEndpoint",
                "type": "text",
                "defaultValue": DEFAULT_MINERU_LOCAL_ENDPOINT,
                "placeholder": DEFAULT_MINERU_LOCAL_ENDPOINT,
                "tooltip": "tooltips.mineruLocalEndpoint",
            },
            {
                "key": "MINERU_API_TOKEN",
                "label": "fields.mineruApiKey",
                "type": "password",
                "tooltip": "tooltips.mineruApiKey",
            },
            {
                "key": "MINERU_MODEL_VERSION",
                "label": "fields.mineruModelVersion",
                "type": "select",
                "defaultValue": "vlm",
                "tooltip": "tooltips.mineruModelVersion",
                "options": [
                    {"value": "pipeline", "label": "fields.mineruModelPipeline"},
                    {"value": "vlm", "label": "fields.mineruModelVlm"},
                ],
            },
            {
                "key": "MINERU_IS_OCR",
                "label": "fields.mineruIsOcr",
                "type": "boolean",
                "defaultValue": "false",
                "tooltip": "tooltips.mineruIsOcr",
            },
            {
                "key": "MINERU_LANGUAGE",
                "label": "fields.mineruLanguage",
                "type": "select",
                "defaultValue": "ch",
                "tooltip": "tooltips.mineruLanguage",
                "options": [
                    {"value": "ch", "label": "fields.languageChinese"},
                    {"value": "en", "label": "fields.languageEnglish"},
                ],
            },
            {
                "key": "MINERU_ENABLE_TABLE",
                "label": "fields.mineruEnableTable",
                "type": "boolean",
                "defaultValue": "true",
                "tooltip": "tooltips.mineruEnableTable",
            },
            {
                "key": "MINERU_ENABLE_FORMULA",
                "label": "fields.mineruEnableFormula",
                "type": "boolean",
                "defaultValue": "true",
                "tooltip": "tooltips.mineruEnableFormula",
            },
            {
                "key": "MINERU_LOCAL_BACKEND",
                "label": "fields.mineruBackend",
                "type": "select",
                "defaultValue": "hybrid-auto-engine",
                "tooltip": "tooltips.mineruBackend",
                "options": [
                    {"value": "hybrid-auto-engine", "label": "fields.mineruBackendHybrid"},
                    {"value": "pipeline", "label": "fields.mineruBackendPipeline"},
                    {"value": "vlm-auto-engine", "label": "fields.mineruBackendVlm"},
                ],
            },
            {
                "key": "MINERU_LOCAL_PARSE_METHOD",
                "label": "fields.mineruParseMethod",
                "type": "select",
                "defaultValue": "auto",
                "options": [
                    {"value": "auto", "label": "fields.parseMethodAuto"},
                    {"value": "txt", "label": "fields.parseMethodText"},
                    {"value": "ocr", "label": "fields.parseMethodOcr"},
                ],
            },
            {
                "key": "MINERU_LOCAL_IMAGE_ANALYSIS",
                "label": "fields.mineruImageAnalysis",
                "type": "boolean",
                "defaultValue": "false",
            },
            {
                "key": "MINERU_ADDITIONAL_SUFFIXES",
                "label": "fields.mineruAdditionalSuffixes",
                "type": "text",
                "placeholder": "doc,xls,ppt",
                "tooltip": "tooltips.additionalSuffixes",
            },
            {
                "key": "MAX_PARALLEL_PARSE_MINERU",
                "label": "fields.maxParallelParse",
                "type": "number",
                "defaultValue": "2",
                "tooltip": "tooltips.maxParallelParse",
            },
            {
                "key": LIGHTRAG_PARSER_KEY,
                "label": "fields.parserRouting",
                "type": "textarea",
                "defaultValue": PARSER_PRESETS["mineru"],
                "tooltip": "tooltips.parserRouting",
            },
        ],
    },
    {
        "id": "docling",
        "name": "providers.parserDocling",
        "description": "Docling document parsing service, alternative to MinerU (PDF / Office / images)",
        "fields": [
            {
                "key": "DOCLING_ENDPOINT",
                "label": "fields.doclingEndpoint",
                "type": "text",
                "defaultValue": DEFAULT_DOCLING_ENDPOINT,
                "placeholder": "http://localhost:5001",
                "required": True,
                "tooltip": "tooltips.doclingEndpoint",
            },
            {
                "key": "DOCLING_ADDITIONAL_SUFFIXES",
                "label": "fields.doclingAdditionalSuffixes",
                "type": "text",
                "placeholder": "doc,ppt,xls",
                "tooltip": "tooltips.additionalSuffixes",
            },
            {
                "key": "MAX_PARALLEL_PARSE_DOCLING",
                "label": "fields.maxParallelParse",
                "type": "number",
                "defaultValue": "2",
                "tooltip": "tooltips.maxParallelParse",
            },
            {
                "key": LIGHTRAG_PARSER_KEY,
                "label": "fields.parserRouting",
                "type": "textarea",
                "defaultValue": PARSER_PRESETS["docling"],
                "tooltip": "tooltips.parserRouting",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Processing helpers
# ---------------------------------------------------------------------------


def derive_parsing_engine(settings: Dict[str, Any]) -> str:
    """
    Infer the UI engine selection from the persisted routing table.

    The engine is UI-only and never persisted; ``LIGHTRAG_PARSER`` is the
    source of truth, so the choice is reconstructed every time the settings
    load.  A custom routing table containing both engines resolves to
    ``mineru`` first, then ``docling``; anything else is ``native``.
    """
    value = normalize_parser_routing(settings.get(LIGHTRAG_PARSER_KEY)).lower()
    if "mineru" in value:
        return "mineru"
    if "docling" in value:
        return "docling"
    return "native"


def derive_mineru_provider(settings: Dict[str, Any]) -> str:
    """
    Resolve LightRAG's native ``MINERU_API_MODE`` (official or local).
    """
    mode = str(settings.get("MINERU_API_MODE") or "local").strip().lower()
    return mode if mode in _MINERU_MODE_REQUIREMENTS else "local"


def validate_parser_endpoints(settings: Dict[str, Any]) -> List[str]:
    """
    Validate that external parser engines referenced by ``LIGHTRAG_PARSER``
    have their required endpoint configured.

    Mirrors LightRAG startup validation (registry.py ``endpoint_requirement``
    closures): a mineru/docling rule without the matching endpoint makes the
    server refuse to start, so we reject the save early with a clear message.
    """
    errors: List[str] = []
    routing = normalize_parser_routing(settings.get(LIGHTRAG_PARSER_KEY)).lower()

    if "mineru" in routing:
        raw_mode = str(settings.get("MINERU_API_MODE") or "local").strip().lower()
        if raw_mode not in _MINERU_MODE_REQUIREMENTS:
            errors.append(
                "MINERU_API_MODE 必须是 LightRAG 支持的 official 或 local，"
                f"当前值为 {raw_mode!r}"
            )
            return errors
        provider = derive_mineru_provider(settings)
        required_keys = _MINERU_MODE_REQUIREMENTS[provider]
        missing = [
            key for key in required_keys if not str(settings.get(key) or "").strip()
        ]
        if missing:
            errors.append(
                f"LIGHTRAG_PARSER 引用了 mineru，但未配置 "
                f"{', '.join(missing)}（当前 MINERU_API_MODE={provider}）"
            )

    if "docling" in routing:
        endpoint = str(settings.get("DOCLING_ENDPOINT") or "").strip()
        if not endpoint:
            errors.append("LIGHTRAG_PARSER 引用了 docling，但未配置 DOCLING_ENDPOINT")

    return errors
