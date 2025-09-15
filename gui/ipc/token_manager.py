"""
Token 管理系统
处理用户认证 token 的生成、验证、存储和过期管理
"""
import uuid
import time
from typing import Dict, Optional, Set
from utils.logger_helper import logger_helper as logger

class TokenManager:
    """Token 管理器"""
    
    def __init__(self):
        self._tokens: Dict[str, Dict] = {}  # token -> {user, created_at, expires_at, permissions}
        self._user_tokens: Dict[str, str] = {}  # username -> current_token
        self._token_expiry = 24 * 60 * 60  # 24小时过期
        
    def generate_token(self, username: str, role: str = 'user', permissions: Set[str] = None) -> str:
        """生成新的 token"""
        # 清理用户的旧 token
        if username in self._user_tokens:
            old_token = self._user_tokens[username]
            if old_token in self._tokens:
                del self._tokens[old_token]
        
        # 生成新 token
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
        """验证 token 有效性"""
        if not token or token not in self._tokens:
            return None
        
        token_info = self._tokens[token]
        current_time = time.time()
        
        # 检查是否过期
        if current_time > token_info['expires_at']:
            logger.warning(f"[TokenManager] Token expired for user: {token_info['username']}")
            self.revoke_token(token)
            return None
        
        # 更新最后使用时间
        token_info['last_used'] = current_time
        
        return token_info
    
    def revoke_token(self, token: str) -> bool:
        """撤销 token"""
        if token not in self._tokens:
            return False
        
        token_info = self._tokens[token]
        username = token_info['username']
        
        # 清理 token
        del self._tokens[token]
        if username in self._user_tokens and self._user_tokens[username] == token:
            del self._user_tokens[username]
        
        logger.info(f"[TokenManager] Revoked token for user: {username}")
        return True
    
    def revoke_user_tokens(self, username: str) -> bool:
        """撤销用户的所有 token"""
        if username not in self._user_tokens:
            return False
        
        token = self._user_tokens[username]
        return self.revoke_token(token)
    
    def get_user_info(self, token: str) -> Optional[Dict]:
        """根据 token 获取用户信息"""
        token_info = self.validate_token(token)
        if not token_info:
            return None
        
        return {
            'username': token_info['username'],
            'role': token_info['role'],
            'permissions': token_info['permissions']
        }
    
    def cleanup_expired_tokens(self) -> int:
        """清理过期的 token"""
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
        """延长 token 有效期"""
        if token not in self._tokens:
            return False
        
        if additional_seconds is None:
            additional_seconds = self._token_expiry
        
        self._tokens[token]['expires_at'] = time.time() + additional_seconds
        logger.debug(f"[TokenManager] Extended token expiry by {additional_seconds} seconds")
        return True
    
    def get_active_tokens_count(self) -> int:
        """获取活跃 token 数量"""
        self.cleanup_expired_tokens()
        return len(self._tokens)
    
    def get_token_stats(self) -> Dict:
        """获取 token 统计信息"""
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

# 全局 token 管理器实例
token_manager = TokenManager()

# 定时清理过期 token
import threading
import time

def cleanup_expired_tokens_periodically():
    """定期清理过期 token"""
    while True:
        try:
            time.sleep(3600)  # 每小时清理一次
            token_manager.cleanup_expired_tokens()
        except Exception as e:
            logger.error(f"[TokenManager] Error in periodic cleanup: {e}")

# 启动后台清理线程
cleanup_thread = threading.Thread(target=cleanup_expired_tokens_periodically, daemon=True)
cleanup_thread.start()
