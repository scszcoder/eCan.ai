import threading
import asyncio
import sys
import os
import time
import uuid
import json
import traceback
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
# ])
# ==================== MCP Route Handling ====================
class MCPHandler:
    """MCP request handler."""

    _session_manager_initialized = False
    _session_manager_context = None
    _session_manager_instance = None

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
        """获取基础路由"""
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
        ]

    def get_mcp_routes(self):
        """获取 MCP 相关路由"""
        if not mcp_server_config.has_mcp_support():
            return []
        return [
            Mount("/sse", app=mcp_server_config.handle_sse),
            Mount("/messages/", app=mcp_server_config.meca_sse.handle_post_message),
            Mount("/mcp_messages/", app=mcp_server_config.meca_streamable_http.handle_request),
        ]

    def create_routes(self):
        """创建完整路由列表"""
        routes = self.get_base_routes()
        mcp_routes = self.get_mcp_routes()
        if mcp_routes:
            routes.extend(mcp_routes)
            logger.info("✅ Added MCP routes")
        else:
            logger.info("🔧 MCP routes not added (disabled or unsupported)")
        return routes # ==================== 应用创建 ====================


class AppBuilder:
    """Starlette 应用构建器"""

    @staticmethod
    def create_app(request_handlers):
        """创建 Starlette 应用"""
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

# ==================== 服务器启动 ====================
class ServerOptimizer:
    """服务器优化器"""

    @staticmethod
    def setup_pyinstaller_environment():
        """设置 PyInstaller 环境优化"""
        logger.info("🔧 Detected PyInstaller environment, applying optimizations...")

        # 事件循环优化
        ServerOptimizer._setup_event_loop()

        # 禁用警告
        ServerOptimizer._disable_warnings()

    @staticmethod
    def _setup_event_loop():
        """设置事件循环"""
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
        """禁用可能导致问题的警告"""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        logger.debug("✅ Disabled deprecation warnings for PyInstaller")

# Global reference to allow graceful shutdown
class ServerManager:
    """服务器管理器，用于封装服务器状态和生命周期"""

    def __init__(self, main_win: 'MainWindow'):
        self.main_win: MainWindow = main_win
        self.uvicorn_server = None
        self.server_thread = None

    def start_in_thread(self):
        """在单独的线程中启动服务器"""
        port = int(self.main_win.get_local_server_port())

        self.server_thread = threading.Thread(target=self._run_starlette, args=(port,))
        self.server_thread.daemon = True
        self.server_thread.start()
        logger.info("Local server kicked off in a separate thread.")

    def stop(self):
        """请求 Uvicorn 服务器优雅地关闭"""
        if self.uvicorn_server:
            logger.info("Stopping local Starlette server...")
            self.uvicorn_server.should_exit = True
            return True
        logger.warning("No active Uvicorn server to stop.")
        return False

    def _run_starlette(self, port=4668):
        """启动 Starlette 服务器的内部方法"""
        logger.info(f"Starting Starlette server on port {port}")
        logger.info(f"Environment: {'PyInstaller' if mcp_server_config.is_frozen else 'Development'}")
        logger.info(f"MCP Support: {'Enabled' if mcp_server_config.has_mcp_support() else 'Disabled'}")

        if mcp_server_config.is_frozen:
            ServerOptimizer.setup_pyinstaller_environment()

        # 创建请求处理器和应用
        request_handlers = RequestHandlers(self.main_win)
        app = AppBuilder.create_app(request_handlers)

        host_candidates = [
            os.environ.get("ECBOT_LOCAL_SERVER_HOST", "127.0.0.1"),
            "0.0.0.0",
        ]

        last_err = None
        for host_bind in host_candidates:
            try:
                logger.info(f"✅ Starting Uvicorn server on {host_bind}:{port}")
                config = uvicorn.Config(
                    app=app,
                    host=host_bind,
                    port=port,
                    log_level="debug",
                    access_log=False,
                    loop="asyncio",
                    http="h11",
                    log_config=None,
                )
                server = uvicorn.Server(config)
                if hasattr(server, "install_signal_handlers"):
                    server.install_signal_handlers = lambda: None

                self.uvicorn_server = server
                server.run()
                logger.info(f"✅ Uvicorn server exited normally on {host_bind}:{port}")
                last_err = None
                break
            except Exception as e1:
                last_err = e1
                logger.warning(f"Uvicorn failed on host={host_bind}: {e1}")

        if last_err:
            logger.error(f"Failed to start local server on port {port}: {last_err}")
            try:
                logger.error(traceback.format_exc())
            except Exception:
                pass
            raise last_err

        # self.uvicorn_server = None

# ==================== 全局实例和入口点 ====================

# 全局服务器管理器实例
server_manager_instance = None

def start_local_server_in_thread(mwin: 'MainWindow'):
    """启动本地服务器"""
    global server_manager_instance
    if server_manager_instance is None:
        server_manager_instance = ServerManager(mwin)
        server_manager_instance.start_in_thread()

def stop_local_server():
    """停止本地服务器"""
    global server_manager_instance
    if server_manager_instance:
        return server_manager_instance.stop()
    return False
