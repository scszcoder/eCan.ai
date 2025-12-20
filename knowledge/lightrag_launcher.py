"""
LightRAG Launcher with Module Replacement

Combines:
1. Module replacement for Excel extraction (document_routes_custom)
2. Essential patches for chunker injection
3. SSL patch
4. Stop controller for immediate cancellation
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
    """Replace document_routes with custom version"""
    logger.info("[Launcher] Replacing document_routes...")
    
    try:
        # Detect environment
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        custom_module_path = os.path.join(base_path, 'third_party', 'lightrag_custom')
        
        if not os.path.exists(custom_module_path):
            logger.warning(f"[Launcher] Custom module not found: {custom_module_path}")
            return
        
        sys.path.insert(0, custom_module_path)
        
        import document_routes_custom
        sys.modules['lightrag.api.routers.document_routes'] = document_routes_custom
        
        import lightrag.api.routers
        lightrag.api.routers.document_routes = document_routes_custom
        
        logger.info("[Launcher] ✅ document_routes replaced (Excel空列清理 + Stop检查)")
        
    except Exception as e:
        logger.error(f"[Launcher] ❌ Module replacement failed: {e}")


def patch_lightrag_init():
    """Patch LightRAG.__init__ to inject custom chunker"""
    logger.info("[Launcher] Patching LightRAG.__init__...")
    
    use_custom_chunker = os.getenv('LIGHTRAG_CUSTOM_CHUNKER') == '1'
    if not use_custom_chunker:
        return
    
    try:
        from knowledge.advanced_chunker import universal_chunking_func
        from lightrag import LightRAG
        
        original_init = LightRAG.__init__
        
        def patched_init(self, *args, **kwargs):
            logger.info("[Launcher] ✅ Injecting custom chunker")
            kwargs['chunking_func'] = universal_chunking_func
            original_init(self, *args, **kwargs)
        
        LightRAG.__init__ = patched_init
        logger.info("[Launcher] ✅ LightRAG.__init__ patched")
        
    except Exception as e:
        logger.error(f"[Launcher] ❌ Patch failed: {e}")


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
    """Replace extract_entities with custom version that supports immediate cancellation"""
    logger.info("[Launcher] Replacing extract_entities with cancellable version...")
    
    try:
        from lightrag import operate
        from operate_custom import extract_entities_with_cancellation
        
        # Replace the function in the operate module
        operate.extract_entities = extract_entities_with_cancellation
        
        # CRITICAL: Also replace in lightrag.lightrag module where it's imported directly
        # The lightrag.py file does: from lightrag.operate import extract_entities
        # So we need to patch the reference there too
        try:
            from lightrag import lightrag as lightrag_module
            lightrag_module.extract_entities = extract_entities_with_cancellation
            logger.info("[Launcher] ✅ Also patched lightrag.lightrag.extract_entities")
        except Exception as e:
            logger.warning(f"[Launcher] Could not patch lightrag.lightrag: {e}")
        
        logger.info("[Launcher] ✅ extract_entities replaced with cancellable version")
        
    except Exception as e:
        logger.error(f"[Launcher] ❌ extract_entities replacement failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


def apply_all_patches():
    """Apply all customizations"""
    logger.info('[Launcher] ==================== Applying Customizations ====================')
    
    os.environ['LIGHTRAG_CUSTOM_CHUNKER'] = '1'
    
    replace_document_routes()  # Excel空列清理 + Stop检查 + 立即取消
    patch_lightrag_init()       # 自定义分块器
    patch_ssl()                 # SSL
    patch_extract_entities_for_cancellation()  # 立即取消支持
    
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
