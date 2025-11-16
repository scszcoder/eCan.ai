"""
Local OAuth Server for handling Google OAuth callbacks

This module implements a temporary local HTTP server that handles OAuth callbacks
from Google. The server is created only when authentication is triggered and is
automatically destroyed after authentication completes or times out.
"""

import http.server
import socketserver
import threading
import socket
import time
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any
import secrets
import base64
import hashlib

from utils.logger_helper import logger_helper as logger
from auth.auth_messages import auth_messages


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callbacks"""
    
    def do_GET(self):
        """
        Handles the incoming GET request from Cognito after the user authenticates with Google.
        This is the method that executes when the browser is redirected to our local server.
        """
        try:
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            
            logger.debug(f"OAuth callback received: {self.path}")
            
            # Handle favicon.ico requests (ignore them silently)
            if self.path == '/favicon.ico':
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Not Found')
                return
            
            # Step 1: Check if the URL parameters contain 'code'.
            if 'code' in params:
                # Step 2: If found, store it on the server instance so the wait_for_callback method can retrieve it.
                self.server.auth_code = params['code'][0]
                self.server.state = params.get('state', [None])[0]
                logger.info("Authorization code received successfully")
                # Step 3: Send a success HTML page back to the user's browser.
                self._send_success_response()
                
            # Check for error
            elif 'error' in params:
                error = params['error'][0]
                error_description = params.get('error_description', ['Unknown error'])[0]
                self.server.auth_error = f"{error}: {error_description}"
                logger.error(f"OAuth error received: {self.server.auth_error}")
                self._send_error_response(error, error_description)
                
            else:
                self.server.auth_error = "Invalid callback parameters"
                logger.error("Invalid OAuth callback parameters")
                self._send_error_response("invalid_request", "Invalid callback parameters")
                
        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}")
            self.server.auth_error = f"Callback handling error: {str(e)}"
            self._send_error_response("server_error", "Internal server error")
    
    def _send_success_response(self, language: str = None):
        """Send success response to browser with scheme-based app launch"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        # Get application scheme
        app_scheme = self._get_application_scheme()
        
        # Get localized messages
        lang = language or self._detect_language()
        title = auth_messages.get_message('oauth_success_title', lang)
        message = auth_messages.get_message('oauth_success_message', lang)
        app_prompt = auth_messages.get_message('oauth_success_app_prompt', lang)
        # Use a single countdown setting and inject into i18n string
        countdown_seconds = 3
        launching_text = auth_messages.get_message('oauth_success_launching', lang).format(countdown=countdown_seconds)
        manual_launch_text = auth_messages.get_message('oauth_manual_launch', lang)
        
        # Schedule server shutdown after response is sent
        self._schedule_server_shutdown()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    text-align: center; 
                    padding: 50px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    margin: 0;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{ 
                    max-width: 500px; 
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 40px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }}
                .success {{ 
                    color: #4CAF50; 
                    margin-bottom: 20px;
                    font-size: 2.5em;
                }}
                .message {{ 
                    font-size: 1.2em; 
                    margin: 20px 0;
                    line-height: 1.6;
                }}
                .countdown {{ 
                    font-size: 1.5em; 
                    font-weight: bold; 
                    color: #FFD700;
                    margin: 20px 0;
                }}
                .progress-bar {{
                    width: 100%;
                    height: 6px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 3px;
                    margin: 20px 0;
                    overflow: hidden;
                }}
                .progress-fill {{
                    height: 100%;
                    background: linear-gradient(90deg, #4CAF50, #45a049);
                    border-radius: 3px;
                    animation: progress {countdown_seconds}s linear;
                }}
                @keyframes progress {{
                    from {{ width: 0%; }}
                    to {{ width: 100%; }}
                }}
                .icon {{
                    font-size: 4em;
                    margin-bottom: 20px;
                }}
                a {{ 
                    color: #FFD700; 
                    text-decoration: none; 
                    font-weight: bold;
                    border: 2px solid #FFD700;
                    padding: 10px 20px;
                    border-radius: 25px;
                    display: inline-block;
                    margin-top: 20px;
                    transition: all 0.3s ease;
                }}
                a:hover {{ 
                    background: #FFD700; 
                    color: #333;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(255, 215, 0, 0.3);
                }}
            </style>
        </head>
            <body>
            <div class="container">
                <div class="success">✅</div>
                <div class="message">{message}</div>
                <div class="message" style="font-size: 1.4em; font-weight: bold; margin-top: 30px;">{app_prompt}</div>
                <div class="progress-bar">
                    <div class="progress-fill"></div>
                </div>
                <div id="launch-message" class="countdown">{launching_text}</div>
                <a href="{app_scheme}" id="manual-launch">{manual_launch_text}</a>
                
                <script>
                    let countdown = {countdown_seconds};
                    let appLaunched = false;

                    function launchApplication() {{
                        if (appLaunched) return;
                        appLaunched = true;

                        // 尝试多种方式拉起客户端
                        // 方法 1: 直接跳转
                        window.location.href = '{app_scheme}';

                        // 方法 2: 隐藏 iframe（兼容性更好）
                        const iframe = document.createElement('iframe');
                        iframe.style.display = 'none';
                        iframe.src = '{app_scheme}';
                        document.body.appendChild(iframe);

                        // 方法 3: 兜底 window.open
                        setTimeout(function() {{
                            try {{
                                window.open('{app_scheme}', '_blank');
                            }} catch(e) {{
                                console.log('Window.open failed:', e);
                            }}
                        }}, 500);

                        // 更新提示文案
                        setTimeout(function() {{
                            const launchMsg = document.getElementById('launch-message');
                            if (launchMsg) {{
                                launchMsg.innerHTML = '{manual_launch_text}';
                                launchMsg.style.color = '#4CAF50';
                            }}
                        }}, 1000);
                    }}

                    function updateCountdown() {{
                        if (countdown > 0) {{
                            countdown--;
                            setTimeout(updateCountdown, 1000);
                        }} else {{
                            // 倒计时结束后，直接尝试拉起客户端
                            launchApplication();
                        }}
                    }}

                    document.addEventListener('DOMContentLoaded', function() {{
                        // 页面加载后只显示成功信息和倒计时
                        updateCountdown();
                    }});

                    // 手动点击“打开应用”按钮时立即尝试拉起客户端
                    document.getElementById('manual-launch').addEventListener('click', function(e) {{
                        e.preventDefault();
                        launchApplication();
                    }});
                </script>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))
    
    def _get_application_scheme(self) -> str:
        """Get the application scheme for launching the app"""
        # This should match the scheme registered in your app
        return 'ecan://'
    
    def _schedule_server_shutdown(self):
        """Schedule server shutdown after a brief delay to ensure response is sent"""
        def delayed_shutdown():
            time.sleep(2)  # Wait 2 seconds to ensure response is fully sent
            if hasattr(self.server, 'should_shutdown'):
                self.server.should_shutdown = True
        
        # Start shutdown in a separate thread
        shutdown_thread = threading.Thread(target=delayed_shutdown, daemon=True)
        shutdown_thread.start()
    
    def _send_error_response(self, error: str, description: str, language: str = None):
        """Send error response to browser"""
        self.send_response(400)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        # Get localized messages
        lang = language or self._detect_language()
        title = auth_messages.get_message('oauth_error_title', lang)
        error_label = auth_messages.get_message('oauth_error_label', lang)
        description_label = auth_messages.get_message('oauth_error_description_label', lang)
        close_instruction = auth_messages.get_message('oauth_error_close_instruction', lang)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    text-align: center; 
                    padding: 50px;
                    background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                    color: white;
                    margin: 0;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .error {{ 
                    color: #fff; 
                    margin-bottom: 20px;
                    font-size: 2.5em;
                }}
                .container {{ 
                    max-width: 500px; 
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 40px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }}
                .icon {{
                    font-size: 4em;
                    margin-bottom: 20px;
                    color: #ff4757;
                }}
                .message {{
                    font-size: 1.2em;
                    margin: 20px 0;
                    line-height: 1.6;
                }}
                .error-details {{
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    padding: 20px;
                    margin: 20px 0;
                    text-align: left;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">✗</div>
                <h1 class="error">{title}</h1>
                <div class="error-details">
                    <p><strong>{error_label}:</strong> {error}</p>
                    <p><strong>{description_label}:</strong> {description}</p>
                </div>
                <p class="message">{close_instruction}</p>
                <p class="message" id="countdown-message"></p>
            </div>
            <script>
                (function() {{
                    // 错误页面倒计时自动关闭逻辑
                    let countdown = 5;  // seconds
                    const countdownEl = document.getElementById('countdown-message');

                    function updateCountdown() {{
                        if (!countdownEl) return;
                        if (countdown > 0) {{
                            countdownEl.textContent = countdown + 's...';
                            countdown--;
                            setTimeout(updateCountdown, 1000);
                        }} else {{
                            // 尝试关闭窗口
                            window.close();
                            // 如果浏览器阻止关闭，则在稍后提示用户手动关闭
                            setTimeout(function() {{
                                if (!countdownEl) return;
                                countdownEl.textContent = '';
                            }}, 2000);
                        }}
                    }}

                    updateCountdown();
                }})();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))
    
    def _detect_language(self) -> str:
        """Detect language from Accept-Language header or return default"""
        try:
            accept_language = self.headers.get('Accept-Language', '')
            if 'zh' in accept_language.lower():
                return 'zh-CN'
            return 'en-US'
        except Exception:
            return 'en-US'
    
    def log_message(self, format, *args):
        """Override to use our logger instead of stderr"""
        logger.debug(f"OAuth Server: {format % args}")


class LocalOAuthServer:
    """
    Local OAuth server for handling authentication callbacks
    
    This server is created only when authentication is triggered and is
    automatically destroyed after authentication completes or times out.
    """
    
    def __init__(self, url: str, timeout: int = 300):
        """
        Initialize the OAuth server.

        Args:
            url: The full callback URL to listen on (e.g., http://127.0.0.1:8080/callback).
            timeout: Server timeout in seconds (default: 5 minutes)
        """
        # Step 1: Parse the full URL to get the hostname and port.
        self.timeout = timeout
        parsed_url = urlparse(url)
        self.hostname = parsed_url.hostname
        self.port = parsed_url.port
        self.url = url
        # Step 2: Check if the port is available, raise an error if it's already in use.
        self._check_port()
        self.server = None
        self.server_thread = None
        self.auth_code = None
        self.auth_error = None
        self.state = None
        self.code_verifier = None
        self.code_challenge = None
        self._generate_pkce_pair()
        
        logger.info(f"OAuth server initialized on port {self.port}")
    
    def _check_port(self):
        """Check if the configured port is available to bind."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.hostname, self.port))
        except OSError as e:
            logger.error(f"Address {self.hostname}:{self.port} is already in use. Please close the other application or change the CALLBACK_URL in auth_config.yml.")
            raise RuntimeError(f"Address {self.hostname}:{self.port} is in use.") from e
    
    def _generate_pkce_pair(self):
        """Generate PKCE code verifier and challenge"""
        # Generate code verifier (43-128 characters)
        self.code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')
        
        # Generate code challenge
        challenge_bytes = hashlib.sha256(self.code_verifier.encode('utf-8')).digest()
        self.code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
        
        logger.debug("PKCE pair generated successfully")
    
    def get_redirect_uri(self) -> str:
        """Get the redirect URI for this server."""
        return self.url
    
    def get_pkce_params(self) -> Dict[str, str]:
        """Get PKCE parameters for OAuth request"""
        return {
            'code_challenge': self.code_challenge,
            'code_challenge_method': 'S256'
        }
    
    def get_code_verifier(self) -> str:
        """Get the code verifier for token exchange"""
        return self.code_verifier
    
    def start_server(self):
        """
        Starts the OAuth callback server in a separate, non-blocking thread.
        This allows the main application to remain responsive while waiting for the callback.
        """
        try:
            self.server = socketserver.TCPServer(
                (self.hostname, self.port),
                OAuthCallbackHandler
            )
            
            # Set server attributes for callback handler
            self.server.auth_code = None
            self.server.auth_error = None
            self.server.state = None
            self.server.should_shutdown = False
            
            # Start server in a separate thread
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True
            )
            self.server_thread.start()
            
            logger.info(f"OAuth server started on http://{self.hostname}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start OAuth server: {e}")
            raise RuntimeError(f"Failed to start OAuth server: {e}")
    
    def wait_for_callback(self) -> Dict[str, Any]:
        """
        Waits for the OAuth callback with a timeout. This is a blocking call.
        It continuously checks for the auth_code or an error set by the OAuthCallbackHandler.
        """
        if not self.server:
            raise RuntimeError("Server not started")
        
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            # Check if we received a callback
            if self.server.auth_code:
                logger.info("OAuth callback received successfully")
                result = {
                    'success': True,
                    'auth_code': self.server.auth_code,
                    'state': self.server.state
                }
                # Wait a moment for response to be sent, then shutdown
                if self.server.should_shutdown:
                    logger.info("OAuth server shutting down after successful authentication")
                    self.shutdown()
                return result
            
            if self.server.auth_error:
                logger.error(f"OAuth callback error: {self.server.auth_error}")
                return {
                    'success': False,
                    'error': self.server.auth_error
                }
            
            # Check if server should shutdown
            if self.server.should_shutdown:
                logger.info("OAuth server received shutdown signal")
                break
            
            # Sleep briefly to avoid busy waiting
            time.sleep(0.1)
        
        # Timeout reached
        logger.error("OAuth callback timeout")
        return {
            'success': False,
            'error': 'Authentication timeout'
        }
    
    def shutdown(self):
        """Shutdown the OAuth server and cleanup resources"""
        try:
            if self.server:
                logger.info("Shutting down OAuth server...")
                self.server.shutdown()
                self.server.server_close()
                
                # Wait for server thread to finish
                if self.server_thread and self.server_thread.is_alive():
                    self.server_thread.join(timeout=5)
                
                self.server = None
                self.server_thread = None
                
                logger.info("OAuth server shutdown complete")
                
        except Exception as e:
            logger.error(f"Error during OAuth server shutdown: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        self.start_server()
        return self
    
    def __exit__(self, *_):
        """Context manager exit - ensures server is always cleaned up"""
        self.shutdown()


def create_oauth_server(url: str, timeout: int = 300) -> LocalOAuthServer:
    """
    Factory function to create a new OAuth server
    
    Args:
        timeout: Server timeout in seconds
        port_range: Tuple of (min_port, max_port) for port allocation
        
    Returns:
        LocalOAuthServer instance
    """
    return LocalOAuthServer(url=url, timeout=timeout)

