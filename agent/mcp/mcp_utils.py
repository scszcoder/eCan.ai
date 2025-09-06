import asyncio
import socket
import time
from urllib.parse import urlparse

import httpx
from utils.logger_helper import logger_helper as logger


async def wait_until_server_ready(url: str, timeout=30):
    """
    更稳健的服务器就绪等待：
    1) 先等待 TCP 端口进入监听状态；
    2) 再轮询 /healthz；
    仅使用 httpx 的超时，不再叠加 asyncio.wait_for；复用连接池。
    """
    deadline = time.time() + float(timeout)
    last_error = None

    logger.info(f"Waiting for server ready at {url}, timeout: {timeout}s")

    # 解析 URL 获取主机和端口（用于 TCP 探测）
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if (parsed.scheme or "http") == "https" else 80)

    # 第一阶段：端口监听探测（快速轮询，避免首启盲等 HTTP）
    port_attempts = 0
    while time.time() < deadline:
        port_attempts += 1
        try:
            with socket.create_connection((host, port), timeout=1.0) as s:
                s.close()
                logger.debug(f"TCP {host}:{port} is listening (after {port_attempts} attempts)")
                break
        except OSError as e:
            last_error = f"TCP connect failed: {e}"
        await asyncio.sleep(0.3)
    else:
        error_msg = f"Server port not listening at {host}:{port} within {timeout}s. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # 第二阶段：HTTP 健康检查（复用客户端 + 单层超时）
    http_attempts = 0
    # 初始超时配置；后续根据剩余时间适当收敛
    timeout_cfg = httpx.Timeout(connect=2.0, read=2.5, write=1.0, pool=1.0)
    async with httpx.AsyncClient(timeout=timeout_cfg, trust_env=False) as client:
        while time.time() < deadline:
            http_attempts += 1
            remaining = max(0.5, deadline - time.time())
            # 动态调整读取超时，但不超过 3s
            client.timeout = httpx.Timeout(connect=2.0, read=min(3.0, remaining), write=1.0, pool=1.0)
            try:
                logger.debug(f"Attempt {http_attempts}: checking {url} (read timeout: {client.timeout.read:.1f}s)")
                resp = await client.get(url)
                if resp.status_code == 200:
                    logger.info(f"Server ready at {url} after {http_attempts} attempts")
                    return True
                else:
                    last_error = f"HTTP {resp.status_code}"
                    logger.debug(f"Server returned status {resp.status_code}")
            except httpx.TimeoutException as e:
                last_error = f"HTTPX timeout: {e}"
                logger.debug(f"Attempt {http_attempts}: httpx timeout")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.debug(f"Attempt {http_attempts}: connection failed - {e}")
            except httpx.HTTPError as e:
                last_error = f"HTTP error: {e}"
                logger.debug(f"Attempt {http_attempts}: HTTP error - {e}")
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.debug(f"Attempt {http_attempts}: unexpected error - {e}")

            await asyncio.sleep(0.5)

    error_msg = f"Server not ready at {url} after {timeout}s ({http_attempts} attempts). Last error: {last_error}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)
