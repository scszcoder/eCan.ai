"""
LightRAG Launcher with eCan Customizations

For LightRAG ≥ 1.5.0 (tested against 1.5.6). The launcher monkey-patches a
small set of surfaces where LightRAG has a gap eCan needs filled:

1. Rerank binding conversion — non-native providers (ryoais, ollama) are
   routed through the jina-compatible proxy so LightRAG can speak to them
   while the UI keeps showing the real provider name.
2. Custom chunker injection — LightRAG 1.5 natively accepts a
   ``chunking_func``; eCan's ``universal_chunking_func`` preserves table
   structure across DOCX / Excel / Markdown / PDF.
3. SSL verification control — opt-in via ``SSL_VERIFY=false`` for local
   development and self-signed certificates.
4. httpx compat shim — alias ``httpx.TimeoutError`` for ``browser-use``,
   which still references the pre-0.20 attribute name.
5. Confidence scoring — ``generate_reference_list_from_chunks`` is wrapped
   to also surface per-reference scores so the Q&A prompt can gate
   low-confidence answers.  Degrades gracefully to WARNING if upstream
   renames the function; the server starts without confidence scoring.
6. Lambda proxy headers — when the LLM host is a Lambda Function URL,
   inject ``X-User-Id`` / ``X-Provider`` so the proxy can do per-user
   token accounting.
6.5. LLM retry wrapper — ``AsyncOpenAI.chat.completions.create`` is wrapped
   with exponential backoff for ``RateLimitError`` / ``APIConnectionError`` /
   ``APITimeoutError`` / ``httpx`` network errors. LightRAG 1.5.6 has no
   retry, so without this a transient 429 aborts the whole document.
   Disabled via ``LIGHTRAG_LLM_RETRY=0``.
7. Health monitoring — registers ``/health/status``, ``/health/workers``,
   ``/health/circuits`` (logic in ``knowledge/lightrag_health.py``).
8. Parser retry reset — FAILED documents are reparsed with the current routing
   after removing artifacts, chunks and KG contributions from the old engine.

All patches degrade gracefully: on failure they emit a WARNING and let the
server continue with reduced functionality.  Only ``patch_rerank_binding``
has no fallback (a missing provider is a configuration error).

LightRAG ≥ 1.5 owns routing, cancellation, bounded scheduling, capability
discovery and crash recovery natively; eCan only changes the explicit manual
retry semantics to match the UI's “reprocess with current configuration”.
"""

import sys
import os
import ssl
import aiohttp
import shutil
from pathlib import Path

# Handle __file__ not defined in PyInstaller frozen environment (worker process)
if '__file__' not in dir():
    # In frozen environment, use sys.executable or sys._MEIPASS
    if getattr(sys, 'frozen', False):
        __file__ = os.path.join(sys._MEIPASS, 'knowledge', 'lightrag_launcher.py')
    else:
        __file__ = os.path.abspath(sys.argv[0])

# Add project root to sys.path
_launcher_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_launcher_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def patch_openmp_duplicate_fix():
    """Fix OpenMP library version conflict that causes SIGABRT crashes.
    
    When multiple OpenMP libraries are loaded (e.g., one from conda/venv and one
    from system Homebrew), they have different internal state and cause
    __kmp_abort_process() when trying to register thread regions.
    
    The fix: set LD_PRELOAD-equivalent via DYLD_INSERT_LIBRARIES on macOS
    to ensure only one OpenMP implementation is used.
    
    Alternative: set KMP_DUPLICATE_LIB_OK=TRUE to allow duplicate libraries
    (may cause subtle issues but prevents crashes).
    """
    import platform
    if platform.system() != 'Darwin':
        return
    
    # KMP_DUPLICATE_LIB_OK tells Intel OpenMP to tolerate duplicate libraries
    if 'KMP_DUPLICATE_LIB_OK' not in os.environ:
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
        logger.info('[Launcher] Set KMP_DUPLICATE_LIB_OK=TRUE to prevent OpenMP conflicts')
    
    # Also disable GOMP for scikit-learn compatibility
    if 'OMP_NUM_THREADS' not in os.environ:
        # Use single thread for OpenMP to reduce contention
        os.environ['OMP_NUM_THREADS'] = '1'
        logger.info('[Launcher] Set OMP_NUM_THREADS=1 to reduce OpenMP contention')

from utils.logger_helper import logger_helper as logger

# Re-export stop controller for external access
from knowledge.stop_controller import (
    StopController,
    get_stop_controller,
    request_stop,
    is_stop_requested,
    reset_stop,
)
from knowledge.lightrag_compat import (
    SUPPORTED_MIN_VERSION,
    installed_lightrag_version,
    support_status,
)


# ==================== Module Replacement ====================


def patch_lightrag_init():
    """Inject custom chunker into LightRAG initialization
    
    LightRAG 1.5 natively supports ``chunking_func`` as a constructor
    parameter.  We inject ``universal_chunking_func`` so every
    ``LightRAG()`` call automatically uses eCan's table-aware chunker
    instead of LightRAG's default fixed-token chunker.

    Gracefully degrades: if the custom chunker cannot be loaded the
    server starts with LightRAG's built-in chunker and a WARNING is
    emitted so operators know chunking quality will be reduced.
    """
    use_custom_chunker = os.getenv('LIGHTRAG_CUSTOM_CHUNKER') == '1'
    if not use_custom_chunker:
        logger.info("[Launcher] Custom chunker disabled, skipping injection")
        return
    
    try:
        from knowledge.advanced_chunker import universal_chunking_func
        from lightrag import LightRAG
    except ImportError as e:
        logger.warning(
            f"[Launcher] Cannot import chunker: {e}. "
            "Using LightRAG built-in chunker instead."
        )
        return
    except Exception as e:
        logger.warning(
            f"[Launcher] Custom chunker unavailable ({e}). "
            "Using LightRAG built-in chunker instead."
        )
        return
    
    try:
        original_init = LightRAG.__init__
        
        def patched_init(self, *args, **kwargs):
            if 'chunking_func' not in kwargs:
                logger.debug("[Launcher] Injecting custom chunker into LightRAG")
                kwargs['chunking_func'] = universal_chunking_func
            
            original_init(self, *args, **kwargs)
        
        LightRAG.__init__ = patched_init
        logger.info("[Launcher] ✅ Custom chunker injection active")
    except Exception as e:
        logger.warning(
            f"[Launcher] Cannot patch LightRAG.__init__: {e}. "
            "Using LightRAG built-in chunker instead."
        )


def patch_ssl():
    """Disable SSL verification when ``SSL_VERIFY=false`` is set.

    The env var follows a positive boolean convention: ``SSL_VERIFY=true``
    (the default) keeps verification enabled; ``SSL_VERIFY=false`` switches it
    off. ``lightrag_server.py`` defaults the env var to ``false`` for
    development; this patch honours that without forcing developers to also
    know the underlying monkey-patches.

    Two surfaces are patched:

    - ``ssl._create_default_https_context`` — covers ``urllib`` / stdlib HTTPS.
    - ``aiohttp.TCPConnector.__init__`` — covers aiohttp callers (the LLM and
      rerank bindings both go through aiohttp).
    - ``httpx.Client.__init__`` / ``httpx.AsyncClient.__init__`` — covers the
      openai SDK and any other httpx-based caller. The openai SDK is what
      lightrag uses for embedding and LLM calls; without this patch,
      https://localhost/* fails with ``ConnectError('"localhost" certificate
      does not meet standards')`` even when aiohttp and urllib are disabled.

    Each surface is patched independently and its failure is logged at WARNING
    (per CLAUDE.md §6: SSL config issues are configuration bugs, not crashes).
    """
    disable_ssl = os.environ.get('SSL_VERIFY', 'true').strip().lower() == 'false'

    if not disable_ssl:
        logger.info('[Launcher] SSL verification enabled (SSL_VERIFY != "false")')
        return

    logger.info('[Launcher] 🛡️ Disabling SSL verification (SSL_VERIFY=false)...')

    try:
        ssl._create_default_https_context = ssl._create_unverified_context
        logger.info('[Launcher] ✅ Patched ssl._create_default_https_context')
    except AttributeError as e:
        logger.warning(f'[Launcher] ssl module missing _create_default_https_context: {e}')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch ssl module: {e}')

    try:
        original_init = aiohttp.TCPConnector.__init__

        def _new_init(self, *args, **kwargs):
            kwargs['ssl'] = False
            return original_init(self, *args, **kwargs)

        aiohttp.TCPConnector.__init__ = _new_init
        logger.info('[Launcher] ✅ Patched aiohttp.TCPConnector to disable SSL')
    except AttributeError as e:
        logger.warning(f'[Launcher] aiohttp.TCPConnector missing: {e}')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch aiohttp.TCPConnector: {e}')

    # httpx is used by the openai SDK (and therefore by lightrag's embedding
    # / LLM bindings). Without this patch, calls to https://localhost/* fail
    # with httpx.ConnectError('"localhost" certificate does not meet standards')
    # even though aiohttp and urllib are disabled. Patch both the default
    # Client.__init__ and the async AsyncClient.__init__ used by async flows.
    #
    # IMPORTANT: the openai SDK imports `httpx2` (a vendored fork in
    # site-packages/httpx2/), NOT `httpx`. We must patch both packages —
    # patching only one leaves the other path unverified.
    def _patch_httpx_module(httpx_module, label):
        try:
            original_client_init = httpx_module.Client.__init__

            def _new_client_init(self, *args, **kwargs):
                kwargs['verify'] = False
                return original_client_init(self, *args, **kwargs)

            httpx_module.Client.__init__ = _new_client_init
            logger.info(f'[Launcher] ✅ Patched {label}.Client.__init__ to disable SSL')

            original_async_client_init = httpx_module.AsyncClient.__init__

            def _new_async_client_init(self, *args, **kwargs):
                kwargs['verify'] = False
                return original_async_client_init(self, *args, **kwargs)

            httpx_module.AsyncClient.__init__ = _new_async_client_init
            logger.info(f'[Launcher] ✅ Patched {label}.AsyncClient.__init__ to disable SSL')
        except AttributeError as e:
            logger.warning(f'[Launcher] {label} missing expected attribute: {e}')
        except Exception as e:
            logger.warning(f'[Launcher] Failed to patch {label} SSL: {e}')

    try:
        import httpx as _httpx
        _patch_httpx_module(_httpx, 'httpx')
    except ImportError:
        logger.debug('[Launcher] httpx not installed, skipping SSL patch')

    try:
        import httpx2 as _httpx2
        _patch_httpx_module(_httpx2, 'httpx2')
    except ImportError:
        logger.debug('[Launcher] httpx2 not installed, skipping SSL patch')


def patch_httpx_timeout_compat():
    """Add ``httpx.TimeoutError`` alias for ``browser-use`` compatibility.

    httpx ≥ 0.20 renamed ``TimeoutError`` → ``TimeoutException``;
    ``browser-use`` still references ``httpx.TimeoutError`` in its except
    clauses, so without this alias every LLM call routed through browser-use
    fails with ``AttributeError: module 'httpx' has no attribute 'TimeoutError'``.

    This patch is independent of the LightRAG version — it fixes a httpx /
    browser-use surface mismatch that affects every deployment.
    """
    try:
        import httpx
    except ImportError:
        logger.debug("[Launcher] httpx not installed, skipping TimeoutError compat")
        return

    if not hasattr(httpx, "TimeoutError"):
        httpx.TimeoutError = httpx.TimeoutException
        logger.info("[Launcher] ✅ httpx.TimeoutError alias added (compat shim for browser-use)")
    else:
        logger.debug("[Launcher] httpx.TimeoutError already exists, no shim needed")


def patch_mineru_local_bearer_auth():
    """Attach ``MINERU_API_TOKEN`` to local/custom MinerU requests."""
    try:
        from lightrag.parser.external.mineru.client import MinerURawClient

        original = MinerURawClient._download_local
        if getattr(original, '_ecan_bearer_auth_patch', False):
            return

        class _BearerClient:
            def __init__(self, client, token):
                self._client = client
                self._authorization = f'Bearer {token}'

            def _with_auth(self, kwargs):
                merged = dict(kwargs)
                headers = dict(merged.get('headers') or {})
                headers.setdefault('Authorization', self._authorization)
                merged['headers'] = headers
                return merged

            async def get(self, *args, **kwargs):
                return await self._client.get(*args, **self._with_auth(kwargs))

            async def post(self, *args, **kwargs):
                return await self._client.post(*args, **self._with_auth(kwargs))

            def __getattr__(self, name):
                return getattr(self._client, name)

        async def authenticated_download_local(self, client, *args, **kwargs):
            token = str(self.api_token or '').strip()
            if not token:
                raise ValueError(
                    'MINERU_API_TOKEN is required when MINERU_API_MODE=local'
                )
            return await original(
                self, _BearerClient(client, token), *args, **kwargs
            )

        authenticated_download_local._ecan_bearer_auth_patch = True
        MinerURawClient._download_local = authenticated_download_local
        logger.info('[Launcher] ✅ Enabled Bearer authentication for local MinerU')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch local MinerU authentication: {e}')


def patch_docling_bearer_auth():
    """Attach ``DOCLING_API_KEY`` to every Docling HTTP request."""
    try:
        from lightrag.parser.external.docling.client import DoclingRawClient

        if getattr(DoclingRawClient, '_ecan_bearer_auth_patch', False):
            return

        class _BearerClient:
            def __init__(self, client, token):
                self._client = client
                self._authorization = f'Bearer {token}'

            def _with_auth(self, kwargs):
                merged = dict(kwargs)
                headers = dict(merged.get('headers') or {})
                headers.setdefault('Authorization', self._authorization)
                merged['headers'] = headers
                return merged

            async def get(self, *args, **kwargs):
                return await self._client.get(*args, **self._with_auth(kwargs))

            async def post(self, *args, **kwargs):
                return await self._client.post(*args, **self._with_auth(kwargs))

            def __getattr__(self, name):
                return getattr(self._client, name)

        for method_name in ('_submit', '_poll_until_done', '_download_result_into'):
            original = getattr(DoclingRawClient, method_name)

            async def authenticated_request(self, client, *args, _original=original, **kwargs):
                token = os.environ.get('DOCLING_API_KEY', '').strip()
                if not token:
                    raise ValueError('DOCLING_API_KEY is required for Docling')
                return await _original(
                    self, _BearerClient(client, token), *args, **kwargs
                )

            setattr(DoclingRawClient, method_name, authenticated_request)

        DoclingRawClient._ecan_bearer_auth_patch = True
        logger.info('[Launcher] ✅ Enabled Bearer authentication for Docling')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch Docling authentication: {e}')


def patch_manual_retry_to_use_current_parser():
    """Make FAILED-document retries reparse from scratch with current routing.

    LightRAG 1.5.6 intentionally preserves ``full_docs.parse_engine`` and raw
    parser bundles during FAILED→PENDING reset. For the eCan UI, “scan/retry”
    means applying the currently selected parser, so retaining those values
    can silently run an obsolete engine after the user switches providers.
    """
    try:
        from lightrag.constants import (
            FULL_DOCS_FORMAT_PENDING_PARSE,
            PARSED_ARTIFACT_DIR_SUFFIXES,
            PARSED_DIR_NAME,
        )
        from lightrag.parser.routing import resolve_file_parser_directives
        from lightrag.pipeline import _PipelineMixin
        from lightrag.utils_pipeline import doc_status_custom_chunk_patch

        original = _PipelineMixin._reset_failed_page
        if getattr(original, '_ecan_current_parser_retry_patch', False):
            return

        async def reset_with_current_parser(
            self, docs, token, pipeline_status, pipeline_status_lock
        ):
            # Match upstream's ownership fence before mutating full_docs or
            # deleting artifacts. A stale retry owner must write nothing.
            if not await self._still_freeze_owner(
                token, pipeline_status, pipeline_status_lock
            ):
                return await original(
                    self, docs, token, pipeline_status, pipeline_status_lock
                )

            parsed_root = (
                Path(os.environ.get('INPUT_DIR', './inputs'))
                / (str(getattr(self, 'workspace', '') or '').strip())
                / PARSED_DIR_NAME
            )

            full_doc_updates = {}
            for doc_id, status_doc in docs.items():
                if doc_status_custom_chunk_patch(status_doc) is not None:
                    continue
                content_data = await self.full_docs.get_by_id(doc_id)
                if not isinstance(content_data, dict):
                    continue
                file_path = str(
                    getattr(status_doc, 'file_path', '')
                    or content_data.get('file_path')
                    or ''
                ).strip()
                if not file_path:
                    continue

                engine, process_options = resolve_file_parser_directives(file_path)

                old_chunk_ids = list(dict.fromkeys(
                    chunk_id
                    for chunk_id in (getattr(status_doc, 'chunks_list', None) or [])
                    if isinstance(chunk_id, str) and chunk_id
                ))
                if old_chunk_ids:
                    await self._purge_doc_chunks_and_kg(
                        doc_id,
                        old_chunk_ids,
                        pipeline_status=pipeline_status,
                        pipeline_status_lock=pipeline_status_lock,
                    )
                    status_doc.chunks_list = []
                    status_doc.chunks_count = 0

                fresh = dict(content_data)
                fresh.update({
                    'content': '',
                    'parse_format': FULL_DOCS_FORMAT_PENDING_PARSE,
                    'parse_engine': engine,
                    'process_options': process_options,
                })
                for stale_key in (
                    'sidecar_location', 'content_hash', 'parse_start_time',
                    'parse_end_time', 'analyzing_start_time', 'analyzing_end_time',
                    'chunks_list', 'chunks_count',
                ):
                    fresh.pop(stale_key, None)
                full_doc_updates[doc_id] = fresh

                if not isinstance(status_doc.metadata, dict):
                    status_doc.metadata = {}
                status_doc.metadata['process_options'] = process_options
                status_doc.metadata.pop('parse_engine', None)

                basename = Path(file_path).name
                if parsed_root.is_dir():
                    for candidate in parsed_root.iterdir():
                        if not candidate.is_dir():
                            continue
                        if any(
                            candidate.name == f'{basename}{suffix}'
                            or candidate.name.startswith(f'{basename}{suffix}_')
                            for suffix in PARSED_ARTIFACT_DIR_SUFFIXES
                        ):
                            shutil.rmtree(candidate)
                            logger.info(
                                '[retry] Removed stale parser artifact: %s', candidate
                            )

                logger.info(
                    '[retry] %s will be reparsed from scratch with current engine=%s',
                    file_path,
                    engine,
                )

            if full_doc_updates:
                await self.full_docs.upsert(full_doc_updates)
                await self.full_docs.index_done_callback()

            return await original(
                self, docs, token, pipeline_status, pipeline_status_lock
            )

        reset_with_current_parser._ecan_current_parser_retry_patch = True
        _PipelineMixin._reset_failed_page = reset_with_current_parser
        logger.info('[Launcher] ✅ FAILED retries now use the current parser')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch parser retry reset: {e}')


def patch_utils_for_confidence_scoring():
    """Patch utils.generate_reference_list_from_chunks to include scores for confidence scoring.

    If upstream renames or restructures the target function, this degrades
    gracefully: confidence scoring becomes unavailable but the server starts
    normally (per CLAUDE.md §6 "Expected Behavior" vs "True Bug" rule).
    """
    logger.info("[Launcher] Patching utils for confidence scoring...")

    from lightrag import utils as _lr_utils
    from third_party.lightrag_custom.utils_custom import (
        patch_generate_reference_list_from_chunks,
        generate_reference_list_from_chunks_with_scores,
    )

    if not hasattr(_lr_utils, "generate_reference_list_from_chunks"):
        logger.warning(
            "[Launcher] lightrag.utils.generate_reference_list_from_chunks not found "
            "(upstream rename?). Confidence scoring unavailable — proceeding without it."
        )
        return

    if not patch_generate_reference_list_from_chunks():
        logger.warning(
            "[Launcher] patch_generate_reference_list_from_chunks() returned False — "
            "confidence scoring unavailable — proceeding without it."
        )
        return

    if _lr_utils.generate_reference_list_from_chunks is not generate_reference_list_from_chunks_with_scores:
        logger.warning(
            "[Launcher] generate_reference_list_from_chunks replacement did not stick. "
            "Confidence scoring unavailable — proceeding without it."
        )
        return

    logger.info("[Launcher] ✅ generate_reference_list_from_chunks patched with score support")


def patch_rerank_binding_for_proxy():
    """
    Patch to convert non-native rerank provider bindings to jina format at runtime.
    
    This allows UI to display the actual provider (ryoais, ollama, etc.) while
    LightRAG uses the compatible jina format internally.
    """
    try:
        from knowledge.lightrag_constants import is_native_rerank_provider, DEFAULT_PROXY_RERANK_BINDING
        
        rerank_binding = os.environ.get('RERANK_BINDING', '').lower()
        
        # Log simplified configuration
        logger.info(f'[Launcher] ========== Rerank Configuration ==========')
        logger.info(f'[Launcher] Provider: {rerank_binding} | Model: {os.environ.get("RERANK_MODEL", "N/A")}')
        
        if not rerank_binding:
            logger.warning('[Launcher] RERANK_BINDING is empty, skipping conversion')
            return
        
        if not is_native_rerank_provider(rerank_binding):
            # Convert to jina format for LightRAG
            os.environ['RERANK_BINDING'] = DEFAULT_PROXY_RERANK_BINDING
            
            # Verify proxy configuration
            rerank_host = os.environ.get('RERANK_BINDING_HOST', '')
            if not rerank_host or 'localhost' not in rerank_host:
                logger.warning(f'[Launcher] ⚠️  RERANK_BINDING_HOST should point to localhost proxy: {rerank_host}')
            
            logger.info(f'[Launcher] Using Proxy: {rerank_host}')
            logger.info(f'[Launcher] LightRAG will use: {DEFAULT_PROXY_RERANK_BINDING} provider')
        else:
            # Native provider
            rerank_host = os.environ.get('RERANK_BINDING_HOST', 'N/A')
            logger.info(f'[Launcher] Direct Service: {rerank_host}')
            logger.info(f'[Launcher] Native provider, no proxy needed')
        
        logger.info(f'[Launcher] =============================================')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch rerank binding: {e}')
        import traceback
        logger.warning(traceback.format_exc())


def patch_openai_client_for_lambda_proxy():
    """Inject X-User-Id and X-Provider headers into OpenAI client when Lambda proxy is active.

    LightRAG uses AsyncOpenAI(base_url=LLM_BINDING_HOST). When LLM_BINDING_HOST
    points to our Lambda Function URL, we patch the OpenAI client constructor to
    add per-user headers so the Lambda can do token accounting.

    Alternative (less invasive): pass ``default_headers`` directly to the
    ``AsyncOpenAI`` constructor in ``lightrag_server.py`` after ``rag`` is
    created::

        rag.llm_model_func = AsyncOpenAI(
            base_url=os.environ["LLM_BINDING_HOST"],
            default_headers={"X-User-Id": user_id, "X-Provider": provider},
        )

    That approach requires changes inside the LightRAG upstream module, so this
    patch is used for now.  Degrades gracefully: a failure emits a WARNING and
    the server starts without per-user token accounting.
    """
    proxy_host = os.environ.get('LLM_BINDING_HOST', '')
    _proxy_markers = ('lambda-url', 'execute-api',
                      # CN: TCB-hosted OpenAI-compatible llm-proxy service
                      'tcloudbase.com', '/llm-proxy')
    if not proxy_host or not any(m in proxy_host for m in _proxy_markers):
        logger.info('[Launcher] Lambda proxy not detected, skipping OpenAI header patch')
        return

    user_id = os.environ.get('ECAN_USER_ID', '')
    llm_provider = os.environ.get('ECAN_LLM_PROVIDER', '')
    logger.info(f'[Launcher] Lambda proxy detected ({proxy_host}), injecting user headers (user={user_id})')

    try:
        import openai
        _original_init = openai.AsyncOpenAI.__init__

        def _patched_init(self, *args, **kwargs):
            # Merge our headers into default_headers
            extra = {
                'X-User-Id': user_id,
                'X-Provider': llm_provider or 'openai',
            }
            existing = kwargs.get('default_headers') or {}
            if isinstance(existing, dict):
                existing = {**existing, **extra}
            else:
                existing = extra
            kwargs['default_headers'] = existing
            return _original_init(self, *args, **kwargs)

        openai.AsyncOpenAI.__init__ = _patched_init
        logger.info('[Launcher] Patched AsyncOpenAI.__init__ with proxy headers')
    except Exception as e:
        logger.warning(f'[Launcher] Failed to patch OpenAI client for proxy: {e}')


def patch_openai_client_for_retry_on_429():
    """Wrap each OpenAI client's chat.completions.create with exponential backoff.

    LightRAG 1.5.6's ``operate.py`` uses a blanket ``except Exception`` (line 4065)
    around per-chunk LLM calls; any 429 / connection error / timeout aborts the
    whole chunk and propagates up as a doc-level failure. There is no built-in
    retry.

    Wrapping the OpenAI client's ``chat.completions.create`` per-instance (via
    ``__init__``) is the minimal surface to add retry: it catches the failure
    at the network layer and re-issues the same request, leaving LightRAG's
    call sites untouched.

    Why per-instance instead of class-level: ``AsyncOpenAI.chat`` is a
    ``cached_property`` in openai-sdk ≥ 1.x, so the class attribute cannot be
    ``setattr``-replaced. Wrapping in ``__init__`` works for any SDK shape.

    Only triggered on retriable conditions:
    - openai.RateLimitError (HTTP 429)
    - openai.APIConnectionError (network blip)
    - openai.APITimeoutError (slow provider)
    - httpx.ConnectError / httpx.ReadTimeout / httpx.TimeoutException (transports)

    Non-retriable errors (400 bad request, 401 unauth, 422 content-length)
    pass through unchanged so the user still sees a clear failure.

    Degrades gracefully: if the OpenAI client shape changes upstream, the
    wrapper falls back to no-op and emits a WARNING.
    """
    if os.environ.get('LIGHTRAG_LLM_RETRY', '1') != '1':
        logger.info('[Launcher] LLM retry wrapper disabled via LIGHTRAG_LLM_RETRY=0')
        return

    max_retries = int(os.environ.get('LIGHTRAG_LLM_MAX_RETRIES', '3'))
    initial_backoff = float(os.environ.get('LIGHTRAG_LLM_RETRY_BACKOFF_SEC', '1.0'))

    try:
        import asyncio as _asyncio
        import openai
        from openai import (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
        )

        try:
            import httpx
            httpx_retriable = (httpx.ConnectError, httpx.ReadTimeout, httpx.TimeoutException)
        except ImportError:
            httpx_retriable = ()

        retriable = (RateLimitError, APIConnectionError, APITimeoutError) + httpx_retriable
    except ImportError as e:
        logger.warning(f'[Launcher] Cannot import openai for retry wrapper: {e}')
        return

    try:
        _original_init = openai.AsyncOpenAI.__init__

        def _proxy_wants_no_stream(client) -> bool:
            """The eCanAI/TCB llm-proxy v1 surface rejects stream=True with
            400 'streaming is not supported by this endpoint'."""
            try:
                base = str(getattr(client, 'base_url', '') or '')
                return 'llm-proxy' in base or 'tcloudbase.com' in base
            except Exception:
                return False

        class _FakeStream:
            """Minimal async-iterator emulating an OpenAI chat stream from a
            non-streaming response: one content chunk, then usage, then stop.
            Matches what lightrag/llm/openai.py's stream reader consumes
            (chunk.choices[0].delta.content / chunk.usage)."""

            def __init__(self, response):
                self._response = response
                self._done = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._done:
                    raise StopAsyncIteration
                self._done = True
                from types import SimpleNamespace
                choice = (self._response.choices or [None])[0]
                content = getattr(getattr(choice, 'message', None), 'content', '') or ''
                delta = SimpleNamespace(content=content)
                fake_choice = SimpleNamespace(delta=delta, finish_reason='stop')
                return SimpleNamespace(
                    choices=[fake_choice],
                    usage=getattr(self._response, 'usage', None),
                )

            async def close(self):
                return None

        async def _create_with_retry(self, *args, **kwargs):
            # 2026-08-30: query-time answer synthesis passes stream=True; the
            # llm-proxy rejects it. Downgrade to a non-streaming call and hand
            # LightRAG a single-chunk fake stream so both code paths work.
            emulate_stream = False
            if kwargs.get('stream') and _proxy_wants_no_stream(self):
                kwargs = dict(kwargs)
                kwargs.pop('stream', None)
                kwargs.pop('stream_options', None)
                emulate_stream = True
            backoff = initial_backoff
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    result = await self._llm_original_create(*args, **kwargs)
                    return _FakeStream(result) if emulate_stream else result
                except retriable as e:
                    last_exc = e
                    if attempt == max_retries:
                        logger.warning(
                            f'[Launcher] LLM call exhausted retries '
                            f'(attempt={attempt + 1}/{max_retries + 1}): {e}'
                        )
                        raise
                    logger.info(
                        f'[Launcher] LLM retriable error (attempt={attempt + 1}/'
                        f'{max_retries + 1}), backing off {backoff:.1f}s: {e}'
                    )
                    await _asyncio.sleep(backoff)
                    backoff *= 2
            # Unreachable, but mypy/typing wants an explicit raise path
            if last_exc is not None:
                raise last_exc

        def _patched_init(self, *args, **kwargs):
            _original_init(self, *args, **kwargs)
            # Cache and wrap the per-instance chat.completions.create.
            # After this, every call from LightRAG goes through _create_with_retry.
            self._llm_original_create = self.chat.completions.create
            self.chat.completions.create = _create_with_retry.__get__(
                self, type(self.chat.completions)
            )

        openai.AsyncOpenAI.__init__ = _patched_init
        logger.info(
            f'[Launcher] Wrapped AsyncOpenAI chat.completions.create with retry '
            f'(max_retries={max_retries}, initial_backoff={initial_backoff}s)'
        )
    except Exception as e:
        logger.warning(f'[Launcher] Failed to install LLM retry wrapper: {e}')


def patch_health_monitoring():
    """
    Register health check routes and start health monitoring.
    
    Provides:
    - /health/status - Overall health score and recommendations
    - /health/workers - Detailed worker statistics
    - /health/circuits - Circuit breaker states
    
    Implemented via patch_fastapi_for_health_routes() in knowledge/lightrag_health.py.
    """
    try:
        from knowledge.lightrag_health import patch_fastapi_for_health_routes
        patch_fastapi_for_health_routes()
    except ImportError:
        logger.warning("[Launcher] lightrag_health module not available, health routes disabled")
    except Exception as e:
        logger.warning(f"[Launcher] Failed to setup health monitoring: {e}")


def apply_all_patches():
    """Apply all eCan customizations on top of LightRAG ≥ 1.4.16.

    Order matters: each patch reads env state set by an earlier one.
    """
    logger.info('[Launcher] ==================== Applying Customizations ====================')
    lightrag_version = installed_lightrag_version()

    status, resolved_version = support_status(lightrag_version)
    if status == "not_installed":
        # Every patch below binds to symbols on the lightrag-hku package.
        # Without the package installed, all subsequent imports raise and the
        # launcher dispatch logic never gets a chance to run.
        raise RuntimeError(
            "[Launcher] FATAL: lightrag-hku is not installed. "
            "Install requirements-base.txt before launching the server."
        )
    if status == "below_minimum":
        # Treated as expected behaviour (per CLAUDE.md §6): a 1.4.x rollback is
        # a documented fallback. We log WARNING, not ERROR, and proceed so that
        # operators on a temporary 1.4 rollback still work. The remaining
        # patches (chunker, SSL, confidence scoring) bind to the parts of
        # LightRAG that have been stable since 1.4.10.
        logger.warning(
            f"[Launcher] LightRAG {resolved_version} is below the supported "
            f"minimum ({SUPPORTED_MIN_VERSION}); the legacy 1.4-only monkey "
            f"patches this launcher used to ship have been removed. Schedule "
            f"an upgrade to ≥ 1.4.16 (tested: 1.5.6)."
        )
    elif status == "above_tested":
        # Above 1.5.6 hasn't been validated by eCan. Log WARNING so we don't
        # hide a real bug, but do not refuse to start — upstream owns
        # routing / cancellation / scheduling / capability discovery.
        logger.warning(
            f"[Launcher] LightRAG {resolved_version} is newer than the eCan "
            f"tested maximum (1.5.6). Behaviour regressions are possible. "
            f"Validate before shipping."
        )
    logger.info(
        f"[Launcher] LightRAG {resolved_version}; support_status={status}"
    )

    # Note: Environment variables are already set by parent process
    # (lightrag_server.py::build_env) which loads lightrag.env via
    # config_manager.get_effective_config().

    os.environ['LIGHTRAG_CUSTOM_CHUNKER'] = '1'

    # 0. OpenMP library conflict fix (must be first to prevent SIGABRT crashes)
    # See: https://github.com/intel/tbb/wiki/TBBMalloc#tcmalloc-and-intel-tbb
    patch_openmp_duplicate_fix()

    # 0.5 (mt101 storage dep blocker — removed; lightrag-hku 1.5.6 already
    # lazy-imports storage backends via factory.get_storage_class(), so the
    # blocker never fires. Keep the comment as a tombstone in case upstream
    # switches to eager loading.)

    # 1. Rerank binding conversion FIRST — reads from os.environ which is
    # already populated by the parent process.
    patch_rerank_binding_for_proxy()

    # 2. Custom chunker injection (LightRAG 1.4.10+ natively supports
    # chunking_func).
    patch_lightrag_init()

    # 3. SSL verification control.
    patch_ssl()

    # 4. httpx compat shim for browser-use (independent of LightRAG version).
    patch_httpx_timeout_compat()

    # 4.5. Local/custom MinerU services also require the configured API key.
    patch_mineru_local_bearer_auth()
    patch_docling_bearer_auth()
    patch_manual_retry_to_use_current_parser()

    # 5. Confidence scoring support.
    patch_utils_for_confidence_scoring()

    # 6. Lambda proxy header injection (X-User-Id for per-user accounting).
    patch_openai_client_for_lambda_proxy()

    # 6.5. LLM retry wrapper (exponential backoff on 429 / timeout / connection).
    # LightRAG 1.5.6 has no retry; without this, transient cloud API failures
    # abort the whole document. Disabled via LIGHTRAG_LLM_RETRY=0.
    patch_openai_client_for_retry_on_429()

    # 7. Health monitoring (registers /health/* routes — actual logic lives in
    # knowledge/lightrag_health.py).
    patch_health_monitoring()

    logger.info('[Launcher] ==================== Complete ====================')


def main():
    """Main entry point — starts LightRAG FastAPI app via uvicorn.

    Uses ``create_app()`` + ``uvicorn.run()`` instead of ``runpy.run_module()``.
    The latter replaces the current process, which breaks ``subprocess.Popen``
    management in ``LightragServer.start()`` (the parent process loses its child
    handle).  ``uvicorn.run()`` keeps the child subprocess alive and controllable.
    """
    import uvicorn

    apply_all_patches()

    logger.info(f'[Launcher] Building FastAPI app...')
    try:
        from lightrag.api.lightrag_server import create_app
        # Map non-native LLM/embedding bindings to LightRAG-supported values
        # so the validator inside create_app() accepts them.
        _LIGHTRAG_LLM_SUPPORTED = {'lollms', 'ollama', 'openai', 'azure_openai', 'aws_bedrock', 'gemini'}
        _LIGHTRAG_EMBED_SUPPORTED = _LIGHTRAG_LLM_SUPPORTED | {'jina'}
        _PROVIDER_MAPPING = {
            'ryoais': 'openai', 'ecanai': 'openai', 'anthropic': 'openai', 'deepseek': 'openai',
            'dashscope': 'openai', 'bytedance': 'openai', 'baidu_qianfan': 'openai',
            'zhipuai': 'openai', 'google': 'openai', 'bedrock': 'aws_bedrock',
        }
        for env_key, supported in [('LLM_BINDING', _LIGHTRAG_LLM_SUPPORTED),
                                    ('EMBEDDING_BINDING', _LIGHTRAG_EMBED_SUPPORTED)]:
            val = os.environ.get(env_key, '').lower()
            if val and val not in supported:
                mapped = _PROVIDER_MAPPING.get(val, 'openai')
                logger.info(f"[Launcher] Mapping {env_key} '{val}' -> '{mapped}'")
                os.environ[env_key] = mapped

        from lightrag.api.config import initialize_config
        # force=True: re-parse args after binding mapping has been applied to os.environ.
        # Without force, initialize_config() returns the cached result from first import
        # (before env vars were set in main()).
        args = initialize_config(force=True)
        app = create_app(args)
    except Exception as e:
        logger.error(f'[Launcher] Failed to create FastAPI app: {e}')
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

    # Suppress uvicorn access log (we already log at debug level via our own logger)
    logger.info(f'[Launcher] Starting uvicorn on {args.host}:{args.port}...')
    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=args.log_level.lower(),  # uvicorn accepts lowercase
            access_log=False,
            timeout_keep_alive=30,
        )
    except Exception as e:
        logger.error(f'[Launcher] uvicorn.run() failed: {e}')
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()
