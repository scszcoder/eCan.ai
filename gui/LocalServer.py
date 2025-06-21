import threading
import asyncio
# from flask import Flask, send_from_directory, jsonify, request, Response
# from flask_cors import CORS
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
from agent.mcp.server.server import handle_sse, sse_handle_messages, meca_mcp_server, meca_sse
from langchain_mcp_adapters.client import MultiServerMCPClient
import sys
import traceback
response_dict = {}

# mecaLocalServer = Flask(__name__, static_folder='dist')  # Serve Vue static files
# CORS(mecaLocalServer)
MainWin = None
IMAGE_FOLDER = os.path.abspath("run_images")  # Ensure this is your intended path
base_dir = getattr(sys, '_MEIPASS', os.getcwd())

static_dir = os.path.join(base_dir, 'agent', 'agent_files')
# Endpoint to serve images
async def serve_image(request):
    filename = request.path_params['filename']
    file_path = os.path.join(IMAGE_FOLDER, filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return JSONResponse({"error": "File not found."}, status_code=404)

# API Endpoint equivalent to Flask route '/api/gen_feedbacks'
async def gen_feedbacks(request):
    print("serving gen_feedbacks.....")
    mids = request.query_params.get('mids', "-1")  # Default value is "-1"
    print("mids", mids)

    data = MainWin.genFeedbacks(mids)
    return JSONResponse(data, status_code=200)

# API Endpoint to handle GET mission reports
async def get_mission_reports(request):
    start_date = request.query_params.get('start_date', "-1")
    end_date = request.query_params.get('end_date', "-1")
    data = MainWin.getRPAReports(start_date, end_date)
    return JSONResponse(data, status_code=200)

# API Endpoint to handle POST feedback data
async def post_data(request):
    incoming_data = await request.json()
    print(f"Received data: {incoming_data}")
    task_id = str(uuid.uuid4())
    future = asyncio.get_event_loop().create_future()
    response_dict[task_id] = future
    MainWin.task_queue.put({
        "task_id": task_id,
        "data": incoming_data
    })
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
        print("sync_bots_missions Received data:", incoming_data)

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
        print(ex_stat)
        return JSONResponse({"status": "failure", "result": ex_stat}, status_code=500)

async def health_check(request):
    print("health_check status returned................")
    return JSONResponse({"status": "ok"})

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
messages_router = Router([
    Route("/", endpoint=sse_handle_messages, methods=["POST"])
])

sse_router = Router([
    Route("/", endpoint=handle_sse, methods=["GET"])
])

routes = [
    Route("/healthz", health_check),
    Mount("/sse", app=handle_sse),
    Mount("/messages/", app=meca_sse.handle_post_message),
    # Route("/sse", endpoint=handle_sse),
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
    Mount('/', StaticFiles(directory=static_dir, html=True), name='static'),
]


mecaLocalServer = Starlette(debug=True, routes=routes)

# CORS Middleware setup (same as Flask-CORS)
mecaLocalServer.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Adjust as needed
    allow_methods=['*'],
    allow_headers=['*']
)

def run_starlette(port=4668):
    print(f"Starting Starlette server....on port {port}")
    uvicorn.run(mecaLocalServer, host='0.0.0.0', port=port)

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
    print("local server kicked off....................")

# if __name__ == '__main__':
#     run_starlette()
# ============================= now create global client ===========================
async def create_mcp_client():
    mcp_client = MultiServerMCPClient(
            {
                "E-Commerce Agents Service": {
                    # make sure you start your weather server on port 8000
                    "url": "http://localhost:4668/sse/",
                    "transport": "sse",
                }
            }
    )
    await mcp_client.__aenter__()
    print("mcp client created................")
    return mcp_client

