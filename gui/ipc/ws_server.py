"""
WebSocket Server for IPC Communication

Provides WebSocket-based transport for web deployment mode.
This allows the React frontend to communicate with the Python backend
over a network connection instead of Qt WebChannel.

Usage:
    # Start server
    python -m gui.ipc.ws_server
    
    # Or programmatically
    from gui.ipc.ws_server import WebSocketServer
    server = WebSocketServer(host="0.0.0.0", port=8765)
    await server.start()
"""

import asyncio
import json
import traceback
from typing import Optional, Dict, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime

from .transport import IPCTransport
from .types import (
    IPCRequest, IPCResponse, 
    create_error_response, create_success_response, create_pending_response
)
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

# Try to import websockets, provide helpful error if not installed
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


@dataclass
class WebSocketConnection:
    """Represents a single WebSocket connection with metadata"""
    websocket: Any  # WebSocketServerProtocol
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    def update_activity(self):
        self.last_activity = datetime.now()


class WebSocketTransport(IPCTransport):
    """WebSocket-based IPC transport for web deployment.
    
    This transport allows the Python backend to communicate with
    browser-based frontends over WebSocket connections.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        """Initialize WebSocket transport.
        
        Args:
            host: Host to bind to (default: all interfaces)
            port: Port to listen on (default: 8765)
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets library is required for WebSocket transport. "
                "Install with: pip install websockets"
            )
        
        self.host = host
        self.port = port
        self._server = None
        self._connections: Dict[str, WebSocketConnection] = {}  # connection_id -> connection
        self._message_handler: Optional[Callable[[str], str]] = None
        self._running = False
        self._server_task: Optional[asyncio.Task] = None
        
    def send_to_frontend(self, message: dict) -> None:
        """Send message to all connected frontends.
        
        For targeted sending, use send_to_connection() instead.
        """
        asyncio.create_task(self._broadcast(message))
    
    async def _broadcast(self, message: dict) -> None:
        """Broadcast message to all connections"""
        if not self._connections:
            logger.warning("[WS] No connections to broadcast to")
            return
            
        message_str = json.dumps(message)
        for conn_id, conn in list(self._connections.items()):
            try:
                await conn.websocket.send(message_str)
            except Exception as e:
                logger.error(f"[WS] Error broadcasting to {conn_id}: {e}")
    
    async def send_to_connection(self, connection_id: str, message: dict) -> bool:
        """Send message to a specific connection.
        
        Args:
            connection_id: The connection to send to
            message: The message dict to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        conn = self._connections.get(connection_id)
        if not conn:
            logger.warning(f"[WS] Connection {connection_id} not found")
            return False
            
        try:
            await conn.websocket.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"[WS] Error sending to {connection_id}: {e}")
            return False
    
    def set_message_handler(self, handler: Callable[[str], str]) -> None:
        """Set the handler for incoming messages"""
        self._message_handler = handler
    
    def start(self) -> None:
        """Start the WebSocket server (non-blocking, creates task)"""
        if self._running:
            logger.warning("[WS] Server already running")
            return
        
        # Create task to run server
        loop = asyncio.get_event_loop()
        self._server_task = loop.create_task(self._run_server())
        logger.info(f"[WS] Server starting on ws://{self.host}:{self.port}")
    
    async def start_async(self) -> None:
        """Start the WebSocket server (async version)"""
        if self._running:
            logger.warning("[WS] Server already running")
            return
        await self._run_server()
    
    def stop(self) -> None:
        """Stop the WebSocket server"""
        self._running = False
        if self._server:
            self._server.close()
        if self._server_task:
            self._server_task.cancel()
        logger.info("[WS] Server stopped")
    
    @property
    def is_connected(self) -> bool:
        """Check if server is running and has connections"""
        return self._running and len(self._connections) > 0
    
    @property
    def connection_count(self) -> int:
        """Get number of active connections"""
        return len(self._connections)
    
    async def _run_server(self) -> None:
        """Main server loop"""
        self._running = True
        
        async with websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
        ) as server:
            self._server = server
            logger.info(f"[WS] Server listening on ws://{self.host}:{self.port}")
            
            # Keep running until stopped
            while self._running:
                await asyncio.sleep(1)
    
    async def _handle_connection(self, websocket) -> None:
        """Handle a new WebSocket connection"""
        connection_id = f"ws_{id(websocket)}_{datetime.now().timestamp()}"
        conn = WebSocketConnection(websocket=websocket)
        self._connections[connection_id] = conn
        
        logger.info(f"[WS] New connection: {connection_id} (total: {len(self._connections)})")
        
        try:
            async for message in websocket:
                conn.update_activity()
                await self._handle_message(connection_id, message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"[WS] Connection closed: {connection_id} - {e}")
        except Exception as e:
            logger.error(f"[WS] Connection error: {connection_id} - {e}")
        finally:
            # Unbind connection from session manager
            try:
                from gui.context.session_manager import SessionManager
                session_manager = SessionManager.get_instance()
                unbound_session = session_manager.unbind_connection(connection_id)
                if unbound_session:
                    logger.info(f"[WS] Unbound connection {connection_id} from session {unbound_session}")
            except Exception as e:
                logger.error(f"[WS] Error unbinding connection {connection_id}: {e}")
            
            del self._connections[connection_id]
            logger.info(f"[WS] Connection removed: {connection_id} (remaining: {len(self._connections)})")
    
    async def _handle_message(self, connection_id: str, message: str) -> None:
        """Handle an incoming message from a connection"""
        try:
            # Log incoming message (truncated)
            truncated = message[:500] + "..." if len(message) > 500 else message
            logger.debug(f"[WS] Received from {connection_id}: {truncated}")
            
            # Use the message handler if set
            if self._message_handler:
                response_str = self._message_handler(message)
            else:
                # Default: route through IPC registry (pass connection_id for session lookup)
                response_str = await self._route_to_handler(message, connection_id)
            
            # Send response back to the same connection
            conn = self._connections.get(connection_id)
            if conn:
                await conn.websocket.send(response_str)
                
        except Exception as e:
            logger.error(f"[WS] Error handling message: {e}\n{traceback.format_exc()}")
            error_response = {
                "id": "error",
                "status": "error",
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e)
                }
            }
            conn = self._connections.get(connection_id)
            if conn:
                await conn.websocket.send(json.dumps(error_response))
    
    async def _route_to_handler(self, message: str, connection_id: Optional[str] = None) -> str:
        """Route message to appropriate IPC handler.
        
        This mirrors the logic in wc_service.py but for WebSocket.
        """
        try:
            data = json.loads(message)
            
            # Check message type
            if 'type' not in data:
                return json.dumps(create_error_response(
                    {'id': 'missing_type', 'method': 'unknown'},
                    'MISSING_TYPE',
                    "Message missing type field"
                ))
            
            # Handle request message
            if data['type'] == 'request':
                return await self._handle_request(IPCRequest(**data), connection_id)
            
            # Unknown message type
            return json.dumps(create_error_response(
                {'id': 'unknown_type', 'method': 'unknown'},
                'UNKNOWN_TYPE',
                f"Unknown message type: {data['type']}"
            ))
            
        except json.JSONDecodeError as e:
            return json.dumps(create_error_response(
                {'id': 'parse_error', 'method': 'unknown'},
                'PARSE_ERROR',
                f"Invalid JSON format: {str(e)}"
            ))
    
    async def _handle_request(self, request: IPCRequest, connection_id: Optional[str] = None) -> str:
        """Handle an IPC request and return response"""
        method = request.get('method')
        if not method:
            return json.dumps(create_error_response(
                request,
                'INVALID_REQUEST',
                "Missing method in request"
            ))
        
        handler_info = IPCHandlerRegistry.get_handler(method)
        if not handler_info:
            return json.dumps(create_error_response(
                request,
                'METHOD_NOT_FOUND',
                f"Unknown method: {method}"
            ))
        
        handler, handler_type = handler_info
        
        try:
            params = request.get('params')
            
            # Set session context for this request (web mode)
            session_id = self._get_session_for_request(request, connection_id)
            
            # Wrapper to set/clear session context in executor thread
            def run_with_context():
                from gui.ipc.context_bridge import set_request_session_id, clear_request_session_id
                try:
                    if session_id:
                        set_request_session_id(session_id)
                    return handler(request, params)
                finally:
                    clear_request_session_id()
            
            # Execute handler (run sync handlers in executor to not block)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, run_with_context)
            
            return json.dumps(response)
            
        except Exception as e:
            logger.error(f"[WS] Handler error for {method}: {e}\n{traceback.format_exc()}")
            return json.dumps(create_error_response(
                request,
                'HANDLER_ERROR',
                f"Error executing handler: {str(e)}"
            ))
    
    def _get_session_for_request(self, request: IPCRequest, connection_id: Optional[str]) -> Optional[str]:
        """Get session ID for a request from various sources"""
        # 1. From connection binding
        if connection_id:
            from gui.context.session_manager import SessionManager
            session_manager = SessionManager.get_instance()
            session_id = session_manager.get_session_id_by_connection(connection_id)
            if session_id:
                return session_id
        
        # 2. From request params
        params = request.get('params', {})
        if isinstance(params, dict) and params.get('session_id'):
            session_id = params['session_id']
            # Bind this connection to the session if not already bound
            if connection_id and session_id:
                from gui.context.session_manager import SessionManager
                session_manager = SessionManager.get_instance()
                if session_manager.bind_connection(connection_id, session_id):
                    logger.info(f"[WS] Bound connection {connection_id} to session {session_id}")
            return session_id
        
        # 3. From request meta
        meta = request.get('meta', {})
        if isinstance(meta, dict) and meta.get('session_id'):
            session_id = meta['session_id']
            # Bind this connection to the session if not already bound
            if connection_id and session_id:
                from gui.context.session_manager import SessionManager
                session_manager = SessionManager.get_instance()
                if session_manager.bind_connection(connection_id, session_id):
                    logger.info(f"[WS] Bound connection {connection_id} to session {session_id}")
            return session_id
        
        return None


# =============================================================================
# Standalone Server Entry Point
# =============================================================================

async def run_standalone_server(host: str = "0.0.0.0", port: int = 8765):
    """Run the WebSocket server standalone (for testing or web deployment)"""
    
    # Import handlers to register them
    import gui.ipc.handlers  # noqa: F401
    import gui.ipc.context_handlers  # noqa: F401
    
    transport = WebSocketTransport(host=host, port=port)
    
    print(f"Starting WebSocket IPC server on ws://{host}:{port}")
    print("Press Ctrl+C to stop")
    
    try:
        await transport.start_async()
    except KeyboardInterrupt:
        print("\nShutting down...")
        transport.stop()


if __name__ == "__main__":
    import sys
    
    host = "0.0.0.0"
    port = 8765
    
    # Parse command line args
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        host = sys.argv[2]
    
    asyncio.run(run_standalone_server(host, port))
