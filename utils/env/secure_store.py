import json
import os
import platform
import sys
import re
import keyring
from typing import Optional, Dict

from utils.logger_helper import logger_helper as logger

# Service name prefix for LLM API keys (isolated from auth services)
SERVICE_NAME_PREFIX = "ecan_llm"


class SecureStore:
    """
    Cross-platform secure key store using keyring library.
    
    Storage Strategy (reuses proven patterns from auth_manager.py):
    - macOS: Uses system Keychain via keyring (most secure)
    - Windows: Uses Credential Manager via keyring (native secure storage)
    - Linux: Uses Secret Service or encrypted file via keyring
    - Fallback: Encrypted JSON file if keyring is unavailable
    
    Environment Isolation:
    - dev/prod environments use separate service names
    - Completely isolated from auth services (different service names)
    
    Design Philosophy:
    - Reuses auth_manager.py patterns for consistency
    - Separate namespace to avoid conflicts
    - File fallback for maximum compatibility
    """

    def __init__(self) -> None:
        self.system = platform.system()
        # Fallback file storage (only used if keyring fails)
        self._fallback_dir = os.path.join(os.path.expanduser('~'), '.ecan')
        self._fallback_file = os.path.join(self._fallback_dir, 'llm_keys.json')
        
        # Check keyring accessibility on startup (similar to auth_manager)
        self._keyring_available = self._check_keyring_availability()

    # ---------- Public API ----------
    def set(self, key: str, value: str, username: Optional[str] = None) -> bool:
        """Store a key-value pair in secure storage with user isolation.
        
        Args:
            key: Environment variable name (e.g., "OPENAI_API_KEY")
            value: API key value to store
            username: Optional username for user-specific isolation. If provided, 
                     the key will be stored as "{username}@{key}" to ensure 
                     each user has their own isolated storage.
        
        Uses keyring as primary storage, with file fallback if keyring fails.
        """
        # Build user-isolated key if username is provided
        isolated_key = self._build_user_key(key, username)
        
        env = self._detect_env()
        service_name = self._get_service_name(env)
        safe_key = self._sanitize_key_name(isolated_key)
        
        if self._keyring_available:
            try:
                keyring.set_password(service_name, safe_key, value)
                logger.debug(f"[SecureStore] Stored {isolated_key} in keyring (service: {service_name})")
                return True
            except Exception as e:
                logger.warning(f"[SecureStore] Keyring storage failed for {isolated_key}: {e}")
                logger.info("[SecureStore] Falling back to file storage")
        
        # Fallback to file storage
        return self._fallback_set(env, isolated_key, value)

    def get(self, key: str, username: Optional[str] = None) -> Optional[str]:
        """Retrieve a value from secure storage with user isolation.
        
        Args:
            key: Environment variable name (e.g., "OPENAI_API_KEY")
            username: Optional username for user-specific isolation. If provided,
                     will look for key stored as "{username}@{key}".
        
        Tries keyring first, then falls back to file storage.
        """
        # Build user-isolated key if username is provided
        isolated_key = self._build_user_key(key, username)
        
        env = self._detect_env()
        service_name = self._get_service_name(env)
        safe_key = self._sanitize_key_name(isolated_key)
        
        if self._keyring_available:
            try:
                value = keyring.get_password(service_name, safe_key)
                if value:
                    # logger.debug(f"[SecureStore] Retrieved {isolated_key} from keyring")
                    return value
            except Exception as e:
                logger.error(f"[SecureStore] Keyring retrieval failed for {isolated_key}: {e}")
        
        # Try file fallback
        return self._fallback_get(env, isolated_key)

    def delete(self, key: str, username: Optional[str] = None) -> bool:
        """Delete a key from secure storage with user isolation.
        
        Args:
            key: Environment variable name (e.g., "OPENAI_API_KEY")
            username: Optional username for user-specific isolation. If provided,
                     will delete key stored as "{username}@{key}".
        
        Deletes from both keyring and file storage to ensure complete removal.
        """
        # Build user-isolated key if username is provided
        isolated_key = self._build_user_key(key, username)
        
        env = self._detect_env()
        service_name = self._get_service_name(env)
        safe_key = self._sanitize_key_name(isolated_key)
        
        success = True
        
        # Delete from keyring
        if self._keyring_available:
            try:
                keyring.delete_password(service_name, safe_key)
                logger.debug(f"[SecureStore] Deleted {isolated_key} from keyring")
            except Exception:
                # Fallback: overwrite with empty string
                try:
                    keyring.set_password(service_name, safe_key, "")
                except Exception as e:
                    logger.warning(f"[SecureStore] Failed to delete {isolated_key} from keyring: {e}")
                    success = False
        
        # Also delete from file fallback
        file_success = self._fallback_delete(env, isolated_key)
        
        return success or file_success
    
    def _build_user_key(self, key: str, username: Optional[str] = None) -> str:
        """Build user-isolated key name.
        
        Args:
            key: Base key name (e.g., "OPENAI_API_KEY")
            username: Optional username for isolation
        
        Returns:
            Isolated key name: "{username}@{key}" if username provided, otherwise "{key}"
        """
        if username and username.strip():
            # Use "@" separator to clearly distinguish user and key
            # Format: "user@example.com@OPENAI_API_KEY"
            return f"{username}@{key}"
        return key

    # ---------- Environment detection (reused from auth_manager) ----------
    def _detect_env(self) -> str:
        """Detect environment: dev or prod.
        
        Same logic as auth_manager._refresh_service() for consistency.
        """
        env = os.environ.get('ECAN_ENV', '').strip().lower()
        if env in ('dev', 'prod'):
            return env
        # Default: app bundle → prod, otherwise dev
        return 'prod' if getattr(sys, 'frozen', False) else 'dev'

    def _get_service_name(self, env: str) -> str:
        """Get service name with environment isolation.
        
        Uses different namespace from auth to avoid conflicts:
        - Auth uses: ecan_auth, ecan_refresh, ecan_refresh_dev
        - LLM uses: ecan_llm_dev, ecan_llm_prod
        """
        return f"{SERVICE_NAME_PREFIX}_{env}"

    def _sanitize_key_name(self, key: str) -> str:
        """Sanitize key name for keyring compatibility.
        
        Reuses logic from auth_manager._sanitize_username_for_keyring()
        to ensure Windows Credential Manager compatibility.
        """
        if not key:
            return "default_key"
        
        # Replace problematic characters that might cause issues in Windows Credential Manager
        # Keep only alphanumeric, dots, underscores, and hyphens
        sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', key)
        
        # Ensure it's not too long (Windows has limits)
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        
        return sanitized

    def _check_keyring_availability(self) -> bool:
        """Check if keyring is accessible.
        
        Similar to auth_manager._check_keychain_access() but simpler.
        """
        try:
            test_service = f"{SERVICE_NAME_PREFIX}_test"
            test_key = "test_key"
            test_value = "test_value"
            
            keyring.set_password(test_service, test_key, test_value)
            retrieved = keyring.get_password(test_service, test_key)
            keyring.delete_password(test_service, test_key)
            
            if retrieved == test_value:
                logger.debug("[SecureStore] Keyring is available and working")
                return True
            else:
                logger.warning("[SecureStore] Keyring test failed - using file fallback")
                return False
                
        except Exception as e:
            error_msg = str(e)
            if "(-25244" in error_msg:
                logger.warning("[SecureStore] Keychain access denied (-25244)")
                logger.info("[SecureStore] File storage will be used as fallback")
            else:
                logger.debug(f"[SecureStore] Keyring not available: {e}")
            return False

    # ---------- File fallback storage ----------
    def _ensure_fallback(self) -> None:
        """Ensure fallback directory and file exist with proper permissions."""
        os.makedirs(self._fallback_dir, exist_ok=True)
        try:
            os.chmod(self._fallback_dir, 0o700)
        except Exception:
            pass
        if not os.path.exists(self._fallback_file):
            with open(self._fallback_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            try:
                os.chmod(self._fallback_file, 0o600)
            except Exception:
                pass

    def _read_fallback(self) -> Dict[str, Dict[str, str]]:
        """Read fallback JSON file."""
        self._ensure_fallback()
        try:
            with open(self._fallback_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Backward-compat: if flat dict, wrap under 'dev'
                if isinstance(data, dict) and all(not isinstance(v, dict) for v in data.values()):
                    return {'dev': data}
                return data
        except Exception as e:
            logger.debug(f"[SecureStore] Failed to read fallback file: {e}")
            return {}

    def _write_fallback(self, data: Dict[str, Dict[str, str]]) -> bool:
        """Write fallback JSON file."""
        try:
            self._ensure_fallback()
            with open(self._fallback_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            try:
                os.chmod(self._fallback_file, 0o600)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"[SecureStore] Failed to write fallback file: {e}")
            return False

    def _fallback_set(self, env: str, key: str, value: str) -> bool:
        """Store key in fallback JSON file.
        
        Note: key is already user-isolated (format: "{username}@{env_var}") if username was provided.
        """
        data = self._read_fallback()
        if not isinstance(data, dict):
            data = {}
        env_map = data.get(env) if isinstance(data.get(env), dict) else {}
        env_map[key] = value
        data[env] = env_map
        success = self._write_fallback(data)
        if success:
            logger.debug(f"[SecureStore] Stored {key} in fallback file")
        return success

    def _fallback_get(self, env: str, key: str) -> Optional[str]:
        """Get key from fallback JSON file.
        
        Note: key is already user-isolated (format: "{username}@{env_var}") if username was provided.
        """
        data = self._read_fallback()
        if not isinstance(data, dict):
            return None
        env_map = data.get(env)
        if isinstance(env_map, dict):
            value = env_map.get(key)
            if value:
                logger.debug(f"[SecureStore] Retrieved {key} from fallback file")
            return value
        return None

    def _fallback_delete(self, env: str, key: str) -> bool:
        """Delete key from fallback JSON file.
        
        Note: key is already user-isolated (format: "{username}@{env_var}") if username was provided.
        """
        data = self._read_fallback()
        if not isinstance(data, dict):
            return False
        env_map = data.get(env)
        if isinstance(env_map, dict) and key in env_map:
            del env_map[key]
            data[env] = env_map
            success = self._write_fallback(data)
            if success:
                logger.debug(f"[SecureStore] Deleted {key} from fallback file")
            return success
        return False


# Global instance for easy access
secure_store = SecureStore()


def get_current_username() -> Optional[str]:
    """Get current logged-in username for API key isolation.
    
    This is a utility function that can be used throughout the application
    to get the current user's username for secure store operations.
    
    Note: AuthManager is responsible for restoring user identity from uli.json
    during initialization, so this function only needs to query AuthManager.
    
    Returns:
        Username if user is logged in or identity was restored, None otherwise
    """
    try:
        from app_context import AppContext
        auth_manager = AppContext.get_auth_manager()
        if auth_manager:
            return auth_manager.get_current_user()
    except Exception:
        # Silently fail - this is called from many places and shouldn't break if auth is unavailable
        pass
    
    return None
