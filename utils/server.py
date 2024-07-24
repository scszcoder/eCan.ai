# 寻找一个未使用的端口
import http
import os
import shutil
import socket
import urllib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread


class CustomHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(http.HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/api/v1/image':
            self.localhost_file()
        else:
            super().do_GET()

    def localhost_file(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(parsed_path.query))
        file_path = query.get('file')
        # 检查文件是否存在
        if os.path.exists(file_path):
            # 设置响应状态码
            self.send_response(200)

            # 设置响应头
            self.send_header('Content-type', 'image/png')  # 假设文件类型是PNG
            self.end_headers()

            # 读取文件并发送到客户端
            with open(file_path, 'rb') as file:
                shutil.copyfileobj(file, self.wfile)
        else:
            # 文件不存在，返回404错误
            self.send_error(404, "File Not Found")


class HttpServer:
    def __init__(self, main_window):
        self.port = self.find_free_port()
        self.port = 8888
        print("Server started on port:", self.port)
        self.httpd = self.start_http_server(main_window.homepath + '/ecbot-ui/dist', self.port)

    def find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', 0))
            return s.getsockname()[1]

    def start_http_server(self, directory, port):
        os.chdir(directory)  # 切换到指定目录
        httpd = HTTPServer(('localhost', port), CustomHandler)
        httpd_thread = Thread(target=httpd.serve_forever)
        httpd_thread.daemon = True
        httpd_thread.start()
        return httpd

    def close_server(self):
        self.httpd.shutdown()
