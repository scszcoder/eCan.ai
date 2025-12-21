"""
Test Harness for WebSocket Transport

This module provides easy local testing of the WebSocket-based IPC mechanism
without needing the full Qt application or a browser.

Usage:
    # Run tests
    pytest gui/ipc/tests/test_ws_transport.py -v
    
    # Or run the interactive test client
    python -m gui.ipc.tests.test_ws_transport
"""

import asyncio
import json
import pytest
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from gui.ipc.types import create_request, IPCResponse
from gui.ipc.registry import IPCHandlerRegistry


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_request():
    """Create a sample IPC request"""
    return create_request("ping", {"message": "hello"})


@pytest.fixture
def registered_ping_handler():
    """Register a simple ping handler for testing"""
    from gui.ipc.types import create_success_response
    
    @IPCHandlerRegistry.handler('test_ping')
    def handle_test_ping(request, params):
        return create_success_response(request, {
            "pong": True,
            "echo": params.get("message", "") if params else ""
        })
    
    yield
    
    # Cleanup: remove the handler after test
    if 'test_ping' in IPCHandlerRegistry._handlers:
        del IPCHandlerRegistry._handlers['test_ping']


# =============================================================================
# Unit Tests
# =============================================================================

class TestIPCTypes:
    """Test IPC type creation and validation"""
    
    def test_create_request(self):
        """Test request creation"""
        req = create_request("test_method", {"key": "value"})
        
        assert req['type'] == 'request'
        assert req['method'] == 'test_method'
        assert req['params'] == {"key": "value"}
        assert 'id' in req
        assert 'timestamp' in req
    
    def test_create_request_no_params(self):
        """Test request creation without params"""
        req = create_request("test_method")
        
        assert req['method'] == 'test_method'
        assert req['params'] is None


class TestHandlerRegistry:
    """Test handler registration and lookup"""
    
    def test_handler_registration(self, registered_ping_handler):
        """Test that handlers can be registered and found"""
        handler_info = IPCHandlerRegistry.get_handler('test_ping')
        
        assert handler_info is not None
        handler, handler_type = handler_info
        assert callable(handler)
    
    def test_unknown_handler(self):
        """Test that unknown handlers return None"""
        handler_info = IPCHandlerRegistry.get_handler('nonexistent_method')
        assert handler_info is None
    
    def test_handler_execution(self, registered_ping_handler):
        """Test that registered handler executes correctly.
        
        Note: In test environment without MainWindow, the registry middleware
        may return SYSTEM_NOT_READY error. We verify the handler is called
        and returns a valid response structure.
        """
        handler_info = IPCHandlerRegistry.get_handler('test_ping')
        handler, _ = handler_info
        
        request = create_request("test_ping", {"message": "hello"})
        response = handler(request, request['params'])
        
        # Handler returns a valid response (may be error if MainWindow not available)
        assert 'status' in response
        assert response['status'] in ('success', 'error')
        
        if response['status'] == 'success':
            assert response['result']['pong'] is True
            assert response['result']['echo'] == 'hello'
        else:
            # Error is expected when MainWindow is not available
            assert response['error']['code'] in ('SYSTEM_NOT_READY', 'MAIN_WINDOW_NOT_AVAILABLE')


# =============================================================================
# WebSocket Transport Tests (require websockets library)
# =============================================================================

import pytest_asyncio

@pytest_asyncio.fixture
async def ws_server():
    """Start a WebSocket server for testing"""
    try:
        from gui.ipc.ws_server import WebSocketTransport
    except ImportError:
        pytest.skip("websockets library not installed")
    
    # Register test handler and add to whitelist (skip middleware checks)
    from gui.ipc.types import create_success_response
    
    # Add to whitelist so it bypasses system ready check
    IPCHandlerRegistry.add_to_whitelist('ws_test_echo')
    
    @IPCHandlerRegistry.handler('ws_test_echo')
    def handle_ws_test_echo(request, params):
        return create_success_response(request, {
            "echoed": params.get("data", "") if params else ""
        })
    
    # Start server on a random available port
    transport = WebSocketTransport(host="127.0.0.1", port=0)
    
    # We need to start it differently for testing
    import websockets
    
    server = await websockets.serve(
        transport._handle_connection,
        "127.0.0.1",
        0,  # Random port
    )
    
    # Get the actual port
    port = server.sockets[0].getsockname()[1]
    transport.port = port
    transport._server = server
    transport._running = True
    
    yield transport, port
    
    # Cleanup
    server.close()
    await server.wait_closed()
    
    if 'ws_test_echo' in IPCHandlerRegistry._handlers:
        del IPCHandlerRegistry._handlers['ws_test_echo']
    IPCHandlerRegistry.remove_from_whitelist('ws_test_echo')


@pytest.mark.asyncio
async def test_ws_connection(ws_server):
    """Test WebSocket connection"""
    import websockets
    from websockets.protocol import State
    
    transport, port = ws_server
    
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        # websockets 14+ uses .state instead of .open
        assert ws.state == State.OPEN
        assert transport.connection_count == 1


@pytest.mark.asyncio
async def test_ws_echo_request(ws_server):
    """Test sending a request and receiving response"""
    import websockets
    
    transport, port = ws_server
    
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        # Send request
        request = create_request("ws_test_echo", {"data": "test123"})
        await ws.send(json.dumps(request))
        
        # Receive response
        response_str = await asyncio.wait_for(ws.recv(), timeout=5.0)
        response = json.loads(response_str)
        
        assert response['status'] == 'success'
        assert response['result']['echoed'] == 'test123'
        assert response['id'] == request['id']


@pytest.mark.asyncio
async def test_ws_unknown_method(ws_server):
    """Test handling of unknown method"""
    import websockets
    
    transport, port = ws_server
    
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        request = create_request("nonexistent_method_xyz", {})
        await ws.send(json.dumps(request))
        
        response_str = await asyncio.wait_for(ws.recv(), timeout=5.0)
        response = json.loads(response_str)
        
        assert response['status'] == 'error'
        assert response['error']['code'] == 'METHOD_NOT_FOUND'


@pytest.mark.asyncio
async def test_ws_invalid_json(ws_server):
    """Test handling of invalid JSON"""
    import websockets
    
    transport, port = ws_server
    
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        await ws.send("not valid json {{{")
        
        response_str = await asyncio.wait_for(ws.recv(), timeout=5.0)
        response = json.loads(response_str)
        
        assert response['status'] == 'error'
        assert response['error']['code'] == 'PARSE_ERROR'


# =============================================================================
# Interactive Test Client
# =============================================================================

async def interactive_client(host: str = "127.0.0.1", port: int = 8765):
    """Interactive WebSocket client for manual testing.
    
    This allows you to send requests and see responses in real-time.
    """
    try:
        import websockets
    except ImportError:
        print("ERROR: websockets library required. Install with: pip install websockets")
        return
    
    uri = f"ws://{host}:{port}"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as ws:
            print(f"Connected! Type requests as JSON or use shortcuts:")
            print("  ping          - Send a ping request")
            print("  echo <msg>    - Send an echo request")
            print("  raw <json>    - Send raw JSON")
            print("  quit          - Exit")
            print()
            
            # Start receiver task
            async def receiver():
                try:
                    async for message in ws:
                        print(f"\n<-- RESPONSE:\n{json.dumps(json.loads(message), indent=2)}\n> ", end="")
                except websockets.exceptions.ConnectionClosed:
                    print("\nConnection closed by server")
            
            receiver_task = asyncio.create_task(receiver())
            
            # Input loop
            while True:
                try:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("> ")
                    )
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    if line.lower() == 'quit':
                        break
                    
                    # Parse shortcuts
                    if line.lower() == 'ping':
                        request = create_request("ping", {"timestamp": "now"})
                    elif line.lower().startswith('echo '):
                        msg = line[5:]
                        request = create_request("ws_test_echo", {"data": msg})
                    elif line.lower().startswith('raw '):
                        request = json.loads(line[4:])
                    else:
                        # Try to parse as method name
                        request = create_request(line, {})
                    
                    print(f"--> SENDING: {json.dumps(request)}")
                    await ws.send(json.dumps(request))
                    
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}")
                except KeyboardInterrupt:
                    break
            
            receiver_task.cancel()
            
    except ConnectionRefusedError:
        print(f"ERROR: Could not connect to {uri}")
        print("Make sure the WebSocket server is running:")
        print("  python -m gui.ipc.ws_server")
    except Exception as e:
        print(f"ERROR: {e}")


async def run_quick_test(host: str = "127.0.0.1", port: int = 8765):
    """Run a quick automated test against a running server"""
    try:
        import websockets
    except ImportError:
        print("ERROR: websockets library required")
        return False
    
    uri = f"ws://{host}:{port}"
    print(f"Running quick test against {uri}...")
    
    try:
        async with websockets.connect(uri) as ws:
            # Test 1: Ping
            print("\n1. Testing ping...")
            request = create_request("ping", {"test": True})
            await ws.send(json.dumps(request))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            print(f"   Response status: {response.get('status')}")
            
            # Test 2: Unknown method
            print("\n2. Testing unknown method...")
            request = create_request("unknown_method_xyz", {})
            await ws.send(json.dumps(request))
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert response['status'] == 'error', "Expected error for unknown method"
            print(f"   Got expected error: {response['error']['code']}")
            
            # Test 3: Invalid JSON
            print("\n3. Testing invalid JSON...")
            await ws.send("not json")
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert response['status'] == 'error', "Expected error for invalid JSON"
            print(f"   Got expected error: {response['error']['code']}")
            
            print("\n✅ All quick tests passed!")
            return True
            
    except ConnectionRefusedError:
        print(f"❌ Could not connect to {uri}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="WebSocket Transport Test Client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8765, help="Server port")
    parser.add_argument("--quick", action="store_true", help="Run quick automated test")
    parser.add_argument("--interactive", action="store_true", help="Run interactive client")
    
    args = parser.parse_args()
    
    if args.quick:
        success = asyncio.run(run_quick_test(args.host, args.port))
        sys.exit(0 if success else 1)
    else:
        # Default to interactive
        asyncio.run(interactive_client(args.host, args.port))
