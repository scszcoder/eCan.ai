import threading
import asyncio
from flask import Flask, send_from_directory, jsonify, request, Response
from flask_cors import CORS
import os
import time
import uuid
from concurrent.futures import Future
from asyncio import Future as AsyncFuture
response_dict = {}

newECB = Flask(__name__, static_folder='dist')  # Serve Vue static files
CORS(newECB)
MainWin = None

# Route to serve the Vue app
@newECB.route('/api/data', methods=['GET'])
def get_data():
    data = {
        'name': 'John Doe',
        'age': 30,
        'occupation': 'Software Developer'
    }
    return jsonify(data)  # Return data as JSON

# Example API to post data
@newECB.route('/api/data', methods=['POST'])
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
@newECB.route('/api/stream')
def stream():
    def eventStream():
        while True:
            time.sleep(1)  # Simulate some delay or real-time processing
            yield f"data: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return Response(eventStream(), mimetype="text/event-stream")

def run_flask():
    newECB.run(port=6668)

# Start Flask server in a separate thread
def start_local_server_in_thread(mwin):
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # Allows the thread to exit when the main program exits
    flask_thread.start()
    MainWin = mwin

