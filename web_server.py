#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan.ai Web Server - Headless Deployment Entry Point

This is the entry point for running eCan.ai as a web server without Qt GUI.
It starts a WebSocket server that serves multiple browser-based frontends.

Usage:
    # Development
    python web_server.py
    
    # Production with uvicorn
    uvicorn web_server:app --host 0.0.0.0 --port 8765
    
    # With environment variables
    ECAN_MODE=web ECAN_WS_PORT=8765 python web_server.py

Environment Variables:
    ECAN_MODE       - Set to 'web' (automatically set by this script)
    ECAN_WS_HOST    - WebSocket host (default: 0.0.0.0)
    ECAN_WS_PORT    - WebSocket port (default: 8765)
    ECAN_LOG_LEVEL  - Logging level (default: INFO)
"""

import os
import sys
import asyncio
import signal
from typing import Optional

# Set deployment mode BEFORE any other imports
os.environ['ECAN_MODE'] = 'web'

# Configure UTF-8 encoding
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def setup_logging():
    """Configure logging for web server mode"""
    from utils.logger_helper import logger_helper as logger
    
    log_level = os.getenv('ECAN_LOG_LEVEL', 'INFO')
    logger.info(f"[WebServer] Logging level: {log_level}")
    return logger


def load_handlers():
    """Load all IPC handlers"""
    print("[WebServer] Loading IPC handlers...")
    
    # Import handlers to register them with the registry
    try:
        import gui.ipc.handlers
        print("[WebServer] ✓ Core handlers loaded")
    except ImportError as e:
        print(f"[WebServer] ⚠ Could not load core handlers: {e}")
    
    try:
        import gui.ipc.context_handlers
        print("[WebServer] ✓ Context handlers loaded")
    except ImportError as e:
        print(f"[WebServer] ⚠ Could not load context handlers: {e}")
    
    try:
        from gui.ipc.w2p_handlers import _ensure_handlers_loaded
        _ensure_handlers_loaded()
        print("[WebServer] ✓ W2P handlers loaded")
    except ImportError as e:
        print(f"[WebServer] ⚠ Could not load w2p handlers: {e}")
    
    # List registered handlers
    from gui.ipc.registry import IPCHandlerRegistry
    handlers = IPCHandlerRegistry.list_handlers()
    total = len(handlers.get('sync', [])) + len(handlers.get('background', []))
    print(f"[WebServer] Total handlers registered: {total}")


def setup_session_manager():
    """Initialize session manager"""
    from gui.context.session_manager import SessionManager
    
    manager = SessionManager.get_instance()
    
    # Configure session timeout (24 hours default)
    from datetime import timedelta
    manager.set_session_timeout(timedelta(hours=24))
    
    # Set up callbacks for logging
    def on_session_created(session_id, context):
        print(f"[WebServer] Session created: {session_id} for user {context.user_id}")
    
    def on_session_destroyed(session_id):
        print(f"[WebServer] Session destroyed: {session_id}")
    
    manager.set_callbacks(on_created=on_session_created, on_destroyed=on_session_destroyed)
    
    print("[WebServer] ✓ Session manager initialized")
    return manager


async def run_websocket_server(host: str, port: int):
    """Run the WebSocket server"""
    from gui.ipc.ws_server import WebSocketTransport
    
    transport = WebSocketTransport(host=host, port=port)
    
    print(f"[WebServer] Starting WebSocket server on ws://{host}:{port}")
    
    try:
        await transport.start_async()
    except asyncio.CancelledError:
        print("[WebServer] Server shutdown requested")
        transport.stop()


async def main_async():
    """Main async entry point"""
    print("=" * 60)
    print("eCan.ai Web Server")
    print("=" * 60)
    print(f"Mode: {os.getenv('ECAN_MODE', 'unknown')}")
    print(f"Python: {sys.version}")
    print("=" * 60)
    
    # Setup
    logger = setup_logging()
    load_handlers()
    session_manager = setup_session_manager()
    
    # Start session cleanup task
    await session_manager.start_cleanup_task()
    
    # Get configuration
    host = os.getenv('ECAN_WS_HOST', '0.0.0.0')
    port = int(os.getenv('ECAN_WS_PORT', '8765'))
    
    print()
    print(f"[WebServer] Server ready at ws://{host}:{port}")
    print("[WebServer] Press Ctrl+C to stop")
    print("-" * 60)
    
    # Run server
    await run_websocket_server(host, port)


def main():
    """Main entry point"""
    # Handle graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def shutdown_handler(signum, frame):
        print("\n[WebServer] Shutdown signal received...")
        for task in asyncio.all_tasks(loop):
            task.cancel()
    
    # Register signal handlers
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print("\n[WebServer] Interrupted by user")
    except asyncio.CancelledError:
        pass
    finally:
        # Cleanup
        print("[WebServer] Cleaning up...")
        
        # Stop session manager cleanup task
        try:
            from gui.context.session_manager import SessionManager
            SessionManager.get_instance().stop_cleanup_task()
        except Exception:
            pass
        
        # Close the loop
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        
        loop.close()
        print("[WebServer] Shutdown complete")


# FastAPI/ASGI app for production deployment with uvicorn
app: Optional[object] = None

def create_asgi_app():
    """Create ASGI app for uvicorn deployment"""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
        import json
        
        app = FastAPI(
            title="eCan.ai Web Server",
            description="WebSocket API for eCan.ai",
            version="1.0.0"
        )
        
        # Load handlers on startup
        @app.on_event("startup")
        async def startup():
            setup_logging()
            load_handlers()
            session_manager = setup_session_manager()
            await session_manager.start_cleanup_task()
            print("[WebServer] FastAPI server started")
        
        @app.on_event("shutdown")
        async def shutdown():
            from gui.context.session_manager import SessionManager
            SessionManager.get_instance().stop_cleanup_task()
            print("[WebServer] FastAPI server stopped")
        
        # WebSocket endpoint
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            
            from gui.ipc.ws_server import WebSocketTransport
            from gui.ipc.registry import IPCHandlerRegistry
            from gui.ipc.types import IPCRequest, create_error_response
            from gui.ipc.context_bridge import set_request_session_id, clear_request_session_id
            from gui.context.session_manager import SessionManager
            
            connection_id = f"ws_{id(websocket)}_{asyncio.get_event_loop().time()}"
            print(f"[WebServer] WebSocket connected: {connection_id}")
            
            try:
                while True:
                    data = await websocket.receive_text()
                    
                    try:
                        message = json.loads(data)
                        
                        if message.get('type') == 'request':
                            method = message.get('method')
                            params = message.get('params', {})
                            
                            # Get session ID from various sources
                            session_id = None
                            if isinstance(params, dict):
                                session_id = params.get('session_id')
                            if not session_id:
                                meta = message.get('meta', {})
                                if isinstance(meta, dict):
                                    session_id = meta.get('session_id')
                            if not session_id:
                                session_id = SessionManager.get_instance().get_session_id_by_connection(connection_id)
                            
                            # Get handler
                            handler_info = IPCHandlerRegistry.get_handler(method)
                            if not handler_info:
                                response = create_error_response(
                                    message,
                                    'METHOD_NOT_FOUND',
                                    f"Unknown method: {method}"
                                )
                            else:
                                handler, _ = handler_info
                                
                                # Execute with session context
                                def run_handler():
                                    try:
                                        if session_id:
                                            set_request_session_id(session_id)
                                        return handler(message, params)
                                    finally:
                                        clear_request_session_id()
                                
                                loop = asyncio.get_event_loop()
                                response = await loop.run_in_executor(None, run_handler)
                            
                            await websocket.send_text(json.dumps(response))
                        else:
                            await websocket.send_text(json.dumps({
                                'id': message.get('id', 'unknown'),
                                'status': 'error',
                                'error': {'code': 'UNKNOWN_TYPE', 'message': f"Unknown message type"}
                            }))
                            
                    except json.JSONDecodeError as e:
                        await websocket.send_text(json.dumps({
                            'id': 'parse_error',
                            'status': 'error',
                            'error': {'code': 'PARSE_ERROR', 'message': str(e)}
                        }))
                        
            except WebSocketDisconnect:
                print(f"[WebServer] WebSocket disconnected: {connection_id}")
            except Exception as e:
                print(f"[WebServer] WebSocket error: {e}")
            finally:
                # Unbind connection from session
                SessionManager.get_instance().unbind_connection(connection_id)
        
        # Health check endpoint
        @app.get("/health")
        async def health_check():
            from gui.context.session_manager import SessionManager
            return {
                "status": "healthy",
                "mode": "web",
                "sessions": SessionManager.get_instance().get_session_count()
            }
        
        # Serve static frontend files (if available)
        frontend_dist = os.path.join(os.path.dirname(__file__), 'gui_v2', 'dist')
        if os.path.exists(frontend_dist):
            app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
            print(f"[WebServer] Serving frontend from {frontend_dist}")
        
        return app
        
    except ImportError as e:
        print(f"[WebServer] FastAPI not available: {e}")
        print("[WebServer] Install with: pip install fastapi uvicorn")
        return None


# Create ASGI app for uvicorn
try:
    app = create_asgi_app()
except Exception as e:
    print(f"[WebServer] Could not create ASGI app: {e}")
    app = None


if __name__ == "__main__":
    main()
