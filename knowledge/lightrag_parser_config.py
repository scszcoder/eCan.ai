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
                     configured with ``DOCLING_ENDPOINT`` and eCan's runtime
                     Bearer-auth adapter for ``DOCLING_API_KEY``.

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

Docling keeps upstream's ``DOCLING_ENDPOINT`` unchanged. LightRAG 1.5.6 has
no authentication option for Docling, so eCan adds ``DOCLING_API_KEY`` and
injects it into all Docling requests in ``lightrag_launcher``.
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
# eCanAI OpenAI-compatible proxy. The parser UI also reuses this for Docling
# when the user picks the eCanAI provider; the proxy serves `/v1/...` paths
# compatible with both ``local`` MinerU (``/tasks`` etc.) and Docling-serve
# (``/v1/convert/file/async`` etc.) on the host that fronts them.
ECANAI_PARSER_BASE_URL = (
    "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1"
)
DEFAULT_DOCLING_ENDPOINT = ECANAI_PARSER_BASE_URL

# Every env var the parsing engines touch, used to return the current
# values to the UI without leaking unrelated settings.
PARSER_SETTINGS_KEYS: Tuple[str, ...] = (
    LIGHTRAG_PARSER_KEY,
    "MINERU_API_MODE",
    "MINERU_OFFICIAL_ENDPOINT",
    "MINERU_LOCAL_ENDPOINT",
    "MINERU_LOCAL_ENDPOINT_SETTING",
    "MINERU_ECANAI_ENDPOINT",
    "MINERU_API_TOKEN",
    "MINERU_LOCAL_API_KEY",
    "MINERU_OFFICIAL_API_KEY",
    "MINERU_MODEL_VERSION",
    "MINERU_IS_OCR",
    "MINERU_LANGUAGE",
    "MINERU_ENABLE_TABLE",
    "MINERU_ENABLE_FORMULA",
    "MINERU_PAGE_RANGES",
    "MINERU_LOCAL_BACKEND",
    "MINERU_LOCAL_PARSE_METHOD",
    "MINERU_LOCAL_IMAGE_ANALYSIS",
    "MINERU_LOCAL_START_PAGE_ID",
    "MINERU_LOCAL_END_PAGE_ID",
    "MINERU_ADDITIONAL_SUFFIXES",
    "MAX_PARALLEL_PARSE_MINERU",
    "DOCLING_PROVIDER",
    "DOCLING_ENDPOINT",
    "DOCLING_OFFICIAL_ENDPOINT",
    "DOCLING_LOCAL_ENDPOINT",
    "DOCLING_ECANAI_ENDPOINT",
    "DOCLING_API_KEY",
    "DOCLING_LOCAL_API_KEY",
    "DOCLING_OFFICIAL_API_KEY",
    "DOCLING_ADDITIONAL_SUFFIXES",
    "MAX_PARALLEL_PARSE_DOCLING",
)

# Legacy DOCLING_ENDPOINT is kept in the persisted ``PARSER_SETTINGS_KEYS``
# list only for backward compatibility with existing env files.  ``getParserEngines``
# reads/writes DOCLING_LOCAL_ENDPOINT / DOCLING_OFFICIAL_ENDPOINT instead; the
# rewrite below converts the single legacy key into the new pair before save
# and back into the legacy key after load so older env files keep working.
_LEGACY_DOCLING_ENDPOINT = "DOCLING_ENDPOINT"

# ---------------------------------------------------------------------------
# Preset routing tables (canonical upstream rules)
# ---------------------------------------------------------------------------

PARSER_PRESETS: Dict[str, str] = {
    # Recommended starting behavior, no external services (§1.2)
    "native": "*:native-teP,*:legacy-R",
    # The selected external engine must come first: rules are evaluated from
    # left to right and native can also parse DOCX, so a native-first wildcard
    # silently prevents MinerU/Docling from ever seeing those documents.
    "mineru": "*:mineru-teP,*:native-teP,*:legacy-R",
    "docling": "*:docling-teP,*:native-teP,*:legacy-R",
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

# Required variables are the exact names consumed by LightRAG. ``ecanai`` is
# an eCan-specific alias for ``local`` that reuses the account-level LLM API
# key (``ECANAI_LLM_API_KEY``) and the eCanAI parser base URL; the runtime
# still talks to MinerU at ``/tasks`` on that endpoint.
_MINERU_MODE_REQUIREMENTS = {
    "official": ("MINERU_OFFICIAL_API_KEY",),
    "local": ("MINERU_LOCAL_ENDPOINT", "MINERU_LOCAL_API_KEY"),
    # eCanAI always uses the account-managed active token.
    "ecanai": ("MINERU_API_TOKEN",),
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
                "key": "PARSER_IMAGE_ANALYSIS",
                "label": "fields.parserImageAnalysis",
                "type": "boolean",
                "defaultValue": "false",
                "tooltip": "tooltips.parserImageAnalysis",
            },
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
                "key": "PARSER_IMAGE_ANALYSIS",
                "label": "fields.parserImageAnalysis",
                "type": "boolean",
                "defaultValue": "false",
                "tooltip": "tooltips.parserImageAnalysis",
            },
            {
                "key": "MINERU_API_MODE",
                "label": "fields.mineruProvider",
                "type": "select",
                "defaultValue": "ecanai",
                "tooltip": "tooltips.mineruProvider",
                "options": [
                    # eCanAI is the recommended default for desktop users
                    # (no self-hosted MinerU service required, account-level
                    # API key auto-managed). Keep it first so the dropdown
                    # mirrors the default value rather than surprising users
                    # who expect ecanai to be the primary choice.
                    {"value": "ecanai", "label": "fields.providerEcanai"},
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
                "key": "MINERU_LOCAL_ENDPOINT_SETTING",
                "label": "fields.mineruEndpoint",
                "type": "text",
                "placeholder": DEFAULT_MINERU_LOCAL_ENDPOINT,
                "tooltip": "tooltips.mineruLocalEndpoint",
            },
            {
                # eCanAI keeps its endpoint separate from ``MINERU_LOCAL_ENDPOINT``
                # so a user switching between local and ecanai modes never
                # overwrites the endpoint of the inactive mode. The eCanAI
                # value is treated as "owned by the account" and is forced
                # to ``ECANAI_PARSER_BASE_URL`` at save time
                # (``resolve_ecanai_parser_secrets``).
                "key": "MINERU_ECANAI_ENDPOINT",
                "label": "fields.mineruEcanaiEndpoint",
                "type": "text",
                "defaultValue": ECANAI_PARSER_BASE_URL,
                "placeholder": ECANAI_PARSER_BASE_URL,
                "tooltip": "tooltips.mineruEcanaiEndpoint",
            },
            {
                "key": "MINERU_API_TOKEN",
                "label": "fields.mineruApiKey",
                "type": "password",
                "required": True,
                "tooltip": "tooltips.mineruApiKey",
            },
            {
                # Per-mode key for the self-hosted MinerU service. Lives in
                # its own env var so a user-typed value is never overwritten
                # when switching to ecanai mode (which uses MINERU_API_TOKEN
                # for the account-level key). At save time the backend copies
                # this value into MINERU_API_TOKEN so LightRAG reads the
                # right credential.
                "key": "MINERU_LOCAL_API_KEY",
                "label": "fields.mineruLocalApiKey",
                "type": "password",
                "tooltip": "tooltips.mineruLocalApiKey",
            },
            {
                # Same rationale as MINERU_LOCAL_API_KEY but for the
                # official mineru.net API.
                "key": "MINERU_OFFICIAL_API_KEY",
                "label": "fields.mineruOfficialApiKey",
                "type": "password",
                "tooltip": "tooltips.mineruOfficialApiKey",
            },
            {
                "key": "MINERU_MODEL_VERSION",
                "label": "fields.mineruModelVersion",
                "type": "select",
                "defaultValue": "pipeline",
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
                # LightRAG 1.5.6 reads MINERU_LANGUAGE for BOTH modes:
                #   - local: maps to the ``lang_list`` form field of the
                #     local mineru-api service. The service only honors the
                #     12 CLI --lang values on the pipeline backend; other
                #     values silently fall back to default ch.
                #   - official: maps to the ``language`` task parameter of
                #     the mineru.net API, which accepts a much wider list
                #     (en, japanese, french, german, spanish, ... on top
                #     of the CLI set).
                # List the union so the dropdown mirrors what the API
                # accepts; the service-side behavior is documented in the
                # tooltip.
                "key": "MINERU_LANGUAGE",
                "label": "fields.mineruLanguage",
                "type": "select",
                "defaultValue": "ch",
                "tooltip": "tooltips.mineruLanguage",
                "options": [
                    {"value": "ch", "label": "fields.languageChineseMixed"},
                    {"value": "ch_server", "label": "fields.languageChineseMixedServer"},
                    {"value": "ch_lite", "label": "fields.languageChineseLite"},
                    {"value": "chinese_cht", "label": "fields.languageChineseTraditional"},
                    {"value": "en", "label": "fields.languageEnglish"},
                    {"value": "japan", "label": "fields.languageJapanese"},
                    {"value": "korean", "label": "fields.languageKorean"},
                    {"value": "ta", "label": "fields.languageTamil"},
                    {"value": "te", "label": "fields.languageTelugu"},
                    {"value": "ka", "label": "fields.languageKannada"},
                    {"value": "th", "label": "fields.languageThai"},
                    {"value": "el", "label": "fields.languageGreek"},
                    {"value": "arabic", "label": "fields.languageArabic"},
                    {"value": "east_slavic", "label": "fields.languageEastSlavic"},
                    {"value": "cyrillic", "label": "fields.languageCyrillic"},
                    {"value": "devanagari", "label": "fields.languageDevanagari"},
                    {"value": "latin", "label": "fields.languageLatin"},
                    {"value": "french", "label": "fields.languageFrench"},
                    {"value": "german", "label": "fields.languageGerman"},
                    {"value": "spanish", "label": "fields.languageSpanish"},
                    {"value": "portuguese", "label": "fields.languagePortuguese"},
                    {"value": "russian", "label": "fields.languageRussian"},
                    {"value": "italian", "label": "fields.languageItalian"},
                ],
            },
            {
                # MINERU_PAGE_RANGES is a per-file ``page_ranges`` task
                # parameter on the official mineru.net API (comma-
                # separated segments, e.g. ``1-3,5,7-9``). LightRAG 1.5.6
                # also reads it in local mode and maps it to start_page_id
                # / end_page_id via ``local_page_bounds`` which only
                # accepts a single page or simple range, so a multi-
                # segment value would fail at local submission time.
                "key": "MINERU_PAGE_RANGES",
                "label": "fields.mineruPageRanges",
                "type": "text",
                "placeholder": "1-3,5,7-9",
                "tooltip": "tooltips.mineruPageRangesTooltip",
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
                "label": "fields.mineruServerImageProcessing",
                "type": "boolean",
                "defaultValue": "false",
                "tooltip": "tooltips.mineruServerImageProcessing",
            },
            {
                # LightRAG reads these as ``start_page_id`` / ``end_page_id``
                # form fields of the local mineru-api service. They are
                # local-only — official mineru.net uses the per-file
                # MINERU_PAGE_RANGES instead.
                "key": "MINERU_LOCAL_START_PAGE_ID",
                "label": "fields.mineruLocalStartPageId",
                "type": "number",
                "placeholder": "0",
                "tooltip": "tooltips.mineruLocalPageRangeTooltip",
            },
            {
                "key": "MINERU_LOCAL_END_PAGE_ID",
                "label": "fields.mineruLocalEndPageId",
                "type": "number",
                "placeholder": "99999",
                "tooltip": "tooltips.mineruLocalPageRangeTooltip",
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
                "key": "PARSER_IMAGE_ANALYSIS",
                "label": "fields.parserImageAnalysis",
                "type": "boolean",
                "defaultValue": "false",
                "tooltip": "tooltips.parserImageAnalysis",
            },
            {
                "key": "DOCLING_PROVIDER",
                "label": "fields.doclingProvider",
                "type": "select",
                "defaultValue": "ecanai",
                "tooltip": "tooltips.doclingProvider",
                "options": [
                    {"value": "ecanai", "label": "fields.providerEcanai"},
                    {"value": "local", "label": "fields.providerLocal"},
                    {"value": "official", "label": "fields.providerOfficial"},
                ],
            },
            {
                "key": "DOCLING_OFFICIAL_ENDPOINT",
                "label": "fields.doclingEndpoint",
                "type": "text",
                "defaultValue": "https://docling.ai",
                "placeholder": "https://docling.ai",
                "tooltip": "tooltips.doclingEndpoint",
            },
            {
                "key": "DOCLING_LOCAL_ENDPOINT",
                "label": "fields.doclingEndpoint",
                "type": "text",
                "placeholder": "http://127.0.0.1:5001",
                "tooltip": "tooltips.doclingEndpoint",
            },
            {
                # Same rationale as ``MINERU_ECANAI_ENDPOINT``: the eCanAI
                # provider needs a stable endpoint that is never overwritten
                # by the user typing into local / official fields.
                "key": "DOCLING_ECANAI_ENDPOINT",
                "label": "fields.doclingEcanaiEndpoint",
                "type": "text",
                "defaultValue": ECANAI_PARSER_BASE_URL,
                "placeholder": ECANAI_PARSER_BASE_URL,
                "tooltip": "tooltips.doclingEcanaiEndpoint",
            },
            {
                "key": "DOCLING_API_KEY",
                "label": "fields.doclingApiKey",
                "type": "password",
                "required": True,
                "tooltip": "tooltips.doclingApiKey",
            },
            {
                # Per-mode API key for self-hosted Docling. Mirrors the
                # MinerU per-mode design so user-typed credentials are
                # preserved when switching between ecanai/local/official.
                "key": "DOCLING_LOCAL_API_KEY",
                "label": "fields.doclingLocalApiKey",
                "type": "password",
                "tooltip": "tooltips.doclingLocalApiKey",
            },
            {
                # Per-mode API key for the official docling.ai API. Same
                # rationale as DOCLING_LOCAL_API_KEY.
                "key": "DOCLING_OFFICIAL_API_KEY",
                "label": "fields.doclingOfficialApiKey",
                "type": "password",
                "tooltip": "tooltips.doclingOfficialApiKey",
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
# Docling provider mode requirements
# ---------------------------------------------------------------------------
#
# Docling follows the same model as MinerU: the UI exposes a three-way
# provider choice (local / official / ecanai), but LightRAG itself only knows
# about ``DOCLING_ENDPOINT`` / ``DOCLING_API_KEY``. ``ecanai`` and ``official``
# are eCan convenience aliases that re-use the same env keys but point at
# different upstream hosts.
_DOCLING_PROVIDER_REQUIREMENTS = {
    "official": ("DOCLING_OFFICIAL_ENDPOINT", "DOCLING_OFFICIAL_API_KEY"),
    # ``DOCLING_ECANAI_ENDPOINT`` is the dedicated eCanAI endpoint env var
    # so a user-typed local value is not consumed (and clobbered) by
    # switching to ecanai mode.
    "local": ("DOCLING_LOCAL_ENDPOINT", "DOCLING_LOCAL_API_KEY"),
    "ecanai": ("DOCLING_ECANAI_ENDPOINT", "DOCLING_API_KEY"),
}


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
    Resolve LightRAG's native ``MINERU_API_MODE`` (official / local / ecanai).
    ``ecanai`` is an eCan convenience alias resolved to ``local`` at save time.

    The fallback when ``MINERU_API_MODE`` is unset is ``ecanai`` so the UI
    defaults and the runtime defaults agree (empty settings should render
    with the recommended provider, not silently fall back to local).
    """
    mode = str(settings.get("MINERU_API_MODE") or "ecanai").strip().lower()
    return mode if mode in _MINERU_MODE_REQUIREMENTS else "ecanai"


def derive_docling_provider(settings: Dict[str, Any]) -> str:
    """
    Resolve the Docling provider mode (local / official / ecanai).

    Mirrors :func:`derive_mineru_provider`. Default is ``ecanai`` because the
    Docling eCanAI proxy is the easiest path for end users (no self-hosted
    docling-serve required).
    """
    mode = str(settings.get("DOCLING_PROVIDER") or "ecanai").strip().lower()
    return mode if mode in _DOCLING_PROVIDER_REQUIREMENTS else "ecanai"


def normalize_docling_provider_alias(
    settings: Dict[str, Any], ecanai_endpoint: str
) -> Dict[str, Any]:
    """
    Translate the UI-level ``DOCLING_PROVIDER`` value into the single
    ``DOCLING_ENDPOINT`` env var that LightRAG actually reads.

    All three modes share ``DOCLING_ENDPOINT`` + ``DOCLING_API_KEY``; only
    the endpoint value differs. ``official`` and ``ecanai`` are eCan
    convenience aliases that resolve to a fixed upstream / proxy URL.
    """
    provider = derive_docling_provider(settings)
    rewritten = dict(settings)
    endpoint_field = {
        "official": "DOCLING_OFFICIAL_ENDPOINT",
        "local": "DOCLING_LOCAL_ENDPOINT",
        "ecanai": "DOCLING_ECANAI_ENDPOINT",
    }[provider]
    rewritten[_LEGACY_DOCLING_ENDPOINT] = str(settings.get(endpoint_field) or "").strip()
    return rewritten


# ---------------------------------------------------------------------------
# System-managed (UI read-only) fields
# ---------------------------------------------------------------------------
#
# When the user picks the ``ecanai`` provider the URL and API key are
# sourced from the account-level secrets (``ECANAI_LLM_API_KEY`` +
# ``ECANAI_PARSER_BASE_URL``); the user must not edit them directly. We mark
# those fields as ``isSystemManaged`` so the UI renders them read-only and
# disables the input — saving still writes them, but the save path itself
# (``resolve_ecanai_parser_secrets``) refreshes them with the current
# account values so a key rotation propagates without manual intervention.
#
# The eCanAI endpoint lives in a *separate* env var
# (``MINERU_ECANAI_ENDPOINT`` / ``DOCLING_ECANAI_ENDPOINT``) rather than
# overloading ``MINERU_LOCAL_ENDPOINT`` / ``DOCLING_LOCAL_ENDPOINT``. This
# keeps the three providers truly independent: a user who types a custom
# local URL never has it clobbered by switching to ecanai and back.

_ECANAI_SYSTEM_MANAGED_FIELDS = (
    "MINERU_ECANAI_ENDPOINT",
    "MINERU_API_TOKEN",
    "DOCLING_ECANAI_ENDPOINT",
    "DOCLING_API_KEY",
)


def mark_system_managed_parser_fields(
    definitions: List[Dict[str, Any]], settings: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Return a copy of ``definitions`` with ``isSystemManaged`` set on the
    fields that the current provider mode forbids the user from editing.

    The flag is a hint for the UI only; the save path is the authoritative
    source (see ``resolve_ecanai_parser_secrets``) and re-derives the value
    from account state at every save.
    """
    mineru_ecanai = (
        derive_mineru_provider(settings) == "ecanai"
    )
    docling_ecanai = (
        derive_docling_provider(settings) == "ecanai"
    )

    managed_keys: set = set()
    if mineru_ecanai:
        managed_keys.add("MINERU_ECANAI_ENDPOINT")
        managed_keys.add("MINERU_API_TOKEN")
    if docling_ecanai:
        managed_keys.add("DOCLING_ECANAI_ENDPOINT")
        managed_keys.add("DOCLING_API_KEY")

    if not managed_keys:
        return definitions

    annotated: List[Dict[str, Any]] = []
    for engine in definitions:
        new_engine = dict(engine)
        new_fields: List[Dict[str, Any]] = []
        for field in engine.get("fields") or []:
            new_field = dict(field)
            if new_field.get("key") in managed_keys:
                new_field["isSystemManaged"] = True
            new_fields.append(new_field)
        new_engine["fields"] = new_fields
        annotated.append(new_engine)
    return annotated


def resolve_ecanai_parser_secrets(
    settings: Dict[str, Any],
    ecanai_endpoint: str,
    ecanai_api_key: str,
) -> Dict[str, Any]:
    """
    Force-refresh the URL for any parser using the eCanAI provider, and
    resolve the active API key into the env var LightRAG reads.

    Each provider mode owns its own dedicated API key env var
    (``MINERU_LOCAL_API_KEY`` / ``MINERU_OFFICIAL_API_KEY`` for self-hosted
    MinerU, etc.) so a user-typed value is never clobbered by switching
    modes. LightRAG only reads ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY``,
    so this function copies the right per-mode key into the active env var
    on save.

    For eCanAI mode the active key is fully account-managed:
      - When the account key (``ECANAI_LLM_API_KEY``) is available it is
        always used, regardless of what the UI sent. The UI marks this
        field as ``isSystemManaged`` (read-only) and auto-fills with the
        account key, but the save handler is the authoritative source so
        a stale value from a previous mode (e.g. the local-mode key that
        was synced into ``MINERU_API_TOKEN`` earlier) cannot persist.
      - When no account key is available, a user-typed custom key in
        ``MINERU_API_TOKEN`` / ``DOCLING_API_KEY`` is preserved verbatim
        so a self-hosted ecanai proxy still works for users without a
        provisioned account key.
      - ``MINERU_LOCAL_API_KEY`` / ``DOCLING_LOCAL_API_KEY`` is local
        mode's credential and never propagates into ecanai mode.

    Local and official modes copy their own per-mode key into the active
    env var verbatim.
    """
    rewritten = dict(settings)

    mineru_mode = derive_mineru_provider(rewritten)
    if mineru_mode == "ecanai":
        rewritten["MINERU_ECANAI_ENDPOINT"] = ecanai_endpoint
        if ecanai_api_key:
            # Account-managed path: overwrite whatever the UI sent. The
            # field is isSystemManaged (read-only) so the user cannot
            # type into it directly; any value arriving here from a UI
            # payload is stale and must be replaced.
            rewritten["MINERU_API_TOKEN"] = ecanai_api_key
        elif "MINERU_API_TOKEN" in rewritten:
            # No account key, user-typed custom value: preserve verbatim
            # for self-managed ecanai proxies. Local key never leaks here.
            pass
        else:
            # Ensure the key always exists in the returned dict so callers
            # can index ``resolved["MINERU_API_TOKEN"]`` regardless of
            # whether the UI included it. Empty value preserves the
            # "no credential provided" state.
            rewritten["MINERU_API_TOKEN"] = ""
        # MINERU_LOCAL_API_KEY is local mode's key and never leaks here.
    elif mineru_mode == "local":
        # New UI payloads always include the isolated setting slot, even
        # when intentionally blank. Older callers only have the canonical
        # runtime field; preserve it as a one-way compatibility fallback.
        if "MINERU_LOCAL_ENDPOINT_SETTING" in rewritten:
            rewritten["MINERU_LOCAL_ENDPOINT"] = str(
                rewritten.get("MINERU_LOCAL_ENDPOINT_SETTING") or ""
            ).strip()
        # Copy the user-typed local key into MINERU_API_TOKEN so LightRAG
        # reads the right credential. The per-mode key itself is preserved
        # verbatim above.
        local_key = str(rewritten.get("MINERU_LOCAL_API_KEY") or "").strip()
        if local_key:
            rewritten["MINERU_API_TOKEN"] = local_key
    elif mineru_mode == "official":
        official_key = str(rewritten.get("MINERU_OFFICIAL_API_KEY") or "").strip()
        if official_key:
            rewritten["MINERU_API_TOKEN"] = official_key

    docling_mode = derive_docling_provider(rewritten)
    if docling_mode == "ecanai":
        rewritten["DOCLING_ECANAI_ENDPOINT"] = ecanai_endpoint
        if ecanai_api_key:
            # Same account-managed logic as MinerU eCanAI above.
            rewritten["DOCLING_API_KEY"] = ecanai_api_key
        elif "DOCLING_API_KEY" in rewritten:
            # No account key; preserve the user-typed custom key.
            pass
        else:
            # Ensure the key always exists so callers can safely index it.
            rewritten["DOCLING_API_KEY"] = ""
        # DOCLING_LOCAL_API_KEY never leaks here either.
    elif docling_mode == "local":
        local_key = str(rewritten.get("DOCLING_LOCAL_API_KEY") or "").strip()
        if local_key:
            rewritten["DOCLING_API_KEY"] = local_key
    elif docling_mode == "official":
        official_key = str(rewritten.get("DOCLING_OFFICIAL_API_KEY") or "").strip()
        if official_key:
            rewritten["DOCLING_API_KEY"] = official_key

    return rewritten


def unsupported_parser_files(settings: Dict[str, Any], paths: List[Any]) -> List[str]:
    """Return files unsupported by the currently selected parser.

    MinerU 3.4.4 is restricted to its documented Office/PDF/image formats.
    Notably, ``.tiff`` is accepted while the ``.tif`` alias is not.
    """
    if derive_parsing_engine(settings) != "mineru":
        return []
    supported_suffixes = {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".png",
        ".jpg",
        ".jpeg",
        ".jp2",
        ".webp",
        ".gif",
        ".bmp",
        ".tiff",
    }
    return [
        str(path)
        for path in paths
        if not any(
            str(path).strip().lower().endswith(suffix)
            for suffix in supported_suffixes
        )
    ]


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
        raw_mode = str(settings.get("MINERU_API_MODE") or "ecanai").strip().lower()
        if raw_mode not in _MINERU_MODE_REQUIREMENTS:
            errors.append(
                "MINERU_API_MODE 必须是 official / local / ecanai，"
                f"当前值为 {raw_mode!r}"
            )
            return errors
        provider = derive_mineru_provider(settings)
        required_keys = _MINERU_MODE_REQUIREMENTS[provider]
        if provider == "ecanai":
            # eCanAI mode: MINERU_API_TOKEN is fully account-managed. The
            # frontend marks this field as isSystemManaged (read-only) and
            # auto-fills with the account key from secure_store on every
            # load; the save handler refreshes it again at write time.
            # MINERU_LOCAL_API_KEY belongs to local mode and is the wrong
            # credential for the ecanai proxy — accepting it here would
            # leak a self-hosted local key into the ecanai request flow.
            # Note: when the account key is unavailable (e.g. no signed-in
            # account), the save handler's earlier guard rejects the save
            # *before* this validator runs, so an empty MINERU_API_TOKEN
            # arriving here is always a hard error.
            has_token = bool(str(settings.get("MINERU_API_TOKEN") or "").strip())
            if not has_token:
                errors.append(
                    f"LIGHTRAG_PARSER 引用了 mineru，但未配置 API Key "
                    f"（当前 MINERU_API_MODE=ecanai，请在 UI 上填写 "
                    f"MINERU_API_TOKEN 或确保账户有 ECANAI_LLM_API_KEY）"
                )
        else:
            missing = [
                key for key in required_keys if not str(settings.get(key) or "").strip()
            ]
            if missing:
                errors.append(
                    f"LIGHTRAG_PARSER 引用了 mineru，但未配置 "
                    f"{', '.join(missing)}（当前 MINERU_API_MODE={provider}）"
                )

    if "docling" in routing:
        raw_mode = str(settings.get("DOCLING_PROVIDER") or "ecanai").strip().lower()
        if raw_mode not in _DOCLING_PROVIDER_REQUIREMENTS:
            errors.append(
                "DOCLING_PROVIDER 必须是 local / official / ecanai，"
                f"当前值为 {raw_mode!r}"
            )
            return errors
        provider = derive_docling_provider(settings)
        required_keys = _DOCLING_PROVIDER_REQUIREMENTS[provider]
        if provider == "ecanai":
            # DOCLING_ECANAI_ENDPOINT is always required
            if not str(settings.get("DOCLING_ECANAI_ENDPOINT") or "").strip():
                errors.append(
                    "LIGHTRAG_PARSER 引用了 docling，但未配置 DOCLING_ECANAI_ENDPOINT "
                    "（当前 DOCLING_PROVIDER=ecanai）"
                )
            has_api_key = bool(str(settings.get("DOCLING_API_KEY") or "").strip())
            if not has_api_key:
                errors.append(
                    f"LIGHTRAG_PARSER 引用了 docling，但未配置 API Key "
                    f"（当前 DOCLING_PROVIDER=ecanai，请在 UI 上填写 "
                    f"DOCLING_API_KEY 或确保账户有 ECANAI_LLM_API_KEY）"
                )
        else:
            missing = [
                key for key in required_keys if not str(settings.get(key) or "").strip()
            ]
            if missing:
                errors.append(
                    f"LIGHTRAG_PARSER 引用了 docling，但未配置 "
                    f"{', '.join(missing)}（当前 DOCLING_PROVIDER={provider}）"
                )

    return errors


def normalize_parser_ecanai_alias(
    settings: Dict[str, Any], ecanai_endpoint: str
) -> Dict[str, Any]:
    """
    Translate the UI-only ``MINERU_API_MODE=ecanai`` / ``DOCLING_PROVIDER=ecanai``
    values into LightRAG-compatible form before persisting to ``lightrag.env``.

    LightRAG's ``MinerURawClient.__init__`` only accepts ``official`` or
    ``local``; ``ecanai`` is an eCan convenience alias that says "use the
    eCanAI OpenAI-compatible proxy and the account-level LLM API key".  We
    rewrite the mode to ``local``, point ``MINERU_LOCAL_ENDPOINT`` at the
    eCanAI proxy, and let the UI handle the API key source separately.
    Docling has the same UX: the UI exposes a three-way ``DOCLING_PROVIDER``
    selector, but LightRAG only reads ``DOCLING_ENDPOINT`` + ``DOCLING_API_KEY``.
    """
    rewritten = dict(settings)

    if str(rewritten.get("MINERU_API_MODE") or "").strip().lower() == "ecanai":
        rewritten["MINERU_API_MODE"] = "local"
        # LightRAG's local MinerU reads ``MINERU_LOCAL_ENDPOINT``; the eCanAI
        # provider is an alias for ``local`` that uses the eCanAI proxy URL.
        # Source the value from ``MINERU_ECANAI_ENDPOINT`` so a user-typed
        # value in the eCanAI box is preserved across re-saves without
        # clobbering any value the user typed into the local box.
        ecanai_endpoint_value = str(rewritten.get("MINERU_ECANAI_ENDPOINT") or "").strip()
        if ecanai_endpoint_value:
            rewritten["MINERU_LOCAL_ENDPOINT"] = ecanai_endpoint_value

    if "DOCLING_PROVIDER" in settings or "DOCLING_ENDPOINT" in settings:
        # Always rewrite the legacy DOCLING_ENDPOINT value (which LightRAG
        # actually reads) from whichever per-mode field the user is editing.
        # All three Docling modes share ``DOCLING_ENDPOINT`` + ``DOCLING_API_KEY``;
        # the per-mode field just stores where the endpoint points.
        rewritten = normalize_docling_provider_alias(rewritten, ecanai_endpoint)

    return rewritten
