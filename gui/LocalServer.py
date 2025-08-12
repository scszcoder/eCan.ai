import threading
import asyncio

# 导入 logger（需要在早期导入以便在所有类中使用）
from utils.logger_helper import logger_helper as logger

# 在导入任何其他模块之前，立即应用 PyInstaller 修复
def _apply_early_pyinstaller_fixes():
    """在模块导入前应用 PyInstaller 修复"""
    import sys
    import os

    logger.debug(f"[EARLY] Starting early PyInstaller fixes...")
    logger.debug(f"[EARLY] sys.frozen = {getattr(sys, 'frozen', False)}")
    logger.debug(f"[EARLY] sys._MEIPASS = {getattr(sys, '_MEIPASS', 'Not set')}")
    logger.debug(f"[EARLY] Current sys.path length: {len(sys.path)}")

    if getattr(sys, 'frozen', False):
        logger.debug(f"[EARLY] In PyInstaller environment, applying fixes...")

        # 添加 MEIPASS 到 sys.path
        if hasattr(sys, '_MEIPASS'):
            meipass = sys._MEIPASS
            if meipass not in sys.path:
                sys.path.insert(0, meipass)
                logger.debug(f"[EARLY] Added MEIPASS to sys.path: {meipass}")

        # 检查 win32 相关路径
        win32_paths = [path for path in sys.path if 'win32' in path.lower()]
        logger.debug(f"[EARLY] Found {len(win32_paths)} win32 paths in sys.path:")
        for path in win32_paths:
            logger.debug(f"[EARLY]   - {path}")

        # 关键修复：直接修改 sys.modules 来绕过 pywintypes 的路径检查
        try:
            logger.debug(f"[EARLY] Attempting direct pywintypes bypass...")

            # 方法1: 预先在 sys.modules 中注册 pywintypes
            import types
            dummy_pywintypes = types.ModuleType('pywintypes')

            # 添加一些基本属性
            dummy_pywintypes.__file__ = '<dummy pywintypes>'
            dummy_pywintypes.__package__ = 'win32'

            # 添加常用的 pywintypes 属性和类
            class DummyOVERLAPPED:
                def __init__(self):
                    pass

            class DummyHANDLE:
                def __init__(self, value=0):
                    self.value = value

                def __int__(self):
                    return self.value

            # 添加常用的 pywintypes 对象
            dummy_pywintypes.OVERLAPPED = DummyOVERLAPPED
            dummy_pywintypes.HANDLE = DummyHANDLE
            dummy_pywintypes.error = Exception  # pywintypes.error 通常是一个异常类

            # 添加一些常用的常量
            dummy_pywintypes.INFINITE = 0xFFFFFFFF
            dummy_pywintypes.WAIT_OBJECT_0 = 0
            dummy_pywintypes.WAIT_TIMEOUT = 258

            # 注册到 sys.modules
            sys.modules['pywintypes'] = dummy_pywintypes
            logger.info(f"[EARLY] Registered enhanced dummy pywintypes in sys.modules")

            # 方法2: 修改 win32.lib.pywintypes 的行为
            try:
                # 直接修改 pywintypes.py 文件的行为
                import importlib.util
                import importlib.machinery

                # 查找 pywintypes.py 文件
                for path in sys.path:
                    pywintypes_path = os.path.join(path, 'win32', 'lib', 'pywintypes.py')
                    if os.path.exists(pywintypes_path):
                        logger.debug(f"[EARLY] Found pywintypes.py at: {pywintypes_path}")

                        # 创建一个修改过的模块加载器
                        spec = importlib.util.spec_from_file_location("win32.lib.pywintypes", pywintypes_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)

                            # 在执行模块之前，先修改全局环境
                            original_frozen = getattr(sys, 'frozen', False)
                            sys.frozen = False  # 临时禁用 frozen 状态

                            try:
                                spec.loader.exec_module(module)
                                logger.debug(f"[EARLY] Successfully loaded pywintypes with frozen=False")

                                # 恢复 frozen 状态
                                sys.frozen = original_frozen

                                # 注册模块
                                sys.modules['win32.lib.pywintypes'] = module
                                sys.modules['pywintypes'] = module

                                logger.debug(f"[EARLY] Successfully bypassed pywintypes path check")
                                break

                            except Exception as e:
                                sys.frozen = original_frozen  # 确保恢复状态
                                logger.error(f"⚠️ [EARLY] Failed to load modified pywintypes: {e}")

            except Exception as e:
                logger.error(f"⚠️ [EARLY] Advanced pywintypes fix failed: {e}")

        except Exception as e:
            logger.error(f"⚠️ [EARLY] Early PyInstaller fix failed: {e}")
            import traceback
            logger.error(f"⚠️ [EARLY] Traceback: {traceback.format_exc()}")
    else:
        logger.info(f"[EARLY] Not in PyInstaller environment, skipping fixes")

# 立即应用修复
_apply_early_pyinstaller_fixes()

from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Route, Mount, ASGIApp, Router
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import os
import time
import uuid
import json
from concurrent.futures import Future
from asyncio import Future as AsyncFuture
# ==================== 环境检测和条件导入 ====================
import sys
import os

class PyInstallerMCPFixer:
    """PyInstaller MCP 修复器"""

    @staticmethod
    def fix_platform_specific_issues():
        """修复平台特定的问题"""
        if not getattr(sys, 'frozen', False):
            return  # 只在 PyInstaller 环境中修复

        platform = sys.platform
        logger.info(f"🔧 Applying PyInstaller fixes for platform: {platform}")

        if platform.startswith('win'):
            PyInstallerMCPFixer._fix_windows_issues()
        elif platform.startswith('darwin'):
            PyInstallerMCPFixer._fix_macos_issues()
        else:
            logger.warning(f"⚠️ Unknown platform: {platform}, applying generic fixes")
            PyInstallerMCPFixer._fix_generic_issues()

    @staticmethod
    def _fix_windows_issues():
        """修复 Windows 特定问题"""
        logger.info(f"🔧 [WIN] Starting Windows-specific fixes...")

        try:
            # 方法1: 修改 sys.path 包含必要的路径
            logger.info(f"🔧 [WIN] Checking MEIPASS and adding win32 paths...")
            if hasattr(sys, '_MEIPASS'):
                # 添加 PyInstaller 的临时目录到路径
                meipass = sys._MEIPASS
                logger.info(f"🔧 [WIN] Found MEIPASS: {meipass}")

                potential_paths = [
                    os.path.join(meipass, 'win32'),
                    os.path.join(meipass, 'win32', 'lib'),
                    os.path.join(meipass, 'Lib', 'site-packages', 'win32'),
                    os.path.join(meipass, 'Lib', 'site-packages', 'win32', 'lib'),
                ]

                added_paths = 0
                for path in potential_paths:
                    if os.path.exists(path):
                        if path not in sys.path:
                            sys.path.insert(0, path)
                            logger.info(f"✅ [WIN] Added path: {path}")
                            added_paths += 1
                        else:
                            logger.debug(f"ℹ️ [WIN] Path already exists: {path}")
                    else:
                        logger.debug(f"⚠️ [WIN] Path not found: {path}")

                logger.info(f"🔧 [WIN] Added {added_paths} new paths to sys.path")
            else:
                logger.info(f"ℹ️ [WIN] No MEIPASS found (not in PyInstaller environment)")

            # 方法2: 预先导入 pywintypes 避免延迟导入问题
            logger.info(f"🔧 [WIN] Attempting to pre-import pywintypes...")
            try:
                import pywintypes
                logger.info("✅ [WIN] Successfully pre-imported pywintypes")
            except ImportError as e:
                logger.warning(f"⚠️ [WIN] Failed to pre-import pywintypes: {e}")
                logger.warning(f"⚠️ [WIN] This is expected if pywintypes has path issues")

            # 方法3: 修补 pywintypes 的导入检查
            logger.info(f"🔧 [WIN] Attempting to patch pywintypes import function...")
            try:
                import win32.lib.pywintypes as pywintypes_module
                logger.info(f"✅ [WIN] Successfully imported win32.lib.pywintypes for patching")

                if hasattr(pywintypes_module, '__import_pywin32_system_module__'):
                    logger.info(f"🔧 [WIN] Found __import_pywin32_system_module__, applying patch...")
                    original_import = pywintypes_module.__import_pywin32_system_module__

                    def patched_import(modname, globals_dict):
                        logger.debug(f"🔧 [WIN-PATCH] Attempting to import {modname}")
                        try:
                            result = original_import(modname, globals_dict)
                            logger.debug(f"✅ [WIN-PATCH] Successfully imported {modname} via original method")
                            return result
                        except ImportError as e:
                            logger.debug(f"⚠️ [WIN-PATCH] Original import failed for {modname}: {e}")
                            if 'frozen sys.path' in str(e):
                                logger.debug(f"🔧 [WIN-PATCH] Detected frozen path issue, trying alternatives...")
                                # 在 PyInstaller 环境中，尝试直接导入
                                try:
                                    result = __import__(modname)
                                    logger.debug(f"✅ [WIN-PATCH] Successfully imported {modname} via __import__")
                                    return result
                                except ImportError as e2:
                                    logger.debug(f"⚠️ [WIN-PATCH] __import__ also failed for {modname}: {e2}")
                                    # 如果还是失败，返回一个虚拟模块
                                    logger.debug(f"🔧 [WIN-PATCH] Creating dummy module for {modname}")
                                    import types
                                    return types.ModuleType(modname)
                            raise

                    pywintypes_module.__import_pywin32_system_module__ = patched_import
                    logger.info("✅ [WIN] Successfully patched pywintypes import function")
                else:
                    logger.warning("⚠️ [WIN] __import_pywin32_system_module__ not found in pywintypes")

            except ImportError as e:
                logger.warning(f"⚠️ [WIN] pywintypes module not available for patching: {e}")

            logger.info(f"✅ [WIN] Windows fixes completed")

        except Exception as e:
            logger.error(f"❌ [WIN] Windows fixes failed: {e}")
            import traceback
            logger.error(f"❌ [WIN] Traceback: {traceback.format_exc()}")

    @staticmethod
    def _fix_macos_issues():
        """修复 macOS 特定问题"""
        try:
            # 修复 macOS 动态库路径
            if hasattr(sys, '_MEIPASS'):
                meipass = sys._MEIPASS
                macos_paths = [
                    os.path.join(meipass, 'lib'),
                    os.path.join(meipass, 'Frameworks'),
                    os.path.join(meipass, '.dylibs'),
                ]

                for path in macos_paths:
                    if os.path.exists(path):
                        # 添加到 DYLD_LIBRARY_PATH
                        dyld_path = os.environ.get('DYLD_LIBRARY_PATH', '')
                        if path not in dyld_path:
                            os.environ['DYLD_LIBRARY_PATH'] = f"{path}:{dyld_path}" if dyld_path else path
                            logger.info(f"✅ Added macOS library path: {path}")

            # 修复 macOS 权限问题
            try:
                if hasattr(sys, '_MEIPASS'):
                    temp_dir = sys._MEIPASS
                    os.chmod(temp_dir, 0o755)
                    logger.info("✅ Fixed macOS permissions")
            except Exception as e:
                logger.warning(f"⚠️ Permission fix failed: {e}")

            # 设置 macOS 特定的环境变量
            os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
            logger.info("✅ Set macOS fork safety")

        except Exception as e:
            logger.error(f"❌ macOS fixes failed: {e}")

    @staticmethod
    def _fix_generic_issues():
        """修复通用问题"""
        try:
            # 通用的路径修复
            if hasattr(sys, '_MEIPASS'):
                meipass = sys._MEIPASS
                generic_paths = [
                    os.path.join(meipass, 'lib'),
                    os.path.join(meipass, 'libs'),
                ]

                for path in generic_paths:
                    if os.path.exists(path) and path not in sys.path:
                        sys.path.insert(0, path)
                        logger.info(f"✅ Added generic path: {path}")

            logger.info("✅ Applied generic fixes")

        except Exception as e:
            logger.error(f"❌ Generic fixes failed: {e}")

class EnvironmentConfig:
    """环境配置管理器"""

    def __init__(self):
        self.is_frozen = getattr(sys, 'frozen', False)
        self.is_development = not self.is_frozen

        # 在 PyInstaller 环境中应用修复
        if self.is_frozen:
            PyInstallerMCPFixer.fix_platform_specific_issues()

        self._mcp_modules = None
        self._init_mcp_modules()

    def _init_mcp_modules(self):
        """初始化 MCP 模块"""
        logger.info(f"🔧 [MCP] Starting MCP module initialization...")
        logger.info(f"🔧 [MCP] Environment: {'PyInstaller' if self.is_frozen else 'Development'}")

        try:
            # 逐个尝试导入 MCP 模块，记录每个模块的导入状态
            logger.info(f"🔧 [MCP] Attempting to import agent.mcp.server.server...")
            try:
                from agent.mcp.server.server import (
                    handle_sse, sse_handle_messages, meca_mcp_server,
                    meca_sse, meca_streamable_http, handle_streamable_http,
                    session_manager, set_server_main_win, lifespan
                )
                logger.info(f"✅ [MCP] Successfully imported agent.mcp.server.server")
            except ImportError as e:
                logger.error(f"❌ [MCP] Failed to import agent.mcp.server.server: {e}")
                raise

            logger.info(f"🔧 [MCP] Attempting to import langchain_mcp_adapters.client...")
            try:
                from langchain_mcp_adapters.client import MultiServerMCPClient
                logger.info(f"✅ [MCP] Successfully imported langchain_mcp_adapters.client")
            except ImportError as e:
                logger.error(f"❌ [MCP] Failed to import langchain_mcp_adapters.client: {e}")
                raise

            logger.info(f"🔧 [MCP] Attempting to import langchain_mcp_adapters.tools...")
            try:
                from langchain_mcp_adapters.tools import load_mcp_tools
                logger.info(f"✅ [MCP] Successfully imported langchain_mcp_adapters.tools")
            except ImportError as e:
                logger.error(f"❌ [MCP] Failed to import langchain_mcp_adapters.tools: {e}")
                raise

            logger.info(f"🔧 [MCP] Attempting to import mcp.client.sse...")
            try:
                from mcp.client.sse import sse_client
                logger.info(f"✅ [MCP] Successfully imported mcp.client.sse")
            except ImportError as e:
                logger.error(f"❌ [MCP] Failed to import mcp.client.sse: {e}")
                raise

            logger.info(f"🔧 [MCP] Attempting to import mcp.client.session...")
            try:
                from mcp.client.session import ClientSession
                logger.info(f"✅ [MCP] Successfully imported mcp.client.session")
            except ImportError as e:
                logger.error(f"❌ [MCP] Failed to import mcp.client.session: {e}")
                raise

            logger.info(f"🔧 [MCP] Attempting to import contextlib...")
            try:
                from contextlib import asynccontextmanager
                logger.info(f"✅ [MCP] Successfully imported contextlib")
            except ImportError as e:
                logger.error(f"❌ [MCP] Failed to import contextlib: {e}")
                raise

            self._mcp_modules = {
                'handle_sse': handle_sse,
                'sse_handle_messages': sse_handle_messages,
                'meca_mcp_server': meca_mcp_server,
                'meca_sse': meca_sse,
                'meca_streamable_http': meca_streamable_http,
                'handle_streamable_http': handle_streamable_http,
                'session_manager': session_manager,
                'set_server_main_win': set_server_main_win,
                'lifespan': lifespan,
                'MultiServerMCPClient': MultiServerMCPClient,
                'load_mcp_tools': load_mcp_tools,
                'sse_client': sse_client,
                'ClientSession': ClientSession,
                'asynccontextmanager': asynccontextmanager,
            }

            env_type = "PyInstaller (fixed)" if self.is_frozen else "Development"
            logger.info(f"✅ [MCP] Successfully imported ALL MCP modules in {env_type} environment")
            logger.info(f"✅ [MCP] Total modules imported: {len(self._mcp_modules)}")

        except ImportError as e:
            logger.error(f"❌ [MCP] Failed to import MCP modules: {e}")
            logger.error(f"❌ [MCP] Import error type: {type(e).__name__}")
            logger.error(f"❌ [MCP] Import error args: {e.args}")

            # 输出详细的错误信息
            import traceback
            logger.error(f"❌ [MCP] Full traceback:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    logger.error(f"❌ [MCP] {line}")

            if self.is_frozen:
                logger.error("❌ [MCP] MCP import failed in PyInstaller environment - this should not happen after fixes")

                # 输出当前 sys.path 用于调试
                import sys
                logger.error(f"❌ [MCP] Current sys.path length: {len(sys.path)}")
                logger.error(f"❌ [MCP] sys.frozen: {getattr(sys, 'frozen', False)}")
                logger.error(f"❌ [MCP] sys._MEIPASS: {getattr(sys, '_MEIPASS', 'Not set')}")

                # 输出前几个 sys.path 条目
                for i, path in enumerate(sys.path[:5]):
                    logger.error(f"❌ [MCP] sys.path[{i}]: {path}")

            # 创建空的模块字典
            self._mcp_modules = self._get_null_modules()
            logger.warning(f"⚠️ [MCP] Using null modules as fallback")

    def _get_null_modules(self):
        """获取空模块字典"""
        return {key: None for key in [
            'handle_sse', 'sse_handle_messages', 'meca_mcp_server',
            'meca_sse', 'meca_streamable_http', 'handle_streamable_http',
            'session_manager', 'set_server_main_win', 'lifespan',
            'MultiServerMCPClient', 'load_mcp_tools', 'sse_client',
            'ClientSession', 'asynccontextmanager'
        ]}

    def get_module(self, name):
        """获取指定模块"""
        return self._mcp_modules.get(name)

    def has_mcp_support(self):
        """检查是否支持 MCP 功能"""
        # 检查关键模块是否可用
        has_session_manager = self._mcp_modules.get('session_manager') is not None
        has_handle_sse = self._mcp_modules.get('handle_sse') is not None

        # 在开发环境或修复后的 PyInstaller 环境中都支持 MCP
        return has_session_manager and has_handle_sse

# 创建全局环境配置
env_config = EnvironmentConfig()

# 为了向后兼容，导出常用变量
is_frozen_early = env_config.is_frozen
handle_sse = env_config.get_module('handle_sse')
sse_handle_messages = env_config.get_module('sse_handle_messages')
meca_mcp_server = env_config.get_module('meca_mcp_server')
meca_sse = env_config.get_module('meca_sse')
meca_streamable_http = env_config.get_module('meca_streamable_http')
handle_streamable_http = env_config.get_module('handle_streamable_http')
session_manager = env_config.get_module('session_manager')
set_server_main_win = env_config.get_module('set_server_main_win')
lifespan = env_config.get_module('lifespan')
from utils.gui_dispatch import run_on_main_thread, post_to_main_thread

import sys
import traceback
import httpx
response_dict = {}

# mecaLocalServer = Flask(__name__, static_folder='dist')  # Serve Vue static files
# CORS(mecaLocalServer)
MainWin = None
IMAGE_FOLDER = os.path.abspath("run_images")  # Ensure this is your intended path
base_dir = getattr(sys, '_MEIPASS', os.getcwd())

static_dir = os.path.join(base_dir, 'agent', 'agent_files')
if not os.path.isdir(static_dir):
    # 兼容开发与打包路径差异：回退到相对路径
    alt_dir = os.path.join(os.getcwd(), 'agent', 'agent_files')
    if os.path.isdir(alt_dir):
        static_dir = alt_dir

# Endpoint to serve images
async def serve_image(request):
    filename = request.path_params['filename']
    file_path = os.path.join(IMAGE_FOLDER, filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return JSONResponse({"error": "File not found."}, status_code=404)

# API Endpoint equivalent to Flask route '/api/gen_feedbacks'
async def gen_feedbacks(request):
    logger.info("serving gen_feedbacks.....")
    mids = request.query_params.get('mids', "-1")  # Default value is "-1"
    logger.info("mids", mids)

    data = run_on_main_thread(lambda: MainWin.genFeedbacks(mids))
    return JSONResponse(data, status_code=200)

# API Endpoint to handle GET mission reports
async def get_mission_reports(request):
    start_date = request.query_params.get('start_date', "-1")
    end_date = request.query_params.get('end_date', "-1")
    data = run_on_main_thread(lambda: MainWin.getRPAReports(start_date, end_date))
    return JSONResponse(data, status_code=200)

# API Endpoint to handle POST feedback data
async def post_data(request):
    incoming_data = await request.json()
    logger.info(f"Received data: {incoming_data}")
    task_id = str(uuid.uuid4())
    future = asyncio.get_event_loop().create_future()
    response_dict[task_id] = future
    # Ensure any UI-side queue interactions happen on main thread
    run_on_main_thread(lambda: MainWin.task_queue.put({
        "task_id": task_id,
        "data": incoming_data
    }))
    result = await asyncio.wait_for(future, timeout=30)
    return JSONResponse({"status": "success", "result": result})

# SSE endpoint for real-time streaming
async def stream(request):
    async def event_stream():
        while True:
            await asyncio.sleep(1)
            yield f"data: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# Endpoint to sync bots and missions
async def sync_bots_missions(request):
    try:
        incoming_data = await request.json()
        logger.info("sync_bots_missions Received data:", incoming_data)

        b_emails = incoming_data.get('bots', [])
        minfos = incoming_data.get('missions', [])

        m_asin_srcs = []
        for minfo in minfos:
            infos = minfo.split("|")
            m_asin_srcs.append({"asin": infos[0].strip(), "src": infos[1].strip()})

        bots_data = MainWin.bot_service.find_bots_by_emails(b_emails)
        missions_data = MainWin.mission_service.find_missions_by_asin_srcs(m_asin_srcs)
        result = {"bots": bots_data, "missions": missions_data}

        return JSONResponse({"status": "success", "result": result}, status_code=200)

    except Exception as e:
        ex_stat = "ErrorFetchSchedule:" + traceback.format_exc() + " " + str(e)
        logger.error(ex_stat)
        return JSONResponse({"status": "failure", "result": ex_stat}, status_code=500)

async def health_check(request):
    logger.debug("health_check status returned................")
    return JSONResponse({"status": "ok"})



async def initialize(request):
    # Perform whatever server-side initialization you want
    logger.info("initialize() called")
    response = {
        "protocolVersion": "1.0",
        "serverCapabilities": {}
    }
    return JSONResponse(response, status_code=200)

async def get_skill_graph(skg_file):
    skill_graph = None
    if os.path.exists(skg_file):
        with open(skg_file, "r", encoding="utf-8") as skf:
            skill_graph = json.load(skf)
    return skill_graph

async def save_skill_graph(skill_graph, skg_file):
    saved = False
    try:
        with open(skg_file, "w") as outfile:
            json.dump(skill_graph, outfile, indent=4)
        outfile.close()
        saved = True
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSaveSkillGraph:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSaveSkillGraph: traceback information not available:" + str(e)
        saved = False
    return saved

# Wrap the raw ASGI handler for POST
# messages_router = Router([
#     Route("/", endpoint=sse_handle_messages, methods=["POST"])
# ])
#
# sse_router = Router([
#     Route("/", endpoint=handle_sse, methods=["GET"])
# ])
# ==================== MCP 路由处理 ====================
class MCPHandler:
    """MCP 请求处理器"""

    _session_manager_initialized = False
    _session_manager_context = None
    _session_manager_instance = None

    @staticmethod
    async def ensure_session_manager_initialized():
        """确保 session_manager 已正确初始化"""
        if not MCPHandler._session_manager_initialized and session_manager:
            try:
                logger.info("🔧 [MCP] Initializing session manager for PyInstaller environment...")

                # 创建新的 session manager 实例，避免重复使用
                from agent.mcp.server.server import StreamableHTTPSessionManager, meca_mcp_server
                MCPHandler._session_manager_instance = StreamableHTTPSessionManager(
                    app=meca_mcp_server,
                    event_store=None,
                    json_response=True
                )

                # 初始化新实例
                MCPHandler._session_manager_context = MCPHandler._session_manager_instance.run()
                await MCPHandler._session_manager_context.__aenter__()
                MCPHandler._session_manager_initialized = True
                logger.info("✅ [MCP] Session manager initialized successfully")
            except Exception as e:
                logger.error(f"❌ [MCP] Failed to initialize session manager: {e}")
                logger.error(f"❌ [MCP] Traceback: {traceback.format_exc()}")
                # 即使初始化失败，也标记为已尝试，避免重复尝试
                MCPHandler._session_manager_initialized = True

    @staticmethod
    async def handle_request(scope, receive, send):
        """处理 MCP 请求"""
        if env_config.has_mcp_support():
            # 确保 session_manager 已初始化
            await MCPHandler.ensure_session_manager_initialized()

            try:
                # 使用我们自己的 session manager 实例
                if MCPHandler._session_manager_instance:
                    await MCPHandler._session_manager_instance.handle_request(scope, receive, send)
                else:
                    # 如果没有实例，回退到原始的 session_manager
                    await session_manager.handle_request(scope, receive, send)
            except RuntimeError as e:
                if "Task group is not initialized" in str(e) or "can only be called once" in str(e):
                    logger.error("❌ [MCP] Session manager not properly initialized, falling back to error response")
                    await MCPHandler.create_unavailable_response(scope, receive, send)
                else:
                    raise
        else:
            # MCP 模块不可用：返回错误信息
            await MCPHandler.create_unavailable_response(scope, receive, send)

    @staticmethod
    async def create_unavailable_response(scope, receive, send):
        """创建 MCP 不可用响应"""
        from starlette.responses import JSONResponse

        reason = "PyInstaller environment with import issues" if env_config.is_frozen else "MCP modules not available"

        if scope["method"] == "GET":
            # SSE 连接请求
            response = JSONResponse(
                {"error": f"MCP SSE not available: {reason}"},
                status_code=503
            )
        else:
            # JSON-RPC 请求
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

# MCP ASGI 应用
async def mcp_asgi(scope, receive, send):
    """MCP ASGI 入口点"""
    await MCPHandler.handle_request(scope, receive, send)

# ==================== 路由配置 ====================
class RouteBuilder:
    """路由构建器"""

    @staticmethod
    def get_base_routes():
        """获取基础路由"""
        return [
            Mount("/mcp", app=mcp_asgi),
            Route("/healthz", health_check),
            Route('/api/initialize', initialize, methods=['POST']),
            Route('/api/gen_feedbacks', gen_feedbacks, methods=['GET']),
            Route('/api/get_mission_reports', get_mission_reports, methods=['GET']),
            Route('/api/load_graph', get_skill_graph, methods=['GET']),
            Route('/api/stream', stream),
            Route('/api/sync_bots_missions', sync_bots_missions, methods=['POST']),
            Route('/api/save_graph', save_skill_graph, methods=['POST']),
        ]

    @staticmethod
    def get_mcp_routes():
        """获取 MCP 相关路由"""
        if not env_config.has_mcp_support():
            return []

        return [
            Mount("/sse", app=handle_sse),
            Mount("/messages/", app=meca_sse.handle_post_message),
            Mount("/mcp_messages/", app=meca_streamable_http.handle_request),
        ]

    @staticmethod
    def create_routes():
        """创建完整路由列表"""
        routes = RouteBuilder.get_base_routes()
        mcp_routes = RouteBuilder.get_mcp_routes()

        if mcp_routes:
            routes.extend(mcp_routes)
            logger.info("✅ Added full MCP routes for development environment")
        else:
            logger.info("🔧 Using simplified routes (MCP functionality limited)")

        return routes

routes = RouteBuilder.create_routes()

# 仅在静态目录存在时挂载静态文件
if os.path.isdir(static_dir):
    routes.append(Mount('/', StaticFiles(directory=static_dir, html=True), name='static'))
else:
    logger.warning(f"Static dir missing, skipping mount: {static_dir}")

# ==================== 应用创建 ====================
class AppBuilder:
    """Starlette 应用构建器"""

    @staticmethod
    def create_app():
        """创建 Starlette 应用"""
        app_config = {
            'routes': routes,
            'debug': env_config.is_development
        }

        # 只在开发环境且有 lifespan 支持时添加 lifespan
        if env_config.is_development and lifespan is not None:
            app_config['lifespan'] = lifespan
            logger.info("✅ Created Starlette app with lifespan for development environment")
        else:
            logger.info("🔧 Created Starlette app without lifespan (PyInstaller environment or lifespan unavailable)")

        return Starlette(**app_config)

mecaLocalServer = AppBuilder.create_app()

# CORS Middleware setup (same as Flask-CORS)
mecaLocalServer.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Adjust as needed
    allow_methods=['*'],
    allow_headers=['*']
)

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
            # 检查现有事件循环
            try:
                asyncio.get_running_loop()
                logger.debug("Found existing event loop, will create new one")
            except RuntimeError:
                logger.debug("No existing event loop found")

            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("✅ Created new event loop for PyInstaller environment")

            # Windows 特定优化
            if os.name == 'nt':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                logger.info("✅ Set WindowsProactorEventLoopPolicy for PyInstaller")

        except Exception as e:
            logger.warning(f"Failed to setup event loop: {e}")

    @staticmethod
    def _disable_warnings():
        """禁用可能导致问题的警告"""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        logger.debug("✅ Disabled deprecation warnings for PyInstaller")

    @staticmethod
    def setup_windows_policy():
        """设置 Windows 事件循环策略"""
        if os.name == 'nt':
            try:
                import asyncio
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                logger.debug("✅ Set WindowsSelectorEventLoopPolicy for thread compatibility")
            except Exception as e:
                logger.warning(f"Failed to set WindowsSelectorEventLoopPolicy: {e}")

def run_starlette(port=4668):
    """启动 Starlette 服务器"""
    logger.info(f"Starting Starlette server on port {port}")
    logger.info(f"Environment: {'PyInstaller' if env_config.is_frozen else 'Development'}")
    logger.info(f"MCP Support: {'Enabled' if env_config.has_mcp_support() else 'Disabled'}")

    try:
        # 环境特定优化
        if env_config.is_frozen:
            ServerOptimizer.setup_pyinstaller_environment()

        # Windows 兼容性设置
        ServerOptimizer.setup_windows_policy()

        # MCP 会话管理器将在 Starlette 应用的 lifespan 中正确管理

        def _make_server(_lifespan_on: bool):
            cfg = uvicorn.Config(
                app=mecaLocalServer,
                host='127.0.0.1',
                port=port,
                log_level="info",
                access_log=False,
                loop="asyncio",
                lifespan=("on" if _lifespan_on else "off"),
            )
            srv = uvicorn.Server(cfg)
            if hasattr(srv, "install_signal_handlers"):
                srv.install_signal_handlers = False
            return srv

        # lifespan 处理策略
        if env_config.is_frozen:
            # PyInstaller 环境：禁用 lifespan 避免阻塞
            logger.info("🔧 PyInstaller environment: disabling lifespan to avoid blocking...")
            use_lifespan = False
        else:
            # 开发环境：启用 lifespan
            use_lifespan = True

        server = _make_server(use_lifespan)
        try:
            logger.info(f"✅ Starting Uvicorn server on 127.0.0.1:{port}")
            server.run()
        except Exception as e1:
            logger.warning(f"Uvicorn failed with lifespan={'on' if use_lifespan else 'off'}: {e1}")
    except Exception as e:
        logger.exception(f"Failed to start local server on port {port}: {e}")
        # Force-write startup exception to file for diagnosis in frozen environments
        try:
            import traceback
            logger.error(traceback.format_exc())
        except Exception:
            pass
        raise

# Start Starlette server in a separate thread
def start_local_server_in_thread(mwin):
    global MainWin
    MainWin = mwin
    MainWin.mcp_server = meca_mcp_server
    MainWin.sse_server = meca_sse
    port = int(MainWin.get_local_server_port())
    starlette_thread = threading.Thread(target=run_starlette, args=(port,))
    MainWin.local_server_thread = starlette_thread
    starlette_thread.daemon = True  # Allows the thread to exit when the main program exits
    starlette_thread.start()
    logger.info("local server kicked off....................")

# if __name__ == '__main__':
#     run_starlette()
