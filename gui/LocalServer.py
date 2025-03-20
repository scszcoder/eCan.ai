import threading
import asyncio
from flask import Flask, send_from_directory, jsonify, request, Response
from flask_cors import CORS
import os
import time
import uuid
from concurrent.futures import Future
from asyncio import Future as AsyncFuture
import traceback
response_dict = {}

mecaLocalServer = Flask(__name__, static_folder='dist')  # Serve Vue static files
CORS(mecaLocalServer)
MainWin = None

# Route to serve the Vue app
@mecaLocalServer.route('/api/gen_feedbacks', methods=['GET'])
def gen_feedbacks():
    print("servering gen_feedbacks.....")
    mids = request.args.get('mids', default="-1")  # 'default' is the fallback value
    print("mids", mids)
    data = MainWin.genFeedbacks(mids)
    # data = {"fb": "hehloooooo"}
    return jsonify(data), 200 # Return data as JSON

@mecaLocalServer.route('/api/get_mission_reports', methods=['GET'])
def get_mission_reports():
    start_date = request.args.get('start_date', default="-1")  # 'default' is the fallback value
    end_date = request.args.get('end_date', default="-1")  # 'default' is the fallback value

    data = MainWin.getRPAReports(start_date, end_date)
    return jsonify(data), 200 # Return data as JSON


# Example API to post data
@mecaLocalServer.route('/api/gen_feedbacks', methods=['POST'])
def post_data():
    incoming_data = request.json  # Get JSON data sent from Vue
    print(f"Received data: {incoming_data}")
    # Generate a unique ID for the task
    task_id = str(uuid.uuid4())
    future = Future()

    # Add the future to the response dictionary
    response_dict[task_id] = future

    # Send the task to the async worker
    MainWin.task_queue.put({
        "task_id": task_id,
        "data": request.json  # Pass the request data
    })

    # Wait for the result (blocks until future is resolved)
    result = future.result(timeout=30)  # Timeout after 30 seconds
    return jsonify({"status": "success", "result": result})


# SSE route to send real-time data to Vue frontend
@mecaLocalServer.route('/api/stream')
def stream():
    def eventStream():
        while True:
            time.sleep(1)  # Simulate some delay or real-time processing
            yield f"data: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return Response(eventStream(), mimetype="text/event-stream")


# given a list of bot emails, and mission ids,
# read the rows from local DB and send them back.
@mecaLocalServer.route('/api/sync_bots_missions', methods=['POST'])
def sync_bots_missions():
    try:
        incoming_data = request.get_json(force=True)  # `force=True` will attempt to parse even if Content-Type is missing
        print("sync_bots_missions Received data:", incoming_data)

        b_emails = incoming_data.get('bots',[])  # 'default' is the fallback value
        minfos = incoming_data.get('missions', [])  # 'default' is the fallback value
        #minfo is in the format of asin|source_file_full_path
        m_asin_srcs = []
        for minfo in minfos:
            infos = minfo.split("|")
            m_asin_srcs.append({"asin": infos[0].strip(), "src": infos[1].strip()})

        print(f"received syn_bots_missions request.")
        # Generate a unique ID for the task
        bots_data = MainWin.bot_service.find_bots_by_emails(b_emails)
        missions_data = MainWin.mission_service.find_missions_by_asin_srcs(m_asin_srcs)
        # Wait for the result (blocks until future is resolved)
        result = {"bots": bots_data, "missions": missions_data}
        return jsonify({"status": "success", "result": result}), 200

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorFetchSchedule:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorFetchSchedule: traceback information not available:" + str(e)
        print(ex_stat)
        jsonify({"status": "failure", "result": ex_stat})

def run_flask():
    print("Starting mecaLocalServer....")
    mecaLocalServer.run(host="0.0.0.0", port=4668)

# Start Flask server in a separate thread
def start_local_server_in_thread(mwin):
    global MainWin
    MainWin = mwin
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # Allows the thread to exit when the main program exits
    flask_thread.start()

