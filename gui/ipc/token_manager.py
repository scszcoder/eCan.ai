"""
Token Management System
Handles user authentication token generation, validation, storage and expiration management
"""
import uuid
import time
import threading
from typing import Dict, Optional, Set
from utils.logger_helper import logger_helper as logger

class TokenManager:
    """Token Manager"""

    def __init__(self):
        self._tokens: Dict[str, Dict] = {}  # token -> {user, created_at, expires_at, permissions}
        self._user_tokens: Dict[str, str] = {}  # username -> current_token
        self._replaced_tokens: Dict[str, Dict] = {}
        self._token_expiry = 24 * 60 * 60  # 24 hours expiration
        
        # Cleanup thread control
        self._cleanup_stop_event = threading.Event()
        self._cleanup_thread: Optional[threading.Thread] = None

    def generate_token(self, username: str, role: str = 'user', permissions: Set[str] = None, is_refresh: bool = False) -> str:
        """Generate new token and invalidate any existing session for this user
        
        Args:
            username: Username
            role: User role
            permissions: User permissions
            is_refresh: If True, this is a token refresh operation (not a new login/session replacement)
        
        This implements a 'single active session' policy in desktop mode:
        - Desktop mode: When a user logs in on a new device/session, their old session is invalidated
        - Cloud mode: Supports multi-device login, old sessions remain valid
        - The old client will receive INVALID_TOKEN errors and should redirect to login (desktop only)
        """
        import os
        
        # Check if running in cloud mode (supports multi-device login)
        ecan_mode = os.getenv('ECAN_MODE', 'desktop').lower()
        is_cloud_mode = ecan_mode == 'cloud'
        
        session_replaced = False
        
        # Check if user already has a token (session replacement scenario)
        if username in self._user_tokens:
            old_token = self._user_tokens[username]
            if old_token in self._tokens:
                session_replaced = True
                if is_refresh:
                    # Token refresh: Old token will be replaced, but this is expected
                    logger.info(f"[TokenManager] 🔄 Token refresh: Replacing token for user '{username}' (token: {old_token[:8]}...)")
                else:
                    # Session replacement: User logged in from new location
                    logger.warning(f"[TokenManager] 🔄 Session replacement: User '{username}' logged in from new location. "
                                 f"Old session (token: {old_token[:8]}...) will be invalidated.")
                    self._replaced_tokens[old_token] = {
                        'username': username,
                        'replaced_at': time.time(),
                        'reason': 'session_replaced'
                    }
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

        if session_replaced:
            if is_refresh:
                logger.info(f"[TokenManager] ✅ Token refreshed for user: {username}, role: {role}")
            else:
                logger.info(f"[TokenManager] ✅ New session created for user: {username}, role: {role}. Old session invalidated.")
        else:
            logger.info(f"[TokenManager] ✅ Generated token for user: {username}, role: {role}")
        return token

    def validate_token(self, token: str, auto_extend: bool = True) -> Optional[Dict]:
        """Validate token validity with optional auto-extension
        
        Args:
            token: Token to validate
            auto_extend: If True, automatically extend token if it's about to expire
        
        Returns:
            Token info dict if valid, None if invalid or expired
        """
        if not token or token not in self._tokens:
            return None

        token_info = self._tokens[token]
        current_time = time.time()

        # Check if expired
        if current_time > token_info['expires_at']:
            logger.warning(f"[TokenManager] Token expired for user: {token_info['username']}")
            self.revoke_token(token)
            return None

        # Auto-extend token if it's about to expire (less than 1 hour remaining)
        if auto_extend:
            time_remaining = token_info['expires_at'] - current_time
            if time_remaining < 3600:  # Less than 1 hour
                self.extend_token(token)
                logger.info(f"[TokenManager] Auto-extended token for user: {token_info['username']}, remaining time was {time_remaining:.0f}s")

        # Update last used time
        token_info['last_used'] = current_time

        return token_info

    def get_invalid_token_reason(self, token: str) -> Optional[Dict]:
        if not token:
            return None
        replacement = self._replaced_tokens.get(token)
        if replacement:
            return dict(replacement)
        return None

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

        replaced_cutoff = current_time - self._token_expiry
        for token, info in list(self._replaced_tokens.items()):
            if float(info.get('replaced_at') or 0.0) < replaced_cutoff:
                del self._replaced_tokens[token]

        if expired_tokens:
            logger.info(f"[TokenManager] Cleaned up {len(expired_tokens)} expired tokens")

        return len(expired_tokens)

    def extend_token(self, token: str, additional_seconds: int = None) -> bool:
        """Extend token validity period
        
        Args:
            token: Token to extend
            additional_seconds: Seconds to extend (default: full token expiry period)
        
        Returns:
            True if extended successfully, False if token not found
        """
        if token not in self._tokens:
            return False

        if additional_seconds is None:
            additional_seconds = self._token_expiry

        self._tokens[token]['expires_at'] = time.time() + additional_seconds
        logger.debug(f"[TokenManager] Extended token expiry by {additional_seconds} seconds")
        return True
    
    def refresh_token(self, token: str) -> Optional[str]:
        """Refresh token - generate new token with same user info
        
        Args:
            token: Current token to refresh
        
        Returns:
            New token if successful, None if current token invalid
        """
        token_info = self.validate_token(token, auto_extend=False)
        if not token_info:
            logger.warning("[TokenManager] Cannot refresh invalid or expired token")
            return None
        
        # Generate new token with same user info
        # IMPORTANT: Pass is_refresh=True to distinguish from session replacement
        # This prevents the refresh operation from being logged as "session replacement"
        new_token = self.generate_token(
            username=token_info['username'],
            role=token_info['role'],
            permissions=token_info['permissions'],
            is_refresh=True  # Mark this as a refresh operation
        )
        
        logger.info(f"[TokenManager] Refreshed token for user: {token_info['username']}")
        return new_token

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
    
    def start_cleanup_thread(self):
        """Start background cleanup thread"""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            logger.warning("[TokenManager] Cleanup thread already running")
            return
        
        self._cleanup_stop_event.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="TokenCleanup"
        )
        self._cleanup_thread.start()
        logger.info("[TokenManager] Cleanup thread started")
    
    def stop_cleanup_thread(self, timeout: float = 5.0):
        """Stop background cleanup thread gracefully"""
        if not self._cleanup_thread or not self._cleanup_thread.is_alive():
            return
        
        logger.info("[TokenManager] Stopping cleanup thread...")
        self._cleanup_stop_event.set()
        
        # Wait for thread to finish
        self._cleanup_thread.join(timeout=timeout)
        
        if self._cleanup_thread.is_alive():
            logger.warning(f"[TokenManager] Cleanup thread did not stop within {timeout}s")
        else:
            logger.info("[TokenManager] Cleanup thread stopped successfully")
        
        self._cleanup_thread = None
    
    def _cleanup_loop(self):
        """Background cleanup loop - can be interrupted"""
        cleanup_interval = 3600  # 1 hour
        
        while not self._cleanup_stop_event.is_set():
            try:
                # Use wait instead of sleep - can be interrupted immediately
                if self._cleanup_stop_event.wait(timeout=cleanup_interval):
                    # Received stop signal
                    logger.debug("[TokenManager] Cleanup thread received stop signal")
                    break
                
                # Perform cleanup
                removed = self.cleanup_expired_tokens()
                if removed > 0:
                    logger.info(f"[TokenManager] Cleaned up {removed} expired tokens")
            
            except Exception as e:
                logger.error(f"[TokenManager] Error in cleanup loop: {e}")
                # Short wait before continuing
                if self._cleanup_stop_event.wait(timeout=60):
                    break
        
        logger.debug("[TokenManager] Cleanup thread exiting")

# Global token manager instance
token_manager = TokenManager()

# Start background cleanup thread automatically
token_manager.start_cleanup_thread()

# Register cleanup on exit
import atexit
atexit.register(lambda: token_manager.stop_cleanup_thread(timeout=5.0))
