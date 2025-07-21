from PySide6.QtCore import QObject, Slot, Signal, QRunnable, QThreadPool
from utils.logger_helper import logger_helper as logger
import json
from typing import Optional, Dict, Any, Callable
from .types import (
    IPCRequest, IPCResponse, create_pending_response, create_request, create_error_response, create_success_response
)
from .registry import IPCHandlerRegistry
import traceback


# 1. 为工作线程创建一个信号通信器
class WorkerSignals(QObject):
    """定义了从工作线程发出的信号"""
    result = Signal(object, object)  # request, ipc_response
    error = Signal(object, object)  # request, ipc_response

# 2. 创建一个通用的 QRunnable 工作任务
class Worker(QRunnable):
    """可运行的工作线程，执行耗时任务"""
    def __init__(self, handler: Callable, request: IPCRequest):
        super().__init__()
        self.handler = handler
        self.request = request
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """在后台线程中执行任务"""
        request_id = self.request.get('id', '')
        try:
            params = self.request.get('params')
            response: IPCResponse = self.handler(self.request, params)
            self.signals.result.emit(self.request, response)
        except Exception as e:
            logger.error(f"Error in background worker for request {request_id}: {e}", exc_info=True)
            error_details = traceback.format_exc()
            response = create_error_response(self.request, 'WORKER_ERROR', f"{str(e)}\n{error_details}")
            self.signals.error.emit(self.request, response)

class IPCWebChannelService(QObject):
    """IPC 服务类，处理与前端的数据交互"""
    
    # 定义信号
    python_to_web = Signal(str)  # 发送消息到 Web 的信号
    
    def __init__(self):
        super().__init__()
        logger.info("IPC WebChannel service initialized")
        # 存储请求ID和对应的回调函数的映射
        self._request_callbacks: Dict[str, Callable[[IPCResponse], None]] = {}
        self.threadpool = QThreadPool()
        logger.info(f"QThreadPool max thread count: {self.threadpool.maxThreadCount()}")
    
    @Slot(str, result=str)
    def web_to_python(self, message: str) -> str:
        """处理来自 Web 的消息
        
        Args:
            message: JSON 格式的消息字符串
            
        Returns:
            str: JSON 格式的响应消息
        """
        try:
            # 解析消息
            data = json.loads(message)
            data_str = str(data)
            truncated_data = data_str[:800] + "..." if len(data_str) > 500 else data_str
            logger.debug(f"web_to_python: Received message: {truncated_data}")

            # 检查消息类型
            if 'type' not in data:
                logger.warning("Message missing type field")
                return json.dumps(create_error_response(
                    {'id': 'missing_type', 'method': 'unknown'},
                    'MISSING_TYPE',
                    "Message missing type field"
                ))
            
            # 处理响应消息
            if data['type'] == 'response':
                self._handle_response(IPCResponse(**data))
                return json.dumps({"status": "success"})
            
            # 处理请求消息
            if data['type'] == 'request':
                return self._handle_request(IPCRequest(**data))
            
            # 未知消息类型
            logger.warning(f"Unknown message type: {data['type']}")
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
        """处理 IPC 请求，并根据处理器类型分发"""
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
            # 直接在主线程调用同步处理器
            logger.debug(f"Executing sync handler for method: {method}")
            params = request.get('params')
            sync_response = handler(request, params)
            return json.dumps(sync_response)
        
        elif handler_type == 'background':
            # 为后台任务创建一个 Worker 并提交到线程池
            logger.debug(f"Submitting background handler for method: {method} to threadpool")
            worker = Worker(handler, request)
            worker.signals.result.connect(self._on_background_task_result)
            worker.signals.error.connect(self._on_background_task_error)
            self.threadpool.start(worker)
            
            # 立即返回一个 "pending" 响应
            pending_response = create_pending_response(
                request, 
                f"Task '{method}' is being processed in the background",
                meta=request.get('meta', {})
            )
            return json.dumps(pending_response)

    @Slot(object, object)
    def _on_background_task_result(self, request: IPCRequest, result_reponse: IPCResponse):
        """后台任务成功完成时，此槽在主线程中执行"""
        request_id = request['id']
        logger.info(f"Background task for request {request_id} completed successfully.")
        
        # 封装成一个标准的 response 格式发回给前端
        # final_response = create_success_response(request, result_data)
        logger.info(f"Final response: {result_reponse}")
        self.python_to_web.emit(json.dumps(result_reponse))

    @Slot(object, object)
    def _on_background_task_error(self, request: IPCRequest, error_response: IPCResponse):
        """后台任务失败时，此槽在主线程中执行"""
        request_id = request['id']
        logger.error(f"Background task for request {request_id} failed: {error_response.get('error', {}).get('message', '') }")
        self.python_to_web.emit(json.dumps(error_response))
    
    def _handle_response(self, response: IPCResponse) -> None:
        """处理响应
        
        Args:
            response: 响应对象
        """
        try:
            # 获取对应的回调函数
            callback = self._request_callbacks.get(response['id'])
            if callback:
                # 调用回调函数处理响应
                callback(response)
                # 处理完成后删除回调
                del self._request_callbacks[response['id']]
                logger.info(f"Response handled for request: {response['id']} handle finished")
            else:
                logger.warning(f"No callback found for response: {response['id']}")
        except Exception as e:
            logger.error(f"Error handling response: {e}")
    
    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[IPCResponse], None]] = None
    ) -> None:
        """发送请求到 Web
        
        Args:
            method: 方法名
            params: 请求参数
            meta: 元数据
            callback: 响应回调函数
        """
        try:
            # 创建请求
            request = create_request(method, params, meta)
            
            # 如果有回调函数，注册回调
            if callback:
                self._request_callbacks[request['id']] = callback
                logger.debug(f"Callback registered for request: {request['id']}")
            
            # 发送请求
            self.python_to_web.emit(json.dumps(request))
            request_str = json.dumps(request)
            truncated_request = request_str[:800] + "..." if len(request_str) > 500 else request_str
            logger.debug(f"Request sent: {truncated_request}")
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            if callback:
                error_response = create_error_response(
                    request,
                    'REQUEST_ERROR',
                    str(e)
                )
                callback(error_response) 