import threading
import asyncio

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
from agent.mcp.server.server import handle_sse, sse_handle_messages, meca_mcp_server, meca_sse, meca_streamable_http,handle_streamable_http, session_manager, set_server_main_win
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from contextlib import asynccontextmanager
from utils.logger_helper import logger_helper as logger
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
# 简化的MCP路由，直接委托给已初始化的session_manager
async def mcp_asgi(scope, receive, send):
    await session_manager.handle_request(scope, receive, send)

routes = [
    Mount("/mcp", app=mcp_asgi),
    Mount("/sse", app=handle_sse),
    Mount("/messages/", app=meca_sse.handle_post_message),
    Mount("/mcp_messages/", app=meca_streamable_http.handle_request),
    Route("/healthz", health_check),
    # Route("/sse", endpoint=handle_sse),
    Route('/api/initialize', initialize, methods=['POST']),
    Route('/api/gen_feedbacks', gen_feedbacks, methods=['GET']),
    Route('/api/get_mission_reports', get_mission_reports, methods=['GET']),
    Route('/api/load_graph', get_skill_graph, methods=['GET']),
    Route('/api/stream', stream),
    Route('/api/sync_bots_missions', sync_bots_missions, methods=['POST']),
    Route('/api/save_graph', save_skill_graph, methods=['POST']),
    # Route('/{filename:path}', serve_image),
    # Mount("/messages", app=sse_handle_messages),
    # Mount("/sse", app=sse_router),
    # Route("/sse", endpoint=handle_sse),
    # Route("/messages", endpoint=sse_handle_messages, methods=["POST"]),
    # Mount("/sse", sse_to_mcp),
    # Mount("/sse2mcp", app=meca_mcp_server.sse_app()),
    # Mount("/messages", app=sse_handle_messages),
]

# 仅在静态目录存在时挂载静态文件
if os.path.isdir(static_dir):
    routes.append(Mount('/', StaticFiles(directory=static_dir, html=True), name='static'))
else:
    logger.warning(f"Static dir missing, skipping mount: {static_dir}")

mecaLocalServer = Starlette(debug=True, routes=routes)

# CORS Middleware setup (same as Flask-CORS)
mecaLocalServer.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Adjust as needed
    allow_methods=['*'],
    allow_headers=['*']
)

def run_starlette(port=4668):
    logger.info(f"Starting Starlette server....on port {port}")
    try:
        # On Windows, ensure we use a selector policy when running uvicorn in a thread
        try:
            if os.name == 'nt':
                import asyncio as _asyncio
                _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
        except Exception as _e:
            logger.warning(f"Failed to set WindowsSelectorEventLoopPolicy: {_e}")

        # 异步后台初始化 MCP(长期存活的上下文)，避免阻塞本地 HTTP 服务器启动与 /healthz 检测
        async def mcp_runner_forever():
            try:
                # 保持上下文在后台长期存活
                async with session_manager.run():
                    logger.info("StreamableHTTPSessionManager started")
                    stop = asyncio.Event()
                    await stop.wait()
            except Exception as mcp_e:
                logger.error(f"MCP manager error: {mcp_e}")

        def start_mcp_in_background():
            try:
                asyncio.run(mcp_runner_forever())
            except Exception as be:
                logger.error(f"MCP background loop crashed: {be}")

        threading.Thread(target=start_mcp_in_background, daemon=True).start()

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

        use_lifespan = False
        server = _make_server(use_lifespan)
        try:
            server.run()
        except Exception as e1:
            logger.warning(f"Uvicorn failed with lifespan={'on' if use_lifespan else 'off'}: {e1}")
    except Exception as e:
        logger.exception(f"Failed to start local server: {e}")
        # Force-write startup exception to file for diagnosis in frozen environments
        try:
            import traceback
            logger.error(traceback.format_exc())
        except Exception:
            pass

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
