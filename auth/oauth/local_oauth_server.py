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
        """Send success response to browser with user-initiated app launch (Plan A)"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        # Get application scheme
        app_scheme = self._get_application_scheme()
        
        # Get localized messages
        lang = language or self._detect_language()
        title = auth_messages.get_message('oauth_success_title', lang)
        message = auth_messages.get_message('oauth_success_message', lang)
        instruction = auth_messages.get_message('oauth_success_instruction', lang)
        primary_button = auth_messages.get_message('oauth_primary_button', lang)
        secondary_button = auth_messages.get_message('oauth_secondary_button', lang)
        hint = auth_messages.get_message('oauth_app_not_installed_hint', lang)
        
        # Schedule server shutdown after response is sent
        self._schedule_server_shutdown()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    text-align: center; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .container {{ 
                    max-width: 480px;
                    width: 100%;
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 24px;
                    padding: 48px 40px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    color: #333;
                }}
                .icon {{
                    font-size: 72px;
                    margin-bottom: 24px;
                    animation: scaleIn 0.5s ease-out;
                }}
                @keyframes scaleIn {{
                    from {{
                        transform: scale(0);
                        opacity: 0;
                    }}
                    to {{
                        transform: scale(1);
                        opacity: 1;
                    }}
                }}
                h1 {{ 
                    color: #1a1a1a;
                    font-size: 28px;
                    font-weight: 600;
                    margin-bottom: 12px;
                }}
                .message {{ 
                    font-size: 16px; 
                    color: #666;
                    margin-bottom: 8px;
                    line-height: 1.5;
                }}
                .instruction {{
                    font-size: 16px;
                    color: #333;
                    margin-bottom: 32px;
                    line-height: 1.6;
                    font-weight: 500;
                }}
                .button-group {{
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    margin-bottom: 24px;
                }}
                .primary-button {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 16px 32px;
                    border-radius: 12px;
                    font-size: 18px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                    text-decoration: none;
                    display: inline-block;
                }}
                .primary-button:hover {{ 
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
                }}
                .primary-button:active {{
                    transform: translateY(0);
                }}
                .secondary-button {{
                    background: transparent;
                    color: #666;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    text-decoration: none;
                    display: inline-block;
                }}
                .secondary-button:hover {{
                    background: rgba(0, 0, 0, 0.05);
                    color: #333;
                }}
                .hint {{
                    font-size: 13px;
                    color: #999;
                    line-height: 1.5;
                    padding: 16px;
                    background: rgba(0, 0, 0, 0.02);
                    border-radius: 8px;
                    border-left: 3px solid #667eea;
                }}
                .status-message {{
                    margin-top: 16px;
                    font-size: 14px;
                    color: #4CAF50;
                    font-weight: 500;
                    min-height: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">✅</div>
                <h1>{title}</h1>
                <div class="message">{message}</div>
                <div class="instruction">{instruction}</div>
                
                <div class="button-group">
                    <button class="primary-button" id="open-app-btn">
                        {primary_button}
                    </button>
                    <button class="secondary-button" id="close-window-btn">
                        {secondary_button}
                    </button>
                </div>
                
                <div class="hint">{hint}</div>
                <div class="status-message" id="status-message"></div>
                
                <script>
                    const appScheme = '{app_scheme}';
                    let appLaunched = false;

                    function launchApplication() {{
                        if (appLaunched) return;
                        appLaunched = true;

                        // Show status message
                        const statusMsg = document.getElementById('status-message');
                        if (statusMsg) {{
                            statusMsg.textContent = 'Opening application...';
                            statusMsg.style.color = '#667eea';
                        }}

                        // Method 1: Direct location change (most reliable)
                        try {{
                            window.location.href = appScheme;
                        }} catch(e) {{
                            console.log('Direct launch failed:', e);
                        }}

                        // Method 2: Hidden iframe (fallback for some browsers)
                        setTimeout(function() {{
                            try {{
                                const iframe = document.createElement('iframe');
                                iframe.style.display = 'none';
                                iframe.src = appScheme;
                                document.body.appendChild(iframe);
                                
                                // Clean up iframe after a delay
                                setTimeout(function() {{
                                    document.body.removeChild(iframe);
                                }}, 2000);
                            }} catch(e) {{
                                console.log('Iframe method failed:', e);
                            }}
                        }}, 100);

                        // Update status after attempt
                        setTimeout(function() {{
                            if (statusMsg) {{
                                statusMsg.textContent = 'Application opened. You can close this window.';
                                statusMsg.style.color = '#4CAF50';
                            }}
                        }}, 1500);
                    }}

                    function closeWindow() {{
                        // Try to close the window
                        try {{
                            window.close();
                        }} catch(e) {{
                            console.log('Cannot close window:', e);
                        }}
                        
                        // If window.close() doesn't work (some browsers block it),
                        // show a message
                        setTimeout(function() {{
                            const statusMsg = document.getElementById('status-message');
                            if (statusMsg && !document.hidden) {{
                                statusMsg.textContent = 'Please close this tab manually.';
                                statusMsg.style.color = '#999';
                            }}
                        }}, 500);
                    }}

                    // Event listeners
                    document.getElementById('open-app-btn').addEventListener('click', function(e) {{
                        e.preventDefault();
                        launchApplication();
                    }});

                    document.getElementById('close-window-btn').addEventListener('click', function(e) {{
                        e.preventDefault();
                        closeWindow();
                    }});

                    // Keyboard accessibility
                    document.addEventListener('keydown', function(e) {{
                        if (e.key === 'Enter' && !appLaunched) {{
                            launchApplication();
                        }} else if (e.key === 'Escape') {{
                            closeWindow();
                        }}
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

