import asyncio
import socket
import time
from urllib.parse import urlparse

import httpx
from utils.logger_helper import logger_helper as logger


async def wait_until_server_ready(url: str, timeout=30):
    """
    优化的服务器就绪等待机制：
    1) 先等待 TCP 端口进入监听状态（智能退避策略）；
    2) 再轮询 /healthz（快速重试策略）；
    3) 更快的检测间隔和更好的错误处理
    """
    deadline = time.time() + float(timeout)
    last_error = None
    
    logger.info(f"🔍 Optimized server readiness check for {url}, timeout: {timeout}s")
    
    # 解析 URL 获取主机和端口（用于 TCP 探测）
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if (parsed.scheme or "http") == "https" else 80)
    
    # 第一阶段：快速端口检测（智能退避策略）
    port_attempts = 0
    while time.time() < deadline:
        port_attempts += 1
        try:
            with socket.create_connection((host, port), timeout=0.5) as s:
                s.close()
                logger.debug(f"⚡ TCP {host}:{port} ready after {port_attempts} attempts")
                break
        except OSError as e:
            last_error = f"TCP connect failed: {e}"
        
        # 智能退避：前几次快速检测，后续放慢
        if port_attempts < 5:
            await asyncio.sleep(0.1)  # 前5次快速检测
        else:
            await asyncio.sleep(0.3)  # 后续正常间隔
    else:
        error_msg = f"Server port not ready at {host}:{port} within {timeout}s"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # 第二阶段：HTTP 健康检查（优化配置）
    http_attempts = 0
    timeout_cfg = httpx.Timeout(connect=1.0, read=2.0, write=1.0, pool=1.0)
    
    async with httpx.AsyncClient(timeout=timeout_cfg) as client:
        while time.time() < deadline:
            http_attempts += 1
            try:
                logger.debug(f"🔍 HTTP check attempt {http_attempts}: {url}")
                resp = await client.get(url)
                if resp.status_code == 200:
                    logger.info(f"✅ Server ready at {url} after {http_attempts} HTTP attempts")
                    return True
                else:
                    last_error = f"HTTP {resp.status_code}"
            except httpx.TimeoutException:
                last_error = "HTTP timeout"
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
            except Exception as e:
                last_error = f"Unexpected error: {e}"
            
            # 智能退避策略
            if http_attempts < 3:
                await asyncio.sleep(0.2)  # 前3次快速重试
            else:
                await asyncio.sleep(0.5)  # 后续正常间隔
    
    error_msg = f"Server not ready at {url} after {timeout}s. Last error: {last_error}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)


async def check_server_port(host: str = "127.0.0.1", port: int = None, timeout: float = 0.5) -> bool:
    """
    快速检查服务器端口是否可用
    
    Args:
        host: 服务器主机地址，默认 127.0.0.1
        port: 端口号
        timeout: 连接超时时间，默认 0.5 秒
        
    Returns:
        bool: 端口可用返回 True，否则返回 False
    """
    if port is None:
        logger.warning("Port not specified for server port check")
        return False
        
    try:
        logger.debug(f"🔍 Checking server port {host}:{port} (timeout: {timeout}s)")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        logger.debug(f"✅ Server port {host}:{port} is available")
        return True
    except asyncio.TimeoutError:
        logger.debug(f"⏰ Server port {host}:{port} check timeout")
        return False
    except ConnectionRefusedError:
        logger.debug(f"❌ Connection refused to {host}:{port}")
        return False
    except Exception as e:
        logger.debug(f"❌ Server port {host}:{port} check failed: {e}")
        return False


def mcp_result_to_lc_tool_message(tool_name, mcp_result):
    from langchain_core.messages import ToolMessage
    lc_tool_message = ToolMessage(
                content=mcp_result[0].text,
                artifact=mcp_result[0].meta,
                tool_call_id=tool_name,
            )

    return lc_tool_message