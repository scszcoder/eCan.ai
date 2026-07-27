"""
验证码存储（用于手机号登录/注册/密码重置）

开发环境使用内存存储，生产环境应使用 Redis
"""

import time
import secrets
from dataclasses import dataclass
from typing import Optional, Dict
from threading import Lock


@dataclass
class CodeEntry:
    code: str
    purpose: str
    created_at: float
    expires_at: float
    attempts: int = 0


class CodeStore:
    """
    验证码存储

    使用内存字典存储验证码，支持：
    - 60 秒发送冷却
    - 5 分钟过期
    - 最多 5 次验证尝试
    """

    def __init__(self):
        self._codes: Dict[str, CodeEntry] = {}
        self._last_send: Dict[str, float] = {}
        self._lock = Lock()

    def _normalize_phone(self, phone: str) -> str:
        return phone.strip().replace(" ", "").replace("-", "").replace("+86", "")

    def generate_code(self, phone: str, purpose: str = "login",
                     ttl_seconds: int = 300, cooldown_seconds: int = 60) -> Optional[str]:
        """
        生成验证码

        Returns:
            验证码字符串；如果处于冷却期，返回 None
        """
        phone = self._normalize_phone(phone)
        key = f"{phone}:{purpose}"
        now = time.time()

        with self._lock:
            last = self._last_send.get(key, 0)
            if now - last < cooldown_seconds:
                remaining = int(cooldown_seconds - (now - last))
                raise CooldownError(f"请等待 {remaining} 秒后再试")

            code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

            self._codes[key] = CodeEntry(
                code=code,
                purpose=purpose,
                created_at=now,
                expires_at=now + ttl_seconds,
                attempts=0,
            )
            self._last_send[key] = now

            self._cleanup_expired()

            return code

    def verify_code(self, phone: str, code: str, purpose: str = "login",
                   max_attempts: int = 5) -> bool:
        """
        验证验证码

        Returns:
            是否验证成功
        """
        phone = self._normalize_phone(phone)
        key = f"{phone}:{purpose}"

        with self._lock:
            entry = self._codes.get(key)
            if not entry:
                return False

            if time.time() > entry.expires_at:
                self._codes.pop(key, None)
                return False

            entry.attempts += 1
            if entry.attempts > max_attempts:
                self._codes.pop(key, None)
                return False

            if entry.code != code:
                return False

            self._codes.pop(key, None)
            return True

    def _cleanup_expired(self):
        """清理过期的验证码"""
        now = time.time()
        expired = [k for k, v in self._codes.items() if v.expires_at < now]
        for k in expired:
            self._codes.pop(k, None)


class CooldownError(Exception):
    """发送冷却中"""
    pass


_code_store_instance: Optional[CodeStore] = None


def get_code_store() -> CodeStore:
    """获取验证码存储单例"""
    global _code_store_instance
    if _code_store_instance is None:
        _code_store_instance = CodeStore()
    return _code_store_instance
