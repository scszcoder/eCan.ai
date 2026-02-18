import os
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config


import requests
from jose import jwt
from jose.exceptions import JOSEError

from utils.logger_helper import logger_helper as logger
from auth.auth_config import AuthConfig
from auth.performance_config import perf_config

class CognitoService:

    def __init__(self):
        self.cognito_client = None
        self.jwks = None
        # Preload JWKS to avoid blocking during login
        self._preload_jwks()

    def _get_cognito_client(self):
        if not self.cognito_client:
            # Get timeout settings from performance configuration
            cognito_config = perf_config.get_cognito_config()

            # Configure timeouts and connection pool for performance optimization
            config = Config(
                read_timeout=cognito_config['read_timeout'],
                connect_timeout=cognito_config['connect_timeout'],
                retries={'max_attempts': cognito_config['max_attempts']},
                max_pool_connections=cognito_config['max_pool_connections']
            )
            self.cognito_client = boto3.client(
                'cognito-idp',
                region_name=AuthConfig.COGNITO.REGION,
                config=config
            )

            if perf_config.should_log_timing():
                logger.info(f"Cognito client configured: connect_timeout={cognito_config['connect_timeout']}s, "
                          f"read_timeout={cognito_config['read_timeout']}s, "
                          f"max_attempts={cognito_config['max_attempts']}, "
                          f"connection_pool={cognito_config['max_pool_connections']}")

        return self.cognito_client

    def _preload_jwks(self):
        """
        Preload JWKS during initialization to avoid blocking during login.
        This is called in __init__ to fetch JWKS early, reducing login latency.
        """
        import time
        start_time = time.time()
        url = f"https://cognito-idp.{AuthConfig.COGNITO.REGION}.amazonaws.com/{AuthConfig.COGNITO.USER_POOL_ID}/.well-known/jwks.json"
        
        try:
            logger.info(f"[CognitoService] Preloading JWKS from: {url}")
            # Increase timeout for China -> AWS (90 seconds)
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            self.jwks = response.json()['keys']
            elapsed = time.time() - start_time
            logger.info(f"[CognitoService] ✅ JWKS preloaded successfully in {elapsed:.2f}s ({len(self.jwks)} keys)")
        except requests.exceptions.RequestException as e:
            elapsed = time.time() - start_time
            logger.error(f"[CognitoService] ❌ Failed to preload JWKS after {elapsed:.2f}s: {e}")
            logger.warning(f"[CognitoService] Token verification will retry JWKS fetch during login")
            self.jwks = None

    def _get_jwks(self):
        """
        Get JWKS (JSON Web Key Set) for token verification.
        This should normally be preloaded during __init__, but will fetch on-demand if needed.
        """
        # If already cached, return immediately
        if self.jwks:
            return self.jwks
            
        # Otherwise, fetch now (fallback for preload failure)
        import time
        start_time = time.time()
        url = f"https://cognito-idp.{AuthConfig.COGNITO.REGION}.amazonaws.com/{AuthConfig.COGNITO.USER_POOL_ID}/.well-known/jwks.json"
        
        try:
            logger.warning(f"[CognitoService] JWKS not cached, fetching on-demand from: {url}")
            # Increase timeout for China -> AWS (90 seconds)
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            self.jwks = response.json()['keys']
            elapsed = time.time() - start_time
            logger.info(f"[CognitoService] ✅ JWKS fetched on-demand in {elapsed:.2f}s ({len(self.jwks)} keys)")
            return self.jwks
        except requests.exceptions.RequestException as e:
            elapsed = time.time() - start_time
            logger.error(f"[CognitoService] ❌ Failed to fetch JWKS after {elapsed:.2f}s: {e}")
            return None

    def verify_token(self, token: str, token_use: str = 'access'):
        if not self.jwks:
            self.jwks = self._get_jwks()
            if not self.jwks:
                return {'success': False, 'error': 'JWKS not available'}

        try:
            unverified_header = jwt.get_unverified_header(token)
        except JOSEError as e:
            return {'success': False, 'error': f'Invalid token header: {e}'}

        kid = unverified_header.get('kid')
        if not kid:
            return {'success': False, 'error': 'Token header is missing "kid"'}

        key = next((k for k in self.jwks if k['kid'] == kid), None)
        if not key:
            return {'success': False, 'error': 'Public key not found in JWKS'}

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=AuthConfig.COGNITO.CLIENT_ID,
                issuer=f"https://cognito-idp.{AuthConfig.COGNITO.REGION}.amazonaws.com/{AuthConfig.COGNITO.USER_POOL_ID}"
            )

            if claims.get('token_use') != token_use:
                return {'success': False, 'error': f'Invalid token_use claim. Expected "{token_use}"'}

            return {'success': True, 'data': claims}

        except JOSEError as e:
            return {'success': False, 'error': f'Token is invalid: {e}'}

    def sign_up(self, username, password):
        try:
            client = self._get_cognito_client()
            response = client.sign_up(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username,
                Password=password,
                UserAttributes=[{'Name': 'email', 'Value': username}]
            )
            return {'success': True, 'data': response}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}

    def confirm_sign_up(self, username, confirmation_code):
        try:
            client = self._get_cognito_client()
            response = client.confirm_sign_up(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username,
                ConfirmationCode=confirmation_code
            )
            return {'success': True, 'data': response}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}

    def login(self, username, password):
        import time
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        start_time = time.time()

        # Overall timeout to prevent indefinite waiting (e.g., DNS/SSL delays beyond boto3's control)
        # boto3 retries internally (max_attempts * (connect_timeout + read_timeout) ≈ 105s worst case)
        # We add a hard ceiling of 60s to fail fast for users in high-latency networks
        auth_flow_config = perf_config.get_auth_flow_config()
        overall_timeout = auth_flow_config.get('total_timeout', 30)

        try:
            if perf_config.should_log_timing():
                logger.info(f"Starting Cognito authentication: {username}")

            client = self._get_cognito_client()

            def _do_auth():
                return client.initiate_auth(
                    ClientId=AuthConfig.COGNITO.CLIENT_ID,
                    AuthFlow='USER_PASSWORD_AUTH',
                    AuthParameters={
                        'USERNAME': username,
                        'PASSWORD': password
                    }
                )

            # Execute with overall timeout to prevent 185s+ waits
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_auth)
                try:
                    response = future.result(timeout=overall_timeout)
                except FuturesTimeoutError:
                    elapsed_time = time.time() - start_time
                    logger.error(f"Cognito authentication overall timeout: {username}, "
                               f"timeout={overall_timeout}s, elapsed: {elapsed_time:.2f}s")
                    # Reset cognito_client so next attempt creates a fresh connection
                    self.cognito_client = None
                    return {'success': False, 'error': f'Authentication timeout after {overall_timeout}s. Please check your network connection.'}

            elapsed_time = time.time() - start_time

            # Log success
            if perf_config.should_log_timing():
                logger.info(f"Cognito authentication successful: {username}, elapsed: {elapsed_time:.2f}s")

            # Performance alert
            alert_threshold = perf_config.get_alert_threshold()
            if elapsed_time > alert_threshold:
                logger.warning(f"⚠️ Cognito authentication took too long: {elapsed_time:.2f}s > {alert_threshold}s, "
                             f"user: {username}")

            return {'success': True, 'data': response['AuthenticationResult']}

        except ClientError as e:
            elapsed_time = time.time() - start_time
            error_code = e.response['Error']['Code']
            logger.error(f"Cognito authentication failed: {username}, error: {error_code}, elapsed: {elapsed_time:.2f}s")
            return {'success': False, 'error': error_code}
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Cognito authentication exception: {username}, exception: {str(e)}, elapsed: {elapsed_time:.2f}s")
            return {'success': False, 'error': f'Authentication exception: {str(e)}'}


    def get_google_login_url(self, redirect_uri, pkce_params: dict | None = None):
        """Constructs the Cognito Hosted UI URL that initiates the Google login flow.
        Optionally includes PKCE parameters when provided.
        """
        # Key Parameters:
        # - identity_provider=Google: Tells Cognito to redirect directly to Google for authentication instead of showing the Cognito login page.
        # - response_type=code:       Indicates that we expect a one-time authorization code via the callback upon successful authentication.
        # - redirect_uri:             Tells Cognito where to redirect the user after authentication is complete (our local server).
        cognito_domain = AuthConfig.COGNITO.DOMAIN
        client_id = AuthConfig.COGNITO.CLIENT_ID

        base_url = f"{cognito_domain}/oauth2/authorize"
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'identity_provider': 'Google',
            'scope': 'openid profile email'
        }

        if pkce_params:
            params.update(pkce_params)

        from urllib.parse import urlencode
        url = f"{base_url}?{urlencode(params)}"
        return {'success': True, 'data': {'url': url}}

    def exchange_code_for_tokens(self, code, redirect_uri, code_verifier: str | None = None):
        """Performs a secure, server-to-server request to exchange an authorization code for JWTs.
        If PKCE was used in the authorization request, the matching code_verifier must be provided.
        """
        # Key Parameters:
        # - grant_type='authorization_code': Specifies that we are using the Authorization Code Grant flow.
        # - code:                          The one-time authorization code captured from the local server callback.
        # - client_id/client_secret:       Authenticates our application client.
        # This is a back-channel request; the user's browser is not involved, ensuring the exchange is secure.
        cognito_domain = AuthConfig.COGNITO.DOMAIN
        client_id = AuthConfig.COGNITO.CLIENT_ID
        client_secret = AuthConfig.COGNITO.CLIENT_SECRET

        url = f"{cognito_domain}/oauth2/token"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        auth = (client_id, client_secret) if client_secret else None

        data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'code': code,
            'redirect_uri': redirect_uri
        }
        if code_verifier:
            data['code_verifier'] = code_verifier

        try:
            # Add timeout to prevent infinite waiting (120 seconds for China -> AWS)
            # requests library automatically uses HTTP_PROXY/HTTPS_PROXY environment variables
            http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
            https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            if https_proxy or http_proxy:
                logger.info(f"[Cognito] Using proxy for token exchange: {https_proxy or http_proxy}")
            else:
                logger.warning("[Cognito] No proxy configured - direct connection to AWS (may be slow from China)")
            
            response = requests.post(url, headers=headers, data=data, auth=auth, timeout=120)
            response.raise_for_status()
            # On success, the response body will contain the access_token, id_token, and refresh_token.
            logger.info("AuthManager: Token exchange successful")
            return {'success': True, 'data': response.json()}
        except requests.exceptions.Timeout:
            logger.error("AuthManager: Token exchange timeout after 120 seconds")
            return {'success': False, 'error': 'Token exchange request timed out after 120 seconds. Please check your network connection or proxy settings.'}
        except requests.exceptions.RequestException as e:
            error_msg = e.response.json() if e.response else str(e)
            logger.error(f"AuthManager: Token exchange failed: {error_msg}")
            return {'success': False, 'error': error_msg}

    def forgot_password(self, username):
        try:
            client = self._get_cognito_client()
            response = client.forgot_password(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username
            )
            return {'success': True, 'data': response}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}

    def confirm_forgot_password(self, username, confirmation_code, new_password):
        try:
            client = self._get_cognito_client()
            response = client.confirm_forgot_password(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username,
                ConfirmationCode=confirmation_code,
                Password=new_password
            )
            return {'success': True, 'data': response}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}



    def refresh_tokens(self, refresh_token):
        """Refresh tokens using the refresh token."""
        try:
            client = self._get_cognito_client()
            response = client.initiate_auth(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={'REFRESH_TOKEN': refresh_token}
            )
            # The new response contains a new AccessToken and IdToken.
            # It does NOT contain a new RefreshToken unless configured to do so.
            # We will merge the new tokens with the existing refresh token.
            new_tokens = response['AuthenticationResult']
            new_tokens['RefreshToken'] = refresh_token
            return {'success': True, 'data': new_tokens}
        except ClientError as e:
            logger.error(f"CognitoService: Token refresh failed: {e.response['Error']['Code']}")
            return {'success': False, 'error': e.response['Error']['Code']}


    def get_userinfo(self, access_token: str):
        """Calls Cognito's OIDC userInfo endpoint to fetch user claims (like email)."""
        try:
            url = f"{AuthConfig.COGNITO.DOMAIN}/oauth2/userInfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            # Increase timeout for China -> AWS (60 seconds)
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": e.response.json() if getattr(e, 'response', None) else str(e)}
