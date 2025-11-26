import sys
import os
import ssl
import runpy
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def apply_patches():
    """Apply runtime patches before loading the main application."""
    # Patch SSL if SSL_VERIFY env var is set to false
    verify_ssl = os.environ.get('SSL_VERIFY', 'true').lower() == 'false'
    
    if verify_ssl:
        print('[LightragLauncher] 🛡️ Disabling SSL verification...')
        
        # Patch 1: global ssl context
        try:
            _create_unverified_https_context = ssl._create_unverified_context
            ssl._create_default_https_context = _create_unverified_https_context
            print('[LightragLauncher] Patched ssl.create_default_context')
        except AttributeError:
            pass
        
        # Patch 2: aiohttp TCPConnector
        try:
            import aiohttp
            original_init = aiohttp.TCPConnector.__init__
            
            def new_init(self, *args, **kwargs):
                # Force ssl=False for all TCPConnectors
                kwargs['ssl'] = False
                original_init(self, *args, **kwargs)
                
            aiohttp.TCPConnector.__init__ = new_init
            print('[LightragLauncher] Patched aiohttp.TCPConnector to force ssl=False')
        except ImportError:
            pass


def main():
    """Main entry point."""
    apply_patches()
    
    # Fix sys.argv: remove the launcher script from argv[0]
    # so the target module sees the correct arguments
    sys.argv = [sys.executable] + sys.argv[1:]
    
    # Run the actual LightRAG server module
    print('[LightragLauncher] Starting lightrag.api.lightrag_server...')
    try:
        runpy.run_module('lightrag.api.lightrag_server', run_name='__main__', alter_sys=True)
    except Exception as e:
        print(f'[LightragLauncher] Error running module: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()