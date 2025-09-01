import boto3
from botocore.exceptions import ClientError
from pycognito import AWSSRP

import requests
from jose import jwt
from jose.exceptions import JOSEError

from utils.logger_helper import logger_helper as logger
from auth.auth_config import AuthConfig

class CognitoService:

    def __init__(self):
        self.cognito_client = boto3.client('cognito-idp', region_name=AuthConfig.COGNITO.REGION)
        self.jwks = self._get_jwks()

    def _get_jwks(self):
        # In a production environment, this should be cached.
        url = f"https://cognito-idp.{AuthConfig.COGNITO.REGION}.amazonaws.com/{AuthConfig.COGNITO.USER_POOL_ID}/.well-known/jwks.json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()['keys']
        except requests.exceptions.RequestException as e:
            # In a real app, you'd want to log this error.
            print(f"Error fetching JWKS: {e}")
            return None

    def verify_token(self, token: str, token_use: str = 'access'):
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
            response = self.cognito_client.sign_up(
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
            response = self.cognito_client.confirm_sign_up(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username,
                ConfirmationCode=confirmation_code
            )
            return {'success': True, 'data': response}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}

    def login(self, username, password):
        try:
            aws_srp = AWSSRP(
                username=username,
                password=password,
                pool_id=AuthConfig.COGNITO.USER_POOL_ID,
                client_id=AuthConfig.COGNITO.CLIENT_ID,
                client=self.cognito_client
            )
            tokens = aws_srp.authenticate_user()
            return {'success': True, 'data': tokens}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}


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
            response = requests.post(url, headers=headers, data=data, auth=auth)
            response.raise_for_status()
            # On success, the response body will contain the access_token, id_token, and refresh_token.
            return {'success': True, 'data': response.json()}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': e.response.json() if e.response else str(e)}

    def forgot_password(self, username):
        try:
            response = self.cognito_client.forgot_password(
                ClientId=AuthConfig.COGNITO.CLIENT_ID,
                Username=username
            )
            return {'success': True, 'data': response}
        except ClientError as e:
            return {'success': False, 'error': e.response['Error']['Code']}

    def confirm_forgot_password(self, username, confirmation_code, new_password):
        try:
            response = self.cognito_client.confirm_forgot_password(
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
            response = self.cognito_client.initiate_auth(
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
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": e.response.json() if getattr(e, 'response', None) else str(e)}
