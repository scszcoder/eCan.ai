"""
Token Management System
Handles user authentication token generation, validation, storage and expiration management
"""
import uuid
import time
from typing import Dict, Optional, Set
from utils.logger_helper import logger_helper as logger

class TokenManager:
    """Token Manager"""

    def __init__(self):
        self._tokens: Dict[str, Dict] = {}  # token -> {user, created_at, expires_at, permissions}
        self._user_tokens: Dict[str, str] = {}  # username -> current_token
        self._token_expiry = 24 * 60 * 60  # 24 hours expiration

    def generate_token(self, username: str, role: str = 'user', permissions: Set[str] = None) -> str:
        """Generate new token"""
        # Clean up user's old token
        if username in self._user_tokens:
            old_token = self._user_tokens[username]
            if old_token in self._tokens:
                del self._tokens[old_token]

        # Generate new token
        token = str(uuid.uuid4()).replace('-', '')
        current_time = time.time()

        token_info = {
            'username': username,
            'role': role,
            'permissions': permissions or set(),
            'created_at': current_time,
            'expires_at': current_time + self._token_expiry,
            'last_used': current_time
        }

        self._tokens[token] = token_info
        self._user_tokens[username] = token

        logger.info(f"[TokenManager] Generated token for user: {username}, role: {role}")
        return token

    def validate_token(self, token: str) -> Optional[Dict]:
        """Validate token validity"""
        if not token or token not in self._tokens:
            return None

        token_info = self._tokens[token]
        current_time = time.time()

        # Check if expired
        if current_time > token_info['expires_at']:
            logger.warning(f"[TokenManager] Token expired for user: {token_info['username']}")
            self.revoke_token(token)
            return None

        # Update last used time
        token_info['last_used'] = current_time

        return token_info

    def revoke_token(self, token: str) -> bool:
        """Revoke token"""
        if token not in self._tokens:
            return False

        token_info = self._tokens[token]
        username = token_info['username']

        # Clean up token
        del self._tokens[token]
        if username in self._user_tokens and self._user_tokens[username] == token:
            del self._user_tokens[username]

        logger.info(f"[TokenManager] Revoked token for user: {username}")
        return True

    def revoke_user_tokens(self, username: str) -> bool:
        """Revoke all tokens for user"""
        if username not in self._user_tokens:
            return False

        token = self._user_tokens[username]
        return self.revoke_token(token)

    def get_user_info(self, token: str) -> Optional[Dict]:
        """Get user information by token"""
        token_info = self.validate_token(token)
        if not token_info:
            return None

        return {
            'username': token_info['username'],
            'role': token_info['role'],
            'permissions': token_info['permissions']
        }

    def cleanup_expired_tokens(self) -> int:
        """Clean up expired tokens"""
        current_time = time.time()
        expired_tokens = []

        for token, token_info in self._tokens.items():
            if current_time > token_info['expires_at']:
                expired_tokens.append(token)

        for token in expired_tokens:
            self.revoke_token(token)

        if expired_tokens:
            logger.info(f"[TokenManager] Cleaned up {len(expired_tokens)} expired tokens")

        return len(expired_tokens)

    def extend_token(self, token: str, additional_seconds: int = None) -> bool:
        """Extend token validity period"""
        if token not in self._tokens:
            return False

        if additional_seconds is None:
            additional_seconds = self._token_expiry

        self._tokens[token]['expires_at'] = time.time() + additional_seconds
        logger.debug(f"[TokenManager] Extended token expiry by {additional_seconds} seconds")
        return True

    def get_active_tokens_count(self) -> int:
        """Get active token count"""
        self.cleanup_expired_tokens()
        return len(self._tokens)

    def get_token_stats(self) -> Dict:
        """Get token statistics"""
        self.cleanup_expired_tokens()

        stats = {
            'total_tokens': len(self._tokens),
            'active_users': len(self._user_tokens),
            'tokens_by_role': {}
        }

        for token_info in self._tokens.values():
            role = token_info['role']
            stats['tokens_by_role'][role] = stats['tokens_by_role'].get(role, 0) + 1

        return stats

# Global token manager instance
token_manager = TokenManager()

# Periodically clean up expired tokens
import threading
import time

def cleanup_expired_tokens_periodically():
    """Periodically clean up expired tokens"""
    while True:
        try:
            time.sleep(3600)  # Clean up every hour
            token_manager.cleanup_expired_tokens()
        except Exception as e:
            logger.error(f"[TokenManager] Error in periodic cleanup: {e}")

# Start background cleanup thread
cleanup_thread = threading.Thread(target=cleanup_expired_tokens_periodically, daemon=True)
cleanup_thread.start()
