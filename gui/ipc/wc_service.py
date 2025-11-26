from PySide6.QtCore import QObject, Slot, Signal, QRunnable, QThreadPool
from utils.logger_helper import logger_helper as logger
import json
from typing import Optional, Dict, Any, Callable
from .types import (
    IPCRequest, IPCResponse, create_pending_response, create_request, create_error_response, create_success_response
)
from .registry import IPCHandlerRegistry
import traceback


# 1. Create a signal communicator for worker threads
class WorkerSignals(QObject):
    """Defines signals emitted from worker threads"""
    result = Signal(object, object)  # request, ipc_response
    error = Signal(object, object)  # request, ipc_response

# 2. Create a generic QRunnable worker task
class Worker(QRunnable):
    """Runnable worker thread that executes time-consuming tasks"""
    def __init__(self, handler: Callable, request: IPCRequest):
        super().__init__()
        self.handler = handler
        self.request = request
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """Execute task in background thread"""
        import asyncio
        import inspect

        request_id = self.request.get('id', '')
        try:
            params = self.request.get('params')
            result = self.handler(self.request, params)

            # Check if a coroutine object was returned
            if inspect.iscoroutine(result):
                # If it's a coroutine, need to run it in an event loop
                try:
                    # Try to get current event loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, create a new loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    # If no event loop exists, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                response: IPCResponse = loop.run_until_complete(result)
            else:
                response: IPCResponse = result

            self.signals.result.emit(self.request, response)
        except Exception as e:
            logger.error(f"Error in background worker for request {request_id}: {e}", exc_info=True)
            error_details = traceback.format_exc()
            response = create_error_response(self.request, 'WORKER_ERROR', f"{str(e)}\n{error_details}")
            self.signals.error.emit(self.request, response)

class IPCWCService(QObject):
    """
    IPC(Inter-Process Communication) WebChannel Service
    """
    
    # Define signals
    python_to_web = Signal(str)  # Signal to send messages to Web

    def __init__(self):
        super().__init__()
        logger.info("[IPCWCService] IPC WebChannel service initialized")
        # Store mapping of request IDs to corresponding callback functions
        self._request_callbacks: Dict[str, Callable[[IPCResponse], None]] = {}
        self.threadpool = QThreadPool()
        logger.info(f"[IPCWCService] QThreadPool max thread count: {self.threadpool.maxThreadCount()}")

    @Slot(str, result=str)
    def web_to_python(self, message: str) -> str:
        """Handle messages from Web

        Args:
            message: JSON formatted message string

        Returns:
            str: JSON formatted response message
        """
        try:
            # Parse message
            data = json.loads(message)
            data_str = str(data)
            truncated_data = data_str[:800] + "..." if len(data_str) > 500 else data_str
            logger.trace(f"[IPCWCService] web_to_python: Received message: {truncated_data}")

            # Check message type
            if 'type' not in data:
                logger.warning("[IPCWCService] Message missing type field")
                return json.dumps(create_error_response(
                    {'id': 'missing_type', 'method': 'unknown'},
                    'MISSING_TYPE',
                    "Message missing type field"
                ))

            # Handle response message
            if data['type'] == 'response':
                self._handle_response(IPCResponse(**data))
                return json.dumps({"status": "success"})

            # Handle request message
            if data['type'] == 'request':
                return self._handle_request(IPCRequest(**data))

            # Unknown message type
            logger.warning(f"[IPCWCService] Unknown message type: {data['type']}")
            return json.dumps(create_error_response(
                {'id': 'unknown_type', 'method': 'unknown'},
                'UNKNOWN_TYPE',
                f"Unknown message type: {data['type']}"
            ))
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return json.dumps(create_error_response(
                {'id': 'parse_error', 'method': 'unknown'},
                'PARSE_ERROR',
                f"Invalid JSON format: {str(e)}"
            ))
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return json.dumps(create_error_response(
                {'id': 'internal_error', 'method': 'unknown'},
                'INTERNAL_ERROR',
                f"Error processing message: {str(e)}"
            ))

    def _handle_request(self, request: IPCRequest) -> str:
        """Handle IPC request and dispatch based on handler type"""
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

        if handler_type == 'sync':
            # Call sync handler directly in main thread
            logger.trace(f"[IPCWCService] Executing sync handler for method: {method}")
            try:
                params = request.get('params')
                sync_response = handler(request, params)
                return json.dumps(sync_response)
            except KeyboardInterrupt:
                logger.warning(f"[IPCWCService] KeyboardInterrupt during sync handler execution for method: {method}")
                return json.dumps(create_error_response(
                    request,
                    'INTERRUPTED',
                    f"Operation '{method}' was interrupted by user"
                ))
            except Exception as e:
                logger.error(f"Error in sync handler for method {method}: {e}")
                return json.dumps(create_error_response(
                    request,
                    'HANDLER_ERROR',
                    f"Error executing handler for '{method}': {str(e)}"
                ))
        
        elif handler_type == 'background':
            # Create a Worker for background task and submit to thread pool
            logger.debug(f"[IPCWCService] Submitting background handler for method: {method} to threadpool")
            worker = Worker(handler, request)
            worker.signals.result.connect(self._on_background_task_result)
            worker.signals.error.connect(self._on_background_task_error)
            self.threadpool.start(worker)

            # Immediately return a "pending" response
            pending_response = create_pending_response(
                request,
                f"Task '{method}' is being processed in the background",
                meta=request.get('meta', {})
            )
            return json.dumps(pending_response)

    @Slot(object, object)
    def _on_background_task_result(self, request: IPCRequest, result_reponse: IPCResponse):
        """This slot executes in main thread when background task completes successfully"""
        request_id = request['id']
        logger.info(f"[IPCWCService] Background task for request {request_id} completed successfully.")

        # Wrap as standard response format and send back to frontend
        # final_response = create_success_response(request, result_data)
        logger.info(f"[IPCWCService] Final response: {result_reponse}")
        self.python_to_web.emit(json.dumps(result_reponse))

    @Slot(object, object)
    def _on_background_task_error(self, request: IPCRequest, error_response: IPCResponse):
        """This slot executes in main thread when background task fails"""
        request_id = request['id']
        logger.error(f"[IPCWCService] Background task for request {request_id} failed: {error_response.get('error', {}).get('message', '') }")
        self.python_to_web.emit(json.dumps(error_response))

    def _handle_response(self, response: IPCResponse) -> None:
        """Handle response

        Args:
            response: Response object
        """
        try:
            # Get corresponding callback function
            callback = self._request_callbacks.get(response['id'])
            if callback:
                # Call callback function to handle response
                callback(response)
                # Delete callback after processing
                del self._request_callbacks[response['id']]
                logger.trace(f"[IPCWCService] Response handled for request: {response['id']} handle finished")
            else:
                logger.warning(f"[IPCWCService] No callback found for response: {response['id']}")
        except Exception as e:
            logger.error(f"Error handling response: {e}")

    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[IPCResponse], None]] = None
    ) -> None:
        """Send request to Web

        Args:
            method: Method name
            params: Request parameters
            meta: Metadata
            callback: Response callback function
        """
        try:
            # Create request
            request = create_request(method, params, meta)

            # Register callback if provided
            if callback:
                self._request_callbacks[request['id']] = callback
                logger.trace(f"[IPCWCService] Callback registered for request: {request['id']}")

            # Send request
            self.python_to_web.emit(json.dumps(request))
            request_str = json.dumps(request)
            truncated_request = request_str[:800] + "..." if len(request_str) > 500 else request_str
            logger.trace(f"[IPCWCService] Request sent: {truncated_request}")
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            if callback:
                error_response = create_error_response(
                    request,
                    'REQUEST_ERROR',
                    str(e)
                )
                callback(error_response) 