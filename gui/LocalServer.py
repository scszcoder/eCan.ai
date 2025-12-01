import threading
import asyncio
import sys
import os
import traceback
import uuid
import json
import socket
import time
from starlette.applications import Starlette
import typing

from utils.logger_helper import logger_helper as logger
from utils.gui_dispatch import run_on_main_thread

if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow

from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Route, Mount
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from agent.mcp.server.server import (
        handle_sse, sse_handle_messages, meca_mcp_server,
        meca_sse, meca_streamable_http, handle_streamable_http,
        session_manager, set_server_main_win
    )

# ==================== Environment Detection and Conditional Imports ====================

class MCPServerConfig:
    """Manages environment configuration and safely imports modules."""

    def __init__(self):
        self.is_frozen = getattr(sys, 'frozen', False)
        self.is_development = not self.is_frozen

        try:
            self.handle_sse = handle_sse
            self.sse_handle_messages = sse_handle_messages
            self.meca_mcp_server = meca_mcp_server
            self.meca_sse = meca_sse
            self.meca_streamable_http = meca_streamable_http
            self.handle_streamable_http = handle_streamable_http
            self.session_manager = session_manager
            self.set_server_main_win = set_server_main_win
            logger.info("✅ MCP modules imported successfully")
        except ImportError as e:
            logger.error(f"❌ Failed to import MCP modules: {e}. MCP features will be disabled.")

    def has_mcp_support(self):
        """Checks if essential MCP functionality is supported."""
        return self.session_manager is not None and self.handle_sse is not None

# Create a global instance for MCP server configuration and modules
mcp_server_config = MCPServerConfig()
response_dict = {}
IMAGE_FOLDER = os.path.abspath("run_images")  # Ensure this is your intended path
base_dir = getattr(sys, '_MEIPASS', os.getcwd())

static_dir = os.path.join(base_dir, 'agent', 'agent_files')
if not os.path.isdir(static_dir):
    # Handle path differences between development and bundled app: fallback to relative path
    alt_dir = os.path.join(os.getcwd(), 'agent', 'agent_files')
    if os.path.isdir(alt_dir):
        static_dir = alt_dir

# Endpoint to serve images
class RequestHandlers:
    """Encapsulates all request handling logic"""

    def __init__(self, main_win: 'MainWindow'):
        self.main_win = main_win

    async def serve_image(self, request):
        filename = request.path_params['filename']
        file_path = os.path.join(IMAGE_FOLDER, filename)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return JSONResponse({"error": "File not found."}, status_code=404)
    
    async def serve_avatar(self, request):
        """Serve avatar files (images and videos) from absolute path"""
        # Get file path from query parameter
        file_path = request.query_params.get('path', '')
        
        if not file_path:
            return JSONResponse({"error": "Missing 'path' parameter"}, status_code=400)
        
        # Security check: ensure file exists and is readable
        if not os.path.isfile(file_path):
            logger.warning(f"Avatar file not found: {file_path}")
            return JSONResponse({"error": "File not found"}, status_code=404)
        
        # Check if file is in allowed directories (resource/avatars)
        abs_path = os.path.abspath(file_path)
        allowed_dirs = [
            os.path.abspath('resource/avatars'),
            os.path.abspath(os.path.join(base_dir, 'resource/avatars'))
        ]
        
        if not any(abs_path.startswith(allowed_dir) for allowed_dir in allowed_dirs):
            logger.warning(f"Avatar file outside allowed directories: {file_path}")
            return JSONResponse({"error": "Access denied"}, status_code=403)
        
        return FileResponse(file_path)

    async def gen_feedbacks(self, request):
        logger.info("serving gen_feedbacks.....")
        mids = request.query_params.get('mids', "-1")
        logger.info(f"mids: {mids}")
        data = run_on_main_thread(lambda: self.main_win.genFeedbacks(mids))
        return JSONResponse(data, status_code=200)

    async def get_mission_reports(self, request):
        start_date = request.query_params.get('start_date', "-1")
        end_date = request.query_params.get('end_date', "-1")
        data = run_on_main_thread(lambda: self.main_win.getRPAReports(start_date, end_date))
        return JSONResponse(data, status_code=200)

    async def post_data(self, request):
        incoming_data = await request.json()
        logger.info(f"Received data: {incoming_data}")
        task_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        response_dict[task_id] = future
        run_on_main_thread(lambda: self.main_win.task_queue.put({
            "task_id": task_id,
            "data": incoming_data
        }))
        result = await asyncio.wait_for(future, timeout=30)
        return JSONResponse({"status": "success", "result": result})

    async def stream(self, request):
        async def event_stream():
            while True:
                await asyncio.sleep(1)
                yield f"data: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def sync_bots_missions(self, request):
        try:
            incoming_data = await request.json()
            logger.info(f"sync_bots_missions Received data: {incoming_data}")
            b_emails = incoming_data.get('bots', [])
            minfos = incoming_data.get('missions', [])
            m_asin_srcs = []
            for minfo in minfos:
                infos = minfo.split("|")
                m_asin_srcs.append({"asin": infos[0].strip(), "src": infos[1].strip()})
            bots_data = self.main_win.bot_service.find_bots_by_emails(b_emails)
            missions_data = self.main_win.mission_service.find_missions_by_asin_srcs(m_asin_srcs)
            result = {"bots": bots_data, "missions": missions_data}
            return JSONResponse({"status": "success", "result": result}, status_code=200)
        except Exception as e:
            ex_stat = f"ErrorFetchSchedule: {traceback.format_exc()} {str(e)}"
            logger.error(ex_stat)
            return JSONResponse({"status": "failure", "result": ex_stat}, status_code=500)

    async def get_skill_graph(self, request):
        # Default file path if not provided in query
        skg_file = request.query_params.get('file', 'skills/skill_graph.json')
        if not os.path.exists(skg_file):
            return JSONResponse({"error": f"Skill graph file not found: {skg_file}"}, status_code=404)

        try:
            with open(skg_file, "r", encoding="utf-8") as skf:
                skill_graph = json.load(skf)
            return JSONResponse(skill_graph)
        except Exception as e:
            logger.error(f"Error loading skill graph: {e}")
            return JSONResponse({"error": "Failed to load or parse skill graph."}, status_code=500)

    async def save_skill_graph(self, request):
        skg_file = request.query_params.get('file', 'skills/skill_graph.json')
        try:
            skill_graph = await request.json()
            with open(skg_file, "w") as outfile:
                json.dump(skill_graph, outfile, indent=4)
            return JSONResponse({"status": "success"}, status_code=200)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON in request body."}, status_code=400)
        except Exception as e:
            error_message = f"ErrorSaveSkillGraph: {traceback.format_exc()} {str(e)}"
            logger.error(error_message)
            return JSONResponse({"error": "Failed to save skill graph."}, status_code=500)


    async def initialize(self, request):
        # Perform whatever server-side initialization you want
        logger.info("initialize() called")
        response = {
            "protocolVersion": "1.0",
            "serverCapabilities": {}
        }
        return JSONResponse(response, status_code=200)


async def health_check(request):
    """Minimal health check endpoint"""
    logger.debug("health_check status returned................")
    return JSONResponse({"status": "ok"})


# Wrap the raw ASGI handler for POST
# messages_router = Router([
#     Route("/", endpoint=sse_handle_messages, methods=["POST"])
# ])
#
# sse_router = Router([
#     Route("/", endpoint=handle_sse, methods=["GET"])
# ==================== MCP Route Handling ====================
class MCPHandler:
    """MCP request handler."""

    _session_manager_initialized = False
    _session_manager_instance = None
    _session_manager_context = None

    @staticmethod
    async def cleanup():
        """Clean up MCP session manager resources."""
        try:
            if MCPHandler._session_manager_context:
                logger.info("🧹 [MCP] Cleaning up session manager context...")
                # Avoid __aexit__ in a different task - just reset the reference
                # The context manager will be cleaned up when the original task exits
                MCPHandler._session_manager_context = None
                logger.info("✅ [MCP] Session manager context cleaned up")
        except Exception as e:
            logger.debug(f"⚠️  [MCP] Error cleaning up session manager context: {e}")
        
        try:
            if MCPHandler._session_manager_instance:
                logger.info("🧹 [MCP] Cleaning up session manager instance...")
                # Reset the instance
                MCPHandler._session_manager_instance = None
                logger.info("✅ [MCP] Session manager instance cleaned up")
        except Exception as e:
            logger.warning(f"⚠️  [MCP] Error cleaning up session manager instance: {e}")
        
        # Reset initialization flag
        MCPHandler._session_manager_initialized = False
        logger.info("✅ [MCP] Handler cleanup completed")

    @staticmethod
    async def ensure_session_manager_initialized():
        """Ensures the session_manager is properly initialized."""
        if not MCPHandler._session_manager_initialized and mcp_server_config.session_manager:
            try:
                logger.info("🔧 [MCP] Initializing session manager...")
                from agent.mcp.server.server import StreamableHTTPSessionManager
                MCPHandler._session_manager_instance = StreamableHTTPSessionManager(
                    app=mcp_server_config.meca_mcp_server,
                    event_store=None,
                    json_response=True
                )

                # Initialize the new instance
                MCPHandler._session_manager_context = MCPHandler._session_manager_instance.run()
                await MCPHandler._session_manager_context.__aenter__()
                MCPHandler._session_manager_initialized = True
                logger.info("✅ [MCP] Session manager initialized successfully")
            except Exception as e:
                logger.error(f"❌ [MCP] Failed to initialize session manager: {e}")
                logger.error(f"❌ [MCP] Traceback: {traceback.format_exc()}")
                # Mark as attempted even if initialization fails, to avoid retries
                MCPHandler._session_manager_initialized = True

    @staticmethod
    async def handle_request(scope, receive, send):
        """Handles MCP requests."""
        if mcp_server_config.has_mcp_support():
            # Ensure session_manager is initialized
            await MCPHandler.ensure_session_manager_initialized()

            try:
                # Use our own session manager instance
                if MCPHandler._session_manager_instance:
                    await MCPHandler._session_manager_instance.handle_request(scope, receive, send)
                else:
                    # Fallback to the original session_manager if no instance exists
                    await mcp_server_config.session_manager.handle_request(scope, receive, send)
            except RuntimeError as e:
                if "Task group is not initialized" in str(e) or "can only be called once" in str(e):
                    logger.error("❌ [MCP] Session manager not properly initialized, falling back to error response")
                    await MCPHandler.create_unavailable_response(scope, receive, send)
                else:
                    raise
        else:
            # MCP modules unavailable: return an error message
            await MCPHandler.create_unavailable_response(scope, receive, send)

    @staticmethod
    async def create_unavailable_response(scope, receive, send):
        """Creates an MCP unavailable response."""
        from starlette.responses import JSONResponse

        reason = "PyInstaller environment with import issues" if mcp_server_config.is_frozen else "MCP modules not available"

        if scope["method"] == "GET":
            # SSE connection request
            response = JSONResponse(
                {"error": f"MCP SSE not available: {reason}"},
                status_code=503
            )
        else:
            # JSON-RPC request
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32603,
                        "message": f"MCP functionality not available: {reason}. Please use the development environment or fix PyInstaller packaging."
                    }
                },
                status_code=503
            )

        await response(scope, receive, send)

# MCP ASGI Application
async def mcp_asgi(scope, receive, send):
    """MCP ASGI entry point."""
    await MCPHandler.handle_request(scope, receive, send)

# ==================== Route Configuration ====================
class RouteBuilder:
    """Route builder."""

    def __init__(self, request_handlers):
        self.request_handlers: RequestHandlers = request_handlers

    def get_base_routes(self):
        """Get base routes"""
        return [
            Mount("/mcp", app=mcp_asgi),
            Route("/healthz", health_check),
            Route('/api/initialize', self.request_handlers.initialize, methods=['POST']),
            Route('/api/gen_feedbacks', self.request_handlers.gen_feedbacks, methods=['GET']),
            Route('/api/get_mission_reports', self.request_handlers.get_mission_reports, methods=['GET']),
            Route('/api/load_graph', self.request_handlers.get_skill_graph, methods=['GET']),
            Route('/api/stream', self.request_handlers.stream),
            Route('/api/sync_bots_missions', self.request_handlers.sync_bots_missions, methods=['POST']),
            Route('/api/save_graph', self.request_handlers.save_skill_graph, methods=['POST']),
            Route('/api/avatar', self.request_handlers.serve_avatar, methods=['GET']),
        ]

    def get_mcp_routes(self):
        """Get MCP related routes"""
        if not mcp_server_config.has_mcp_support():
            return []
        return [
            Mount("/sse", app=mcp_server_config.handle_sse),
            Mount("/messages/", app=mcp_server_config.meca_sse.handle_post_message),
            Mount("/mcp_messages/", app=mcp_server_config.meca_streamable_http.handle_request),
        ]

    def create_routes(self):
        """Create complete route list"""
        routes = self.get_base_routes()
        mcp_routes = self.get_mcp_routes()
        if mcp_routes:
            routes.extend(mcp_routes)
            logger.info("✅ Added MCP routes")
        else:
            logger.info("🔧 MCP routes not added (disabled or unsupported)")
        return routes # ==================== Application Creation ====================


class AppBuilder:
    """Starlette application builder"""

    @staticmethod
    def create_app(request_handlers):
        """Create Starlette application"""
        route_builder = RouteBuilder(request_handlers)
        routes = route_builder.create_routes()

        if os.path.isdir(static_dir):
            routes.append(Mount('/', StaticFiles(directory=static_dir, html=True), name='static'))
        else:
            logger.warning(f"Static dir missing, skipping mount: {static_dir}")

        app_config = {
            'routes': routes,
            'debug': mcp_server_config.is_development
        }

        logger.info("🔧 Created Starlette app of LcoalServer")
        app = Starlette(**app_config)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_methods=['*'],
            allow_headers=['*']
        )
        return app

# ==================== Server Startup ====================
class ServerOptimizer:
    """Server optimizer"""

    @staticmethod
    def setup_pyinstaller_environment():
        """Setup PyInstaller environment optimizations"""
        logger.info("🔧 Detected PyInstaller environment, applying optimizations...")

        # Event loop optimization
        ServerOptimizer._setup_event_loop()

        # Disable warnings
        ServerOptimizer._disable_warnings()

    @staticmethod
    def _hide_console_window_windows():
        """Best-effort hide any attached console window on Windows.
        This helps avoid a transient Python console flicker when starting background servers
        in packaged (PyInstaller) applications.
        """
        try:
            import sys
            if sys.platform != 'win32':
                return
            import ctypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            GetConsoleWindow = kernel32.GetConsoleWindow
            GetConsoleWindow.restype = ctypes.c_void_p
            hwnd = GetConsoleWindow()
            if hwnd:
                # SW_HIDE = 0
                user32.ShowWindow(ctypes.c_void_p(hwnd), 0)
        except Exception:
            # Silent best-effort
            pass

    @staticmethod
    def _setup_event_loop():
        """Setup event loop"""
        import asyncio

        try:
            # Event loop policy is already set in main.py for the main process
            # No need to set it again here to avoid redundancy
            if os.name == 'nt':
                current_policy = asyncio.get_event_loop_policy()
                if isinstance(current_policy, asyncio.WindowsSelectorEventLoopPolicy):
                    logger.info("✅ WindowsSelectorEventLoopPolicy already set (from main.py)")
                else:
                    logger.info("ℹ️  Event loop policy will be handled by main process")
        except Exception as e:
            logger.warning(f"Failed to check event loop policy: {e}")

    @staticmethod
    def _disable_warnings():
        """Disable warnings that may cause issues"""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        logger.debug("✅ Disabled deprecation warnings for PyInstaller")

# Global reference to allow graceful shutdown
class ServerManager:
    """Server manager for encapsulating server state and lifecycle"""

    def __init__(self, main_win: 'MainWindow'):
        self.main_win: MainWindow = main_win
        self.uvicorn_server = None
        self.server_thread = None

    def get_server_url(self) -> str:
        """Get local server URL"""
        port = int(self.main_win.get_local_server_port())
        return f"http://localhost:{port}"

    def get_api_url(self, endpoint: str) -> str:
        """Get complete URL for API endpoint"""
        return f"{self.get_server_url()}{endpoint}"

    def start_in_thread(self):
        """Start server in a separate thread"""
        port = int(self.main_win.get_local_server_port())

        # Optimization: Set higher thread priority for faster startup
        self.server_thread = threading.Thread(target=self._run_starlette, args=(port,))
        self.server_thread.daemon = False  # Allow proper cleanup instead of forced termination
        self.server_thread.start()
        logger.info(f"🚀 Optimized local server starting on port {port} in separate thread")

    def stop(self):
        """Request Uvicorn server to shut down gracefully"""
        if self.uvicorn_server:
            logger.info("Stopping local Starlette server...")

            # IMPORTANT: First signal the server to stop, then wait for thread completion
            # This is simpler and more reliable than complex async shutdown
            try:
                # Signal the server to stop gracefully
                self.uvicorn_server.should_exit = True
                logger.info("Server shutdown signal sent")

                # Wait for the server thread to complete
                self._sync_shutdown()

            except Exception as e:
                logger.error(f"Error during server shutdown: {e}")
                # Force shutdown as last resort
                self._force_shutdown()

            # Reset references
            self.uvicorn_server = None
            self.server_thread = None

            return True
        logger.warning("No active Uvicorn server to stop.")
        return False

    def _sync_shutdown(self):
        """Synchronous shutdown with optimized thread handling"""
        if self.server_thread and self.server_thread.is_alive():
            logger.info("Waiting for server thread to finish...")
            
            # Use a shorter timeout and more aggressive approach
            self.server_thread.join(timeout=5.0)  # Reduced from 10s to 5s
            
            if self.server_thread.is_alive():
                logger.warning("Server thread did not finish within 5s, checking port release...")
                # Check if port is actually released even if thread is still alive
                port = int(self.main_win.get_local_server_port())
                if is_port_available("127.0.0.1", port):
                    logger.info("✅ Port released successfully despite thread still running")
                else:
                    logger.warning("⚠️  Port still occupied, may need force shutdown")
            else:
                logger.info("✅ Server thread finished successfully")

    def _force_shutdown(self):
        """Force shutdown as last resort"""
        logger.warning("Attempting force shutdown...")
        if self.server_thread and self.server_thread.is_alive():
            # This is not ideal, but sometimes necessary
            logger.warning("Force terminating server thread...")
            # Note: Python doesn't have thread.terminate(), so we rely on daemon behavior
            self.server_thread.daemon = True  # Convert to daemon for force termination

    def _run_starlette(self, port=4668):
        """Optimized Starlette server startup method"""
        logger.info(f"🚀 Starting optimized Starlette server on port {port}")
        logger.info(f"Environment: {'PyInstaller' if mcp_server_config.is_frozen else 'Development'}")
        logger.info(f"MCP Support: {'Enabled' if mcp_server_config.has_mcp_support() else 'Disabled'}")

        if mcp_server_config.is_frozen:
            ServerOptimizer.setup_pyinstaller_environment()
            # Additionally, hide any console window to prevent transient flicker
            ServerOptimizer._hide_console_window_windows()

        # Pre-create components to reduce startup time
        request_handlers = RequestHandlers(self.main_win)
        app = AppBuilder.create_app(request_handlers)

        # Optimized host binding strategy - prioritize 127.0.0.1
        host_candidates = ["127.0.0.1", "0.0.0.0"]

        last_err = None
        for host_bind in host_candidates:
            try:
                logger.info(f"⚡ Attempting fast startup on {host_bind}:{port}")

                # Optimized Uvicorn configuration - reduce startup overhead
                config = uvicorn.Config(
                    app=app,
                    host=host_bind,
                    port=port,
                    log_level="warning",  # Reduce log output
                    access_log=False,     # Disable access log
                    loop="asyncio",
                    http="h11",
                    log_config=None,
                    workers=1,            # Single process mode
                    reload=False,         # Disable auto-reload
                    use_colors=False,     # Disable color output
                )
                server = uvicorn.Server(config)

                self.uvicorn_server = server
                logger.info(f"✅ Server configured, starting on {host_bind}:{port}")
                server.run()
                logger.info(f"✅ Uvicorn server exited normally on {host_bind}:{port}")
                last_err = None
                break
            except Exception as e1:
                last_err = str(e1)
                logger.warning(f"⚠️  Failed to bind {host_bind}:{port} - {e1}")
                continue

        if last_err:
            logger.error(f"❌ All server startup attempts failed. Last error: {last_err}")
            raise RuntimeError(f"Server startup failed: {last_err}")

# ==================== Global Instance and Entry Point ====================

# Global server manager instance
server_manager_instance = None

def start_local_server_in_thread(mwin: 'MainWindow'):
    """Start local server"""
    global server_manager_instance
    if server_manager_instance is None:
        server_manager_instance = ServerManager(mwin)
        server_manager_instance.start_in_thread()
        
        # MCP session warmup will be triggered by the first MCP call
        # We don't pre-warmup here because:
        # 1. The server runs in its own thread with its own event loop
        # 2. MCP calls happen in the main thread's event loop
        # 3. Creating session in wrong event loop causes call_tool to hang
        # 
        # Instead, we set a flag to trigger warmup on first MCP call
        try:
            from agent.mcp.local_client import mark_needs_warmup
            mark_needs_warmup()
            logger.info("MCP session will be warmed up on first call")
        except Exception as e:
            logger.debug(f"MCP warmup flag not set: {e}")

def is_port_available(host: str, port: int) -> bool:
    """Check if port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0  # 0 means connection successful (port occupied)
    except Exception:
        return False

def wait_for_port_release(host: str, port: int, timeout: float = 10.0) -> bool:
    """Wait for port to be released"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_available(host, port):
            logger.info(f"✅ Port {port} on {host} is now available")
            return True
        time.sleep(0.5)
    logger.warning(f"⚠️  Port {port} on {host} is still occupied after {timeout}s")
    return False

def stop_local_server():
    """Stop local server"""
    global server_manager_instance
    if server_manager_instance:
        result = server_manager_instance.stop()

        # Wait for port to be released
        if result:
            port = int(server_manager_instance.main_win.get_local_server_port())
            logger.info(f"Waiting for port {port} to be released...")
            wait_for_port_release("127.0.0.1", port, timeout=10.0)

        # Clear the global instance to allow clean restart
        server_manager_instance = None
        logger.info("✅ Global server manager instance cleared")
        return result
    return False
