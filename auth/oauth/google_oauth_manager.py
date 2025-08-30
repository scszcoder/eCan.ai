"""
Google OAuth Manager

This module manages the complete Google OAuth authentication flow,
including token exchange, user information retrieval, and Cognito integration.
"""

import json
import secrets
import webbrowser
from typing import Dict, Any, Optional
from urllib.parse import urlencode
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from auth.oauth.local_oauth_server import create_oauth_server
from auth.auth_config import AuthConfig
from utils.logger_helper import logger_helper as logger


class GoogleOAuthManager:
    """
    Manages Google OAuth authentication flow with local callback server
    """
    
    # Google OAuth endpoints
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    
    def __init__(self):
        """Initialize Google OAuth manager with configuration."""
        self.session = self._create_http_session()
        
        # OAuth configuration - use class-level access
        self.client_id = AuthConfig.GOOGLE.CLIENT_ID
        self.client_secret = AuthConfig.GOOGLE.CLIENT_SECRET
        self.scopes = AuthConfig.GOOGLE.SCOPES
        self.redirect_uri_base = AuthConfig.GOOGLE.REDIRECT_URI_BASE
        self.callback_port_range = AuthConfig.GOOGLE.CALLBACK_PORT_RANGE
        
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")
        
        logger.info("Google OAuth manager initialized")
    
    def _create_http_session(self) -> requests.Session:
        """Create HTTP session with retry strategy"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def authenticate(self, scopes: Optional[list] = None, timeout: int = 300) -> Dict[str, Any]:
        """
        Perform complete Google OAuth authentication flow
        
        Args:
            scopes: OAuth scopes to request (default: openid, email, profile)
            timeout: Authentication timeout in seconds
            
        Returns:
            Dict containing authentication result
        """
        scopes = scopes or AuthConfig.GOOGLE.SCOPES
        
        try:
            logger.info("Starting Google OAuth authentication flow")
            
            # Get port range from config
            port_range = tuple(AuthConfig.GOOGLE.CALLBACK_PORT_RANGE)
            
            # Create and start local OAuth server
            with create_oauth_server(timeout=timeout, port_range=port_range) as oauth_server:
                # Generate state for CSRF protection
                state = secrets.token_urlsafe(32)
                
                # Build authentication URL
                auth_url = self._build_auth_url(
                    redirect_uri=oauth_server.get_redirect_uri(),
                    scopes=scopes,
                    state=state,
                    pkce_params=oauth_server.get_pkce_params()
                )
                
                logger.info(f"Opening browser for authentication: {auth_url}")
                
                # Open browser for authentication
                webbrowser.open(auth_url)
                
                # Wait for callback
                callback_result = oauth_server.wait_for_callback()
                
                if not callback_result['success']:
                    return {
                        'success': False,
                        'error': callback_result['error']
                    }
                
                # Verify state parameter
                if callback_result.get('state') != state:
                    logger.error("State parameter mismatch - possible CSRF attack")
                    return {
                        'success': False,
                        'error': 'State parameter mismatch'
                    }
                
                # Exchange authorization code for tokens
                tokens = self._exchange_code_for_tokens(
                    auth_code=callback_result['auth_code'],
                    redirect_uri=oauth_server.get_redirect_uri(),
                    code_verifier=oauth_server.get_code_verifier()
                )
                
                if not tokens['success']:
                    return tokens
                
                # Get user information
                user_info = self._get_user_info(tokens['data']['access_token'])
                
                if not user_info['success']:
                    return user_info
                
                logger.info(f"Google OAuth authentication successful for user: {user_info['data']['email']}")
                
                return {
                    'success': True,
                    'data': {
                        'tokens': tokens['data'],
                        'user_info': user_info['data']
                    }
                }
                
        except Exception as e:
            logger.error(f"Google OAuth authentication failed: {e}")
            return {
                'success': False,
                'error': f'Authentication failed: {str(e)}'
            }
    
    def _build_auth_url(self, redirect_uri: str, scopes: list, state: str, pkce_params: Dict[str, str]) -> str:
        """
        Build Google OAuth authorization URL
        
        Args:
            redirect_uri: OAuth callback URI
            scopes: OAuth scopes
            state: CSRF protection state
            pkce_params: PKCE parameters
            
        Returns:
            Complete authorization URL
        """
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'state': state,
            'access_type': 'offline',  # Request refresh token
            'prompt': 'consent',  # Force consent screen for refresh token
            **pkce_params
        }
        
        return f"{self.GOOGLE_AUTH_URL}?{urlencode(params)}"
    
    def _exchange_code_for_tokens(self, auth_code: str, redirect_uri: str, code_verifier: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens
        
        Args:
            auth_code: Authorization code from callback
            redirect_uri: OAuth callback URI
            code_verifier: PKCE code verifier
            
        Returns:
            Dict containing tokens or error
        """
        try:
            logger.debug("Exchanging authorization code for tokens")
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': auth_code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
                'code_verifier': code_verifier
            }
            
            response = self.session.post(
                self.GOOGLE_TOKEN_URL,
                data=data,
                timeout=30
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error_description', f'HTTP {response.status_code}')
                logger.error(f"Token exchange failed: {error_msg}")
                return {
                    'success': False,
                    'error': f'Token exchange failed: {error_msg}'
                }
            
            tokens = response.json()
            
            # Validate required tokens
            if 'access_token' not in tokens:
                logger.error("Access token not received")
                return {
                    'success': False,
                    'error': 'Access token not received'
                }
            
            logger.info("Token exchange successful")
            return {
                'success': True,
                'data': {
                    'access_token': tokens['access_token'],
                    'id_token': tokens.get('id_token'),
                    'refresh_token': tokens.get('refresh_token'),
                    'expires_in': tokens.get('expires_in', 3600),
                    'token_type': tokens.get('token_type', 'Bearer')
                }
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error during token exchange: {e}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}")
            return {
                'success': False,
                'error': f'Token exchange error: {str(e)}'
            }
    
    def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from Google API
        
        Args:
            access_token: Google access token
            
        Returns:
            Dict containing user info or error
        """
        try:
            logger.debug("Fetching user information from Google API")
            
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            response = self.session.get(
                self.GOOGLE_USERINFO_URL,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f'HTTP {response.status_code}'
                logger.error(f"User info request failed: {error_msg}")
                return {
                    'success': False,
                    'error': f'User info request failed: {error_msg}'
                }
            
            user_data = response.json()
            
            # Validate required fields
            if 'email' not in user_data:
                logger.error("User email not available")
                return {
                    'success': False,
                    'error': 'User email not available'
                }
            
            logger.info(f"User information retrieved for: {user_data['email']}")
            return {
                'success': True,
                'data': {
                    'email': user_data['email'],
                    'name': user_data.get('name', ''),
                    'given_name': user_data.get('given_name', ''),
                    'family_name': user_data.get('family_name', ''),
                    'picture': user_data.get('picture', ''),
                    'verified_email': user_data.get('verified_email', False),
                    'locale': user_data.get('locale', 'en')
                }
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error during user info request: {e}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during user info request: {e}")
            return {
                'success': False,
                'error': f'User info error: {str(e)}'
            }
    
    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Google refresh token
            
        Returns:
            Dict containing new tokens or error
        """
        try:
            logger.debug("Refreshing access token")
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            }
            
            response = self.session.post(
                self.GOOGLE_TOKEN_URL,
                data=data,
                timeout=30
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error_description', f'HTTP {response.status_code}')
                logger.error(f"Token refresh failed: {error_msg}")
                return {
                    'success': False,
                    'error': f'Token refresh failed: {error_msg}'
                }
            
            tokens = response.json()
            
            logger.info("Token refresh successful")
            return {
                'success': True,
                'data': {
                    'access_token': tokens['access_token'],
                    'id_token': tokens.get('id_token'),
                    'expires_in': tokens.get('expires_in', 3600),
                    'token_type': tokens.get('token_type', 'Bearer')
                }
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error during token refresh: {e}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            return {
                'success': False,
                'error': f'Token refresh error: {str(e)}'
            }
    
    def revoke_token(self, token: str) -> Dict[str, Any]:
        """
        Revoke Google token
        
        Args:
            token: Token to revoke (access or refresh token)
            
        Returns:
            Dict containing revocation result
        """
        try:
            logger.debug("Revoking Google token")
            
            response = self.session.post(
                'https://oauth2.googleapis.com/revoke',
                data={'token': token},
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("Token revocation successful")
                return {'success': True}
            else:
                logger.warning(f"Token revocation failed: HTTP {response.status_code}")
                return {
                    'success': False,
                    'error': f'Revocation failed: HTTP {response.status_code}'
                }
                
        except Exception as e:
            logger.error(f"Error during token revocation: {e}")
            return {
                'success': False,
                'error': f'Revocation error: {str(e)}'
            }
