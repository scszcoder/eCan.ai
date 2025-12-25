#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows Subprocess Patch for Playwright/browser-use

Fixes NotImplementedError when using WindowsSelectorEventLoopPolicy with subprocess operations.
This is needed because:
1. PySide6/Qt requires WindowsSelectorEventLoopPolicy
2. WindowsSelectorEventLoopPolicy doesn't support asyncio.create_subprocess_exec
3. Playwright/browser-use needs to launch Chrome as a subprocess

Solution: Monkey-patch asyncio.create_subprocess_exec to use threading workaround on Windows.
"""

import sys
import asyncio
import subprocess
import threading
import queue
from typing import Optional, Any, Tuple, List, Union

from utils.logger_helper import logger_helper as logger


class _WriteProtocol(asyncio.Protocol, asyncio.streams.FlowControlMixin):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._loop = loop

class ThreadedWriter:
    """Helper to write to a blocking file/pipe in a separate thread."""
    def __init__(self, pipe, loop):
        self._pipe = pipe
        self._loop = loop
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True, name="AsyncProcessWriter")
        self._thread.start()
        
    def _writer_loop(self):
        while not self._stop_event.is_set():
            try:
                try:
                    data = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                if data is None: # Sentinel
                    break
                    
                self._pipe.write(data)
                self._pipe.flush()
                self._queue.task_done()
            except Exception as e:
                # Pipe broken or closed is expected
                break
                
    def write(self, data):
        self._queue.put(data)
        
    def close(self):
        self._stop_event.set()
        try:
            self._queue.put(None)
        except:
            pass
        try:
            self._pipe.close()
        except:
            pass

class ThreadedStreamTransport(asyncio.Transport):
    """
    A fake Transport that uses ThreadedWriter to write to a blocking pipe.
    Implements needed methods for StreamWriter compatibility.
    """
    def __init__(self, pipe, loop):
        super().__init__()
        self._writer = ThreadedWriter(pipe, loop)
        self._loop = loop
        self._closing = False
        self._protocol = None
    
    def write(self, data):
        if self._closing:
            return
        self._writer.write(data)

    def close(self):
        if self._closing:
            return
        self._closing = True
        self._writer.close()
            
    def is_closing(self):
        return self._closing
        
    def abort(self):
        self.close()
        
    def get_extra_info(self, name, default=None):
        return default
    
    def set_protocol(self, protocol):
        self._protocol = protocol
    
    def get_protocol(self):
        return self._protocol
        
    # WriteTransport methods
    def set_write_buffer_limits(self, high=None, low=None):
        pass
        
    def get_write_buffer_size(self):
        return 0
        
    def write_eof(self):
        # Subprocess pipes usually close to send EOF
        self.close()
        
    def can_write_eof(self):
        return True

class AsyncProcessAdapter:
    """
    Mimics asyncio.subprocess.Process but uses threads for I/O and waiting.
    Compatible with WindowsSelectorEventLoop.
    """
    def __init__(self, process: subprocess.Popen, loop: asyncio.AbstractEventLoop):
        self._process = process
        self._loop = loop
        self.pid = process.pid
        self._returncode = None
        
        self.stdin: Optional[asyncio.StreamWriter] = None
        self.stdout: Optional[asyncio.StreamReader] = None
        self.stderr: Optional[asyncio.StreamReader] = None
        
        # Setup streams
        if process.stdin:
            transport = ThreadedStreamTransport(process.stdin, loop)
            protocol = _WriteProtocol(loop)
            transport.set_protocol(protocol)
            self.stdin = asyncio.StreamWriter(transport, protocol, None, loop)
            
        if process.stdout:
            self.stdout = asyncio.StreamReader(limit=asyncio.streams._DEFAULT_LIMIT)
            self._start_reader_thread(process.stdout, self.stdout, "stdout")
            
        if process.stderr:
            self.stderr = asyncio.StreamReader(limit=asyncio.streams._DEFAULT_LIMIT)
            self._start_reader_thread(process.stderr, self.stderr, "stderr")

    @property
    def returncode(self):
        return self._process.poll()

    def _start_reader_thread(self, pipe, stream_reader, name):
        def _read_loop():
            try:
                while True:
                    # Blocking read
                    data = pipe.read(4096)
                    if not data:
                        break
                    # Schedule data feed in event loop
                    self._loop.call_soon_threadsafe(stream_reader.feed_data, data)
            except Exception:
                pass
            finally:
                self._loop.call_soon_threadsafe(stream_reader.feed_eof)
                try:
                    pipe.close()
                except:
                    pass
                
        t = threading.Thread(target=_read_loop, daemon=True, name=f"AsyncProcessReader-{name}-{self.pid}")
        t.start()

    async def wait(self):
        if self.returncode is not None:
            return self.returncode
        
        # Run blocking wait in executor
        await self._loop.run_in_executor(None, self._process.wait)
        return self.returncode

    def send_signal(self, signal):
        self._process.send_signal(signal)

    def terminate(self):
        self._process.terminate()

    def kill(self):
        self._process.kill()

    async def communicate(self, input=None) -> Tuple[Optional[bytes], Optional[bytes]]:
        if input and self.stdin:
            self.stdin.write(input)
            await self.stdin.drain()
            self.stdin.close()
        
        stdout_task = None
        stderr_task = None
        
        if self.stdout:
            stdout_task = asyncio.create_task(self.stdout.read())
        if self.stderr:
            stderr_task = asyncio.create_task(self.stderr.read())
            
        await self.wait()
        
        stdout = await stdout_task if stdout_task else None
        stderr = await stderr_task if stderr_task else None
        
        return (stdout, stderr)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.returncode is None:
            try:
                self.terminate()
            except ProcessLookupError:
                pass
            # Wait for the process to terminate
            try:
                await self.wait()
            except Exception:
                pass


def _sync_subprocess_exec(*args, **kwargs) -> subprocess.Popen:
    """
    Synchronous subprocess execution helper.
    """
    # Remove asyncio-specific kwargs
    stdin = kwargs.pop('stdin', None)
    stdout = kwargs.pop('stdout', None)
    stderr = kwargs.pop('stderr', None)
    limit = kwargs.pop('limit', None)
    
    # Map asyncio PIPE constants to subprocess PIPE
    if stdin == asyncio.subprocess.PIPE:
        stdin = subprocess.PIPE
    if stdout == asyncio.subprocess.PIPE:
        stdout = subprocess.PIPE
    if stderr == asyncio.subprocess.PIPE:
        stderr = subprocess.PIPE
    if stdin == asyncio.subprocess.DEVNULL:
        stdin = subprocess.DEVNULL
    if stdout == asyncio.subprocess.DEVNULL:
        stdout = subprocess.DEVNULL
    if stderr == asyncio.subprocess.DEVNULL:
        stderr = subprocess.DEVNULL

    # Add Windows-specific flags to hide console window if not present
    if sys.platform == 'win32':
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
    process = subprocess.Popen(
        args[0] if len(args) == 1 else args,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        **kwargs
    )
    return process


async def _threaded_create_subprocess_exec(program, *args, **kwargs):
    """
    Replacement for asyncio.create_subprocess_exec
    """
    loop = asyncio.get_event_loop()
    
    # Run Popen in executor to avoid blocking
    popen_args = [program] + list(args)
    
    try:
        process = await loop.run_in_executor(
            None, 
            lambda: _sync_subprocess_exec(*popen_args, **kwargs)
        )
    except Exception as e:
        logger.error(f"[SubprocessPatch] Failed to spawn process: {e}")
        raise
    
    return AsyncProcessAdapter(process, loop)


async def _threaded_create_subprocess_shell(cmd, **kwargs):
    loop = asyncio.get_event_loop()
    try:
        process = await loop.run_in_executor(None, lambda: _sync_subprocess_exec(cmd, shell=True, **kwargs))
    except Exception as e:
        logger.error(f"[SubprocessPatch] Failed to spawn shell process: {e}")
        raise
    return AsyncProcessAdapter(process, loop)


def patch_asyncio_subprocess_for_windows():
    """
    Patch asyncio.create_subprocess_exec on Windows when using SelectorEventLoop.
    """
    if sys.platform != 'win32':
        return
    
    try:
        # Check if already patched to avoid recursion
        if getattr(asyncio, '_subprocess_patched', False):
            logger.debug("[SubprocessPatch] Already patched, skipping")
            return

        # Relaxed check: We apply the patch regardless of the current policy class,
        # because the patch logic itself tries the original method first and only
        # falls back if NotImplementedError is raised. This safeguards against
        # cases where the policy is wrapped or detection fails.
        policy = asyncio.get_event_loop_policy()
        logger.debug(f"[SubprocessPatch] Current policy: {type(policy).__name__}")
        
        logger.info("[SubprocessPatch] Applying Windows subprocess patch")
        
        original_create_subprocess_exec = asyncio.create_subprocess_exec
        original_create_subprocess_shell = asyncio.create_subprocess_shell
        
        async def patched_create_subprocess_exec(program, *args, **kwargs):
            try:
                return await original_create_subprocess_exec(program, *args, **kwargs)
            except NotImplementedError:
                logger.debug(f"[SubprocessPatch] Intercepting subprocess launch for {program}")
                return await _threaded_create_subprocess_exec(program, *args, **kwargs)

        async def patched_create_subprocess_shell(cmd, **kwargs):
            try:
                return await original_create_subprocess_shell(cmd, **kwargs)
            except NotImplementedError:
                logger.debug(f"[SubprocessPatch] Intercepting subprocess shell launch for {cmd}")
                return await _threaded_create_subprocess_shell(cmd, **kwargs)
        
        asyncio.create_subprocess_exec = patched_create_subprocess_exec
        asyncio.create_subprocess_shell = patched_create_subprocess_shell
        asyncio._subprocess_patched = True
        logger.info("[SubprocessPatch] Patch applied successfully")
        
    except Exception as e:
        logger.warning(f"[SubprocessPatch] Failed to apply patch: {e}")
