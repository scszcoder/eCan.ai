import ssl
import os
import sys

# Force disable SSL verification globally if requested
if os.environ.get('SSL_VERIFY', 'true').lower() == 'false':
    try:
        _create_unverified_https_context = ssl._create_unverified_context
        ssl._create_default_https_context = _create_unverified_https_context
        print("WARNING: SSL verification disabled globally via monkey patch (ssl._create_default_https_context)")
    except AttributeError:
        pass

# Also patch aiohttp if possible, just in case
try:
    import aiohttp
    # This is harder to patch globally for aiohttp as it uses TCPConnector
    # But setting the env var AIOHTTP_NO_VERIFY_SSL=1 helps if the library supports it
    pass
except ImportError:
    pass

# Add the current directory to sys.path to ensure we can import lightrag
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import and run the actual server
try:
    from lightrag.api.lightrag_server import main
    if __name__ == "__main__":
        main()
except ImportError as e:
    print(f"ERROR: Failed to import lightrag.api.lightrag_server: {e}")
    sys.exit(1)
