"""
A single place to hold the stream tables so they survive autoreload.
"""

from typing import Dict
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

REQ_READERS: Dict[str, MemoryObjectReceiveStream] = {}   # client → server
REQ_WRITERS: Dict[str, MemoryObjectSendStream]   = {}
RSP_READERS: Dict[str, MemoryObjectReceiveStream] = {}   # server → client
RSP_WRITERS: Dict[str, MemoryObjectSendStream]   = {}