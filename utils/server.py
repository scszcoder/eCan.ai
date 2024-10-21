import asyncio
import http
import json
import os
import shutil
import socket
import urllib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

from bot.basicSkill import cloudAnalyzeRandomImage8

global cloud_session
global cloud_token


class CustomHandler(SimpleHTTPRequestHandler):
    """
    自定义的 HTTP 请求处理程序
    """

    def end_headers(self):
        """
        在发送响应头时添加跨域相关的头信息
        """
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        """
        处理 OPTIONS 请求
        """
        try:
            self.send_response(http.HTTPStatus.NO_CONTENT)
            self.end_headers()
        except Exception as e:
            print(f"Error handling OPTIONS request: {e}")

    def do_GET(self):
        """
        处理 GET 请求
        """
        try:
            path = self.path.split('?')[0]
            if path == '/api/v1/image':
                self.localhost_file()
            if path == '/api/v1/cloudAnalyzeRandomImage':
                self.cloudAnalyzeRandomImage()
            else:
                super().do_GET()
        except Exception as e:
            print(f"Error handling GET request: {e}")

    def cloudAnalyzeRandomImage(self):
        """
        处理云分析图片的请求
        """
        parsed_path = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(parsed_path.query))
        file_path = query.get('file')

        if file_path and os.path.exists(file_path):
            try:
                data = asyncio.run(cloudAnalyzeRandomImage8(file_path, cloud_session, cloud_token))
                self.send_response_data(200, data, 'success')
            except Exception as e:
                # 处理可能的异常，例如分析图片时的错误
                self.send_response_data(500, None, f'Error during image analysis: {e}')

    def localhost_file(self):
        """
        处理本地文件的请求
        """
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            query = dict(urllib.parse.parse_qsl(parsed_path.query))
            file_path = query.get('file')
            # 检查文件是否存在
            if os.path.exists(file_path):
                self.send_response_image(200, file_path)
            else:
                # 文件不存在，返回 404 错误
                self.send_error(404, "File Not Found")
        except Exception as e:
            print(f"Error handling local file request: {e}")

    def send_response_data(self, code, data, message=None):
        # 设置响应状态码
        self.send_response(code)
        # 设置响应头为 JSON 格式
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        # 构建并发送 JSON 数据
        response_data = {'code': code, 'data': data, 'message': message}
        self.wfile.write(json.dumps(response_data).encode('utf-8'))

    def send_response_image(self, code, message=None):
        # 设置响应状态码
        self.send_response(code)
        # 设置响应头
        self.send_header('Content-type', 'image/png')  # 假设文件类型是 PNG
        self.end_headers()
        # 读取文件并发送到客户端
        with open(message, 'rb') as file:
            shutil.copyfileobj(file, self.wfile)


class HttpServer:
    """
    HTTP 服务器类
    """

    def __init__(self, main_window, session, token):
        self.port = self.find_free_port()
        self.port = 8888
        print("Server started on port:", self.port)
        self.httpd = self.start_http_server(main_window.homepath + '/ecbot-ui/dist', self.port)
        global cloud_session
        cloud_session = session
        global cloud_token
        cloud_token = token

    def find_free_port(self):
        """
        寻找一个未使用的端口
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', 0))
                return s.getsockname()[1]
        except Exception as e:
            print(f"Error finding free port: {e}")

    def start_http_server(self, directory, port):
        """
        启动 HTTP 服务器
        """
        try:
            os.chdir(directory)  # 切换到指定目录
            httpd = HTTPServer(('localhost', port), CustomHandler)
            httpd_thread = Thread(target=httpd.serve_forever)
            httpd_thread.daemon = True
            httpd_thread.start()
            return httpd
        except Exception as e:
            print(f"Error starting HTTP server: {e}")

    def close_server(self):
        """
        关闭服务器
        """
        try:
            self.httpd.shutdown()
        except Exception as e:
            print(f"Error Shutting down server: {e}")
