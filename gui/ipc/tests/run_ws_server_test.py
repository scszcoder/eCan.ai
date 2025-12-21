"""
Simple WebSocket Server Test Runner

This script starts the WebSocket server in a minimal way for testing,
without requiring the full Qt application or MainWindow.

Usage:
    python gui/ipc/tests/run_ws_server_test.py
    
Then in another terminal:
    python gui/ipc/tests/test_ws_transport.py --quick
    # or
    python gui/ipc/tests/test_ws_transport.py --interactive
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

# Set up minimal logging
from utils.logger_helper import logger_helper as logger


def register_test_handlers():
    """Register some test handlers that don't require MainWindow"""
    from gui.ipc.registry import IPCHandlerRegistry
    from gui.ipc.types import create_success_response
    from datetime import datetime
    
    @IPCHandlerRegistry.handler('ping')
    def handle_ping(request, params):
        """Simple ping handler for testing"""
        return create_success_response(request, {
            "pong": True,
            "timestamp": datetime.now().isoformat(),
            "params_received": params
        })
    
    @IPCHandlerRegistry.handler('echo')
    def handle_echo(request, params):
        """Echo back whatever is sent"""
        return create_success_response(request, {
            "echoed": params
        })
    
    @IPCHandlerRegistry.handler('get_server_info')
    def handle_get_server_info(request, params):
        """Return server information"""
        return create_success_response(request, {
            "mode": "websocket_test",
            "python_version": sys.version,
            "handlers_registered": list(IPCHandlerRegistry._handlers.keys())
        })
    
    print(f"Registered test handlers: ping, echo, get_server_info")
    print(f"Total handlers available: {len(IPCHandlerRegistry._handlers)}")


async def main():
    """Main entry point"""
    print("=" * 60)
    print("WebSocket IPC Server - Test Mode")
    print("=" * 60)
    
    # Check for websockets library
    try:
        import websockets
        print(f"✓ websockets library version: {websockets.__version__}")
    except ImportError:
        print("✗ websockets library not found!")
        print("  Install with: pip install websockets")
        sys.exit(1)
    
    # Register test handlers
    register_test_handlers()
    
    # Import and start server
    from gui.ipc.ws_server import WebSocketTransport
    
    host = "127.0.0.1"
    port = 8765
    
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    
    transport = WebSocketTransport(host=host, port=port)
    
    print()
    print(f"Starting server on ws://{host}:{port}")
    print()
    print("Test commands:")
    print(f"  python gui/ipc/tests/test_ws_transport.py --quick --port {port}")
    print(f"  python gui/ipc/tests/test_ws_transport.py --interactive --port {port}")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    try:
        await transport.start_async()
    except KeyboardInterrupt:
        print("\nShutting down...")
        transport.stop()


if __name__ == "__main__":
    asyncio.run(main())
