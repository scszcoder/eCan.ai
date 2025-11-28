import anyio
import anyio.abc
from typing import Optional
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from utils.logger_helper import logger_helper as logger
from agent.ec_skills.system_proxy import create_mcp_httpx_client


class Streamable_HTTP_Manager:
    _instance: Optional["Streamable_HTTP_Manager"] = None

    def __init__(self, url: str) -> None:
        self._url = url
        self._lock = anyio.Lock()
        self._tg: Optional[anyio.abc.TaskGroup] = None
        self._session: Optional[ClientSession] = None
        self._ready: Optional[anyio.Event] = None
    # -------- singleton accessor ------------------------------------
    @classmethod
    def get(cls, url: str) -> "Streamable_HTTP_Manager":
        if cls._instance is None:
            cls._instance = cls(url)
        return cls._instance

    # -------- public API  -------------------------------------------
    async def session(self) -> ClientSession:
        async with self._lock:
            if self._session is None:
                await self._open()           # first time
            # Ensure ready
            if self._ready is not None:
                await self._ready.wait()
        return self._session                 # type: ignore[arg-type]

    async def close(self) -> None:
        async with self._lock:
            if self._tg is not None:
                # Cancel background tasks first
                self._tg.cancel_scope.cancel()

                # Store reference to avoid race conditions
                tg_to_close = self._tg
                self._tg = None
                self._session = None
                self._ready = None

                # Close the task group safely
                try:
                    # Wait for tasks to be cancelled
                    await anyio.sleep(0.1)  # Give tasks time to respond to cancellation
                    await tg_to_close.__aexit__(None, None, None)
                except (RuntimeError, anyio.get_cancelled_exc_class()) as e:
                    # Handle task group exit errors gracefully
                    logger.debug(f"StreamableHTTPManager: Task group exit error (expected during shutdown): {e}")
                except Exception as e:
                    logger.warning(f"StreamableHTTPManager: Unexpected error during close: {e}")
                    # Don't re-raise to avoid breaking the shutdown process

    # -------- internal ----------------------------------------------
    async def _open(self) -> None:
        logger.debug("Streamable_HTTP_Manager: opening persistent session")
        self._tg = anyio.create_task_group()
        await self._tg.__aenter__()
        self._ready = anyio.Event()

        async def _runner() -> None:
            logger.debug(f"Streamable HTTP client opening: {self._url}")
            try:
                async with streamablehttp_client(self._url, terminate_on_close=False, httpx_client_factory=create_mcp_httpx_client) as streams:
                    async with ClientSession(streams[0], streams[1]) as sess:
                        # Only timeout the initialization phase, not the entire session
                        with anyio.fail_after(30):  # 30 second timeout for initialization
                            logger.debug("Streamable HTTP client session initializing")
                            await sess.initialize()

                        logger.debug("Streamable HTTP client session created")
                        self._session = sess
                        self._ready.set()
                        try:
                            await sess.send_ping()
                        except Exception:
                            pass
                        logger.info("Streamable HTTP client ready")
                        await anyio.sleep_forever()   # keep everything alive (no timeout here!)
            except TimeoutError:
                logger.error("Streamable HTTP client initialization timed out after 30s")
                self._ready.set()  # Unblock waiters on timeout
            except Exception as e:
                logger.error(f"Streamable HTTP client error: {e}")
                self._ready.set()  # Unblock waiters even on error
                raise

        self._tg.start_soon(_runner)
