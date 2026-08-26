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
7. Health monitoring — registers ``/health/status``, ``/health/workers``,
   ``/health/circuits`` (logic in ``knowledge/lightrag_health.py``).

All patches degrade gracefully: on failure they emit a WARNING and let the
server continue with reduced functionality.  Only ``patch_rerank_binding``
has no fallback (a missing provider is a configuration error).

LightRAG ≥ 1.5 owns routing, cancellation, bounded scheduling, capability
discovery and crash recovery natively, so no router / extraction /
auto-retry patches are needed.
"""

import sys
import os
import ssl
import runpy
import aiohttp

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

    # 5. Confidence scoring support.
    patch_utils_for_confidence_scoring()

    # 6. Lambda proxy header injection (X-User-Id for per-user accounting).
    patch_openai_client_for_lambda_proxy()

    # 7. Health monitoring (registers /health/* routes — actual logic lives in
    # knowledge/lightrag_health.py).
    patch_health_monitoring()

    logger.info('[Launcher] ==================== Complete ====================')


def main():
    """Main entry point"""
    apply_all_patches()
    sys.argv = [sys.executable] + sys.argv[1:]
    logger.info('[Launcher] Starting lightrag.api.lightrag_server...')
    try:
        runpy.run_module('lightrag.api.lightrag_server', run_name='__main__', alter_sys=True)
    except Exception as e:
        logger.error(f'[Launcher] Error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
