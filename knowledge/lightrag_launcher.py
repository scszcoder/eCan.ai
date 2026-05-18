"""
LightRAG Launcher with Module Replacement

Optimized for LightRAG 1.4.10+:
1. Module replacement for Excel extraction (document_routes_custom)
2. Custom chunker injection (官方已支持 chunking_func 参数)
3. SSL patch
4. Extract entities immediate cancellation (立即停止补丁)
5. HTTP clients cancellation support
6. Rerank binding conversion
7. Confidence scoring support

Note: LightRAG 1.4.10+ has /cancel_pipeline API, but it doesn't stop queued documents.
Our patch provides true immediate cancellation by replacing extract_entities function.
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

from utils.logger_helper import logger_helper as logger

# Re-export stop controller for external access
from knowledge.stop_controller import (
    StopController,
    get_stop_controller,
    request_stop,
    is_stop_requested,
    reset_stop,
)


# ==================== Module Replacement ====================

def replace_document_routes():
    """Replace document_routes with custom version.

    Asserts the swap took effect — without this our Excel cleanup and stop-
    controller checkpoints are inert.
    """
    logger.info("[Launcher] Replacing document_routes...")

    # Detect environment
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    custom_module_path = os.path.join(base_path, 'third_party', 'lightrag_custom')

    if not os.path.exists(custom_module_path):
        raise RuntimeError(
            f"[Launcher] FATAL: custom module path missing: {custom_module_path}. "
            f"This is required for the document_routes replacement."
        )

    sys.path.insert(0, custom_module_path)

    import document_routes_custom
    sys.modules['lightrag.api.routers.document_routes'] = document_routes_custom

    import lightrag.api.routers
    lightrag.api.routers.document_routes = document_routes_custom

    # Assertion: swap must be visible from both binding points.
    assert sys.modules['lightrag.api.routers.document_routes'] is document_routes_custom, \
        "[Launcher] FATAL: sys.modules swap of document_routes did not stick"
    assert lightrag.api.routers.document_routes is document_routes_custom, \
        "[Launcher] FATAL: lightrag.api.routers.document_routes attr swap did not stick"

    logger.info("[Launcher] ✅ document_routes replaced (Excel cleanup + Stop checkpoints)")


def patch_lightrag_init():
    """Inject custom chunker into LightRAG initialization
    
    LightRAG 1.4.10+ natively supports chunking_func parameter.
    This patch simply injects our custom chunker when enabled.
    """
    use_custom_chunker = os.getenv('LIGHTRAG_CUSTOM_CHUNKER') == '1'
    if not use_custom_chunker:
        logger.info("[Launcher] Custom chunker disabled, skipping injection")
        return
    
    try:
        from knowledge.advanced_chunker import universal_chunking_func
        from lightrag import LightRAG
        
        # LightRAG 1.4.10+ natively supports chunking_func parameter
        # We just need to inject it during initialization
        original_init = LightRAG.__init__
        
        def patched_init(self, *args, **kwargs):
            # Inject custom chunker if not already provided
            if 'chunking_func' not in kwargs:
                logger.info("[Launcher] ✅ Injecting custom chunker")
                kwargs['chunking_func'] = universal_chunking_func
            
            original_init(self, *args, **kwargs)
        
        LightRAG.__init__ = patched_init
        logger.info("[Launcher] ✅ LightRAG.__init__ patched for custom chunker")
        
    except Exception as e:
        logger.error(f"[Launcher] ❌ Chunker injection failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


def patch_ssl():
    """Patch SSL if needed"""
    verify_ssl = os.environ.get('SSL_VERIFY', 'true').lower() == 'false'
    
    if not verify_ssl:
        return
    
    logger.info('[Launcher] 🛡️ Disabling SSL verification...')
    
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
        logger.info('[Launcher] Patched ssl')
    except:
        pass
    
    try:
        original_init = aiohttp.TCPConnector.__init__
        def new_init(self, *args, **kwargs):
            kwargs['ssl'] = False
            original_init(self, *args, **kwargs)
        aiohttp.TCPConnector.__init__ = new_init
        logger.info('[Launcher] Patched aiohttp')
    except:
        pass


def patch_extract_entities_for_cancellation():
    """Replace extract_entities with custom version that supports immediate cancellation.

    Hard-fails on startup if either binding point is missing — these are easy
    to silently break across LightRAG upgrades, and a no-op patch means the
    user's cancel button does nothing in production.
    """
    logger.info("[Launcher] Replacing extract_entities with cancellable version...")

    from lightrag import operate
    from lightrag import lightrag as lightrag_module
    from third_party.lightrag_custom.operate_custom import extract_entities_with_cancellation

    # Assertion 1: both binding points must exist BEFORE patching, otherwise the
    # upstream layout changed and our patch is about to silently no-op.
    if not hasattr(operate, "extract_entities"):
        raise RuntimeError(
            "[Launcher] FATAL: lightrag.operate.extract_entities missing — "
            "LightRAG upgrade likely removed/renamed it. Cancellation patch "
            "cannot apply. Review third_party/lightrag_custom/operate_custom.py."
        )
    if not hasattr(lightrag_module, "extract_entities"):
        raise RuntimeError(
            "[Launcher] FATAL: lightrag.lightrag.extract_entities missing — "
            "upstream stopped re-exporting it from the lightrag module. Cancel "
            "button will not work without further changes."
        )

    operate.extract_entities = extract_entities_with_cancellation
    lightrag_module.extract_entities = extract_entities_with_cancellation

    # Assertion 2: confirm the replacement stuck (catches descriptor/property
    # weirdness that could quietly reject the assignment).
    assert operate.extract_entities is extract_entities_with_cancellation, \
        "[Launcher] FATAL: operate.extract_entities assignment did not take effect"
    assert lightrag_module.extract_entities is extract_entities_with_cancellation, \
        "[Launcher] FATAL: lightrag.lightrag.extract_entities assignment did not take effect"

    logger.info("[Launcher] ✅ extract_entities replaced (both operate + lightrag bindings)")


def patch_auto_retry_prevention():
    """Patch LightRAG to prevent auto-retry of user-cancelled documents.

    Asserts that LightRAG._validate_and_fix_document_consistency still exists
    before patching — without that method our metadata-flag-based cancellation
    is bypassed and cancelled docs get retried on the next startup.
    """
    logger.info("[Launcher] Applying auto-retry prevention patch...")

    from lightrag import LightRAG
    from third_party.lightrag_custom.lightrag_patch import (
        apply_lightrag_patch,
        patched_validate_and_fix_document_consistency,
    )

    if not hasattr(LightRAG, "_validate_and_fix_document_consistency"):
        raise RuntimeError(
            "[Launcher] FATAL: LightRAG._validate_and_fix_document_consistency "
            "missing — upstream rename. User-cancelled documents will get "
            "auto-retried. Review third_party/lightrag_custom/lightrag_patch.py."
        )

    if not apply_lightrag_patch():
        raise RuntimeError("[Launcher] FATAL: apply_lightrag_patch() returned False")

    assert LightRAG._validate_and_fix_document_consistency is patched_validate_and_fix_document_consistency, \
        "[Launcher] FATAL: _validate_and_fix_document_consistency replacement did not stick"

    logger.info("[Launcher] ✅ Auto-retry prevention patch applied successfully")


def patch_http_clients_for_cancellation():
    """Patch HTTP clients (Ollama, OpenAI, httpx) to register for cancellation.
    
    This allows us to close HTTP connections immediately when cancel is requested.
    Works for both local Ollama and cloud APIs (OpenAI, Claude, DeepSeek, etc.)
    """
    logger.info("[Launcher] Patching HTTP clients for cancellation support...")
    
    from third_party.lightrag_custom.operate_custom import register_http_client
    
    # Patch Ollama AsyncClient
    try:
        import ollama
        
        original_ollama_init = ollama.AsyncClient.__init__
        
        def patched_ollama_init(self, *args, **kwargs):
            original_ollama_init(self, *args, **kwargs)
            # Register this client for potential cancellation
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(register_http_client(self))
                else:
                    loop.run_until_complete(register_http_client(self))
            except Exception as e:
                logger.debug(f"[Launcher] Could not register Ollama client: {e}")
        
        ollama.AsyncClient.__init__ = patched_ollama_init
        logger.info("[Launcher] ✅ Ollama AsyncClient patched")
        
    except ImportError:
        logger.debug("[Launcher] Ollama not installed, skipping patch")
    except Exception as e:
        logger.warning(f"[Launcher] Could not patch Ollama AsyncClient: {e}")
    
    # Patch OpenAI AsyncOpenAI (used by OpenAI, Azure, and compatible APIs)
    try:
        from openai import AsyncOpenAI
        
        original_openai_init = AsyncOpenAI.__init__
        
        def patched_openai_init(self, *args, **kwargs):
            original_openai_init(self, *args, **kwargs)
            # Register this client for potential cancellation
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(register_http_client(self))
                else:
                    loop.run_until_complete(register_http_client(self))
            except Exception as e:
                logger.debug(f"[Launcher] Could not register OpenAI client: {e}")
        
        AsyncOpenAI.__init__ = patched_openai_init
        logger.info("[Launcher] ✅ OpenAI AsyncOpenAI patched")
        
    except ImportError:
        logger.debug("[Launcher] OpenAI not installed, skipping patch")
    except Exception as e:
        logger.warning(f"[Launcher] Could not patch OpenAI AsyncOpenAI: {e}")
    
    # Patch httpx AsyncClient (used by many APIs including Anthropic)
    try:
        import httpx
        
        original_httpx_init = httpx.AsyncClient.__init__
        
        def patched_httpx_init(self, *args, **kwargs):
            original_httpx_init(self, *args, **kwargs)
            # Register this client for potential cancellation
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(register_http_client(self))
                else:
                    loop.run_until_complete(register_http_client(self))
            except Exception as e:
                logger.debug(f"[Launcher] Could not register httpx client: {e}")
        
        httpx.AsyncClient.__init__ = patched_httpx_init
        logger.info("[Launcher] ✅ httpx AsyncClient patched")

        # Compatibility shim: httpx >= 0.20 renamed TimeoutError → TimeoutException.
        # browser-use still references httpx.TimeoutError in its except clauses;
        # without this alias every LLM call fails with AttributeError.
        if not hasattr(httpx, 'TimeoutError'):
            httpx.TimeoutError = httpx.TimeoutException
            logger.info("[Launcher] ✅ httpx.TimeoutError alias added (httpx compat shim for browser-use)")
        
    except ImportError:
        logger.debug("[Launcher] httpx not installed, skipping patch")
    except Exception as e:
        logger.warning(f"[Launcher] Could not patch httpx AsyncClient: {e}")


def patch_utils_for_confidence_scoring():
    """Patch utils.generate_reference_list_from_chunks to include scores for confidence scoring.

    Asserts upstream still has the target function — silent-no-op here would
    disable the confidence score gate in our Q&A prompt Step 3.
    """
    logger.info("[Launcher] Patching utils for confidence scoring...")

    from lightrag import utils as _lr_utils
    from utils_custom import (
        patch_generate_reference_list_from_chunks,
        generate_reference_list_from_chunks_with_scores,
    )

    if not hasattr(_lr_utils, "generate_reference_list_from_chunks"):
        raise RuntimeError(
            "[Launcher] FATAL: lightrag.utils.generate_reference_list_from_chunks "
            "missing — upstream rename. Confidence scoring will lose its score "
            "input. Review third_party/lightrag_custom/utils_custom.py."
        )

    if not patch_generate_reference_list_from_chunks():
        raise RuntimeError("[Launcher] FATAL: patch_generate_reference_list_from_chunks() returned False")

    assert _lr_utils.generate_reference_list_from_chunks is generate_reference_list_from_chunks_with_scores, \
        "[Launcher] FATAL: generate_reference_list_from_chunks replacement did not stick"

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
    """
    proxy_host = os.environ.get('LLM_BINDING_HOST', '')
    if not proxy_host or 'lambda-url' not in proxy_host and 'execute-api' not in proxy_host:
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
    
    This provides:
    - /health/status - Overall health score and recommendations
    - /health/workers - Detailed worker statistics
    - /health/circuits - Circuit breaker states
    
    Consolidated in knowledge/lightrag_health.py
    """
    logger.info("[Launcher] Setting up health monitoring...")


def apply_all_patches():
    """Apply all customizations"""
    logger.info('[Launcher] ==================== Applying Customizations ====================')
    
    # Note: Environment variables are already set by parent process (lightrag_server.py::build_env)
    # which loads lightrag.env via config_manager.get_effective_config()
    
    os.environ['LIGHTRAG_CUSTOM_CHUNKER'] = '1'
    
    # Apply rerank binding conversion FIRST
    # This reads from os.environ which is already populated by parent process
    patch_rerank_binding_for_proxy()           # Rerank binding 转换支持
    
    # 1. Replace document_routes (Excel空列清理 + Stop检查)
    replace_document_routes()
    
    # 2. Inject custom chunker (LightRAG 1.4.10+ 官方支持 chunking_func)
    patch_lightrag_init()
    
    # 3. SSL verification control (官方未实现)
    patch_ssl()
    
    # 4. Extract entities immediate cancellation (官方未完全实现)
    # Note: LightRAG 1.4.10+ has /cancel_pipeline API, but it doesn't stop queued documents
    patch_extract_entities_for_cancellation()
    
    # 5. Auto-retry prevention for user-cancelled documents (官方未实现)
    # Note: LightRAG auto-retries FAILED documents, even when user manually cancelled
    patch_auto_retry_prevention()
    
    # 6. HTTP clients cancellation support (官方未实现)
    # Note: LightRAG 1.4.10+ has /cancel_pipeline API, but HTTP clients still need patching
    patch_http_clients_for_cancellation()
    
    # 7. Confidence scoring support (官方未实现)
    patch_utils_for_confidence_scoring()

    # 8. Lambda proxy header injection (inject X-User-Id for per-user accounting)
    patch_openai_client_for_lambda_proxy()

    # 9. Health monitoring with circuit breaker (防假死监控)
    # Provides /health/status, /health/workers, /health/circuits endpoints
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
