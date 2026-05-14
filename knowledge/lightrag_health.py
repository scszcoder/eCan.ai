"""
Worker Pool Health Monitor

This module provides comprehensive protection against worker pool exhaustion and hangs:
1. Circuit breaker pattern for failing services
2. Worker pool health monitoring
3. HTTP client timeout protection
4. Embedding batch size enforcement

Usage:
    from knowledge.lightrag_health import (
        get_health_monitor,
        get_pool_status,
        CircuitBreaker,
        EmbeddingBatchFixer,
        with_timeout,
    )
"""

import asyncio
import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Any, Dict, List, Optional, Tuple
from enum import Enum
from functools import wraps
from utils.logger_helper import logger_helper as logger

# Try to import provider validator
try:
    from knowledge.provider_limits_validator import get_validator
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False
    get_validator = None


# =============================================================================
# Circuit Breaker
# =============================================================================

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, requests blocked
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker
    
    Aggressive settings to prevent 38-minute hangs observed in bug.log.
    Recovery timeout should be much shorter than LightRAG's internal timeouts.
    """
    failure_threshold: int = 3          # Open circuit after 3 consecutive failures
    timeout_threshold: int = 2           # Open circuit after 2 consecutive timeouts
    recovery_timeout: float = 10.0       # Try recovery after 10s (much shorter than 300s timeout)
    half_open_max_requests: int = 2       # Allow 2 test requests in half-open state
    success_threshold: int = 1           # Close circuit after 1 success
    max_request_duration: float = 60.0   # Force timeout if request takes > 60s


class CircuitBreaker:
    """Circuit breaker implementation for worker pools."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._timeout_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_requests = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        return self._state
    
    @property
    def is_available(self) -> bool:
        return self._state != CircuitState.OPEN
    
    async def record_success(self):
        """Record a successful request"""
        async with self._lock:
            self._failure_count = 0
            self._timeout_count = 0
            self._success_count += 1
            
            if self._state == CircuitState.HALF_OPEN:
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    logger.info(f"[CircuitBreaker] {self.name}: Circuit CLOSED (recovered)")
    
    async def record_failure(self, is_timeout: bool = False):
        """Record a failed request"""
        async with self._lock:
            self._last_failure_time = time.time()
            
            if is_timeout:
                self._timeout_count += 1
                if self._timeout_count >= self.config.timeout_threshold:
                    self._open_circuit()
                    return
            else:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._open_circuit()
                    return
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
                self._half_open_requests = 0
                logger.warning(f"[CircuitBreaker] {self.name}: Circuit REOPENED")
    
    def _open_circuit(self):
        """Open the circuit (called with lock held)"""
        if self._state != CircuitState.OPEN:
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._half_open_requests = 0
            logger.warning(
                f"[CircuitBreaker] {self.name}: Circuit OPENED "
                f"(failures={self._failure_count}, timeouts={self._timeout_count})"
            )
    
    async def can_execute(self) -> bool:
        """Check if a request can be executed"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.config.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                    logger.info(f"[CircuitBreaker] {self.name}: Circuit HALF_OPEN")
                    return True
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.config.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                return False
            
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        async with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "timeout_count": self._timeout_count,
            }


# =============================================================================
# Worker Pool Health Monitor
# =============================================================================

@dataclass
class WorkerStats:
    """Statistics for a single worker"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    total_response_time: float = 0.0
    last_request_time: float = 0.0
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    is_busy: bool = False
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_response_time(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests


class WorkerPoolHealthMonitor:
    """
    Monitors worker pool health and provides circuit breaker functionality.
    
    Singleton pattern for global access.
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._workers: Dict[str, WorkerStats] = {}
        self._worker_lock = asyncio.Lock()
        
        # Circuit breakers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            "embedding": CircuitBreaker("embedding"),
            "llm": CircuitBreaker("llm"),
            "rerank": CircuitBreaker("rerank"),
        }
        
        # Global statistics
        self._global_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "timeout_requests": 0,
            "rejected_requests": 0,
        }
        
        # Recent events
        self._recent_events: deque = deque(maxlen=100)
        
        logger.info("[WorkerPoolHealthMonitor] Initialized")
    
    async def register_worker(self, worker_id: str):
        async with self._worker_lock:
            if worker_id not in self._workers:
                self._workers[worker_id] = WorkerStats()
    
    async def record_request_start(self, worker_id: str):
        async with self._worker_lock:
            if worker_id not in self._workers:
                self._workers[worker_id] = WorkerStats()
            worker = self._workers[worker_id]
            worker.total_requests += 1
            worker.last_request_time = time.time()
            worker.is_busy = True
            self._global_stats["total_requests"] += 1
    
    async def record_request_success(self, worker_id: str, response_time: float):
        async with self._worker_lock:
            if worker_id not in self._workers:
                return
            worker = self._workers[worker_id]
            worker.successful_requests += 1
            worker.total_response_time += response_time
            worker.last_success_time = time.time()
            worker.is_busy = False
            self._global_stats["successful_requests"] += 1
    
    async def record_request_failure(self, worker_id: str, error_type: str = "error"):
        is_timeout = "timeout" in error_type.lower()
        
        async with self._worker_lock:
            if worker_id not in self._workers:
                return
            worker = self._workers[worker_id]
            worker.failed_requests += 1
            worker.last_failure_time = time.time()
            worker.is_busy = False
            
            if is_timeout:
                worker.timeout_requests += 1
                self._global_stats["timeout_requests"] += 1
            else:
                self._global_stats["failed_requests"] += 1
        
        # Record in circuit breaker
        circuit = self._circuit_breakers.get(
            "embedding" if "embedding" in worker_id.lower() else "llm"
        )
        if circuit:
            await circuit.record_failure(is_timeout)
    
    async def can_execute_request(self, service: str = "llm") -> bool:
        circuit = self._circuit_breakers.get(service)
        if not circuit:
            return True
        
        can_exec = await circuit.can_execute()
        if not can_exec:
            async with self._worker_lock:
                self._global_stats["rejected_requests"] += 1
        return can_exec
    
    async def get_pool_status(self) -> Dict[str, Any]:
        async with self._worker_lock:
            worker_stats = {
                wid: {
                    "total_requests": w.total_requests,
                    "successful": w.successful_requests,
                    "failed": w.failed_requests,
                    "timeouts": w.timeout_requests,
                    "success_rate": f"{w.success_rate:.2%}",
                    "is_busy": w.is_busy,
                }
                for wid, w in self._workers.items()
            }
        
        circuit_status = {
            name: await cb.get_status()
            for name, cb in self._circuit_breakers.items()
        }
        
        return {
            "global_stats": self._global_stats.copy(),
            "worker_count": len(self._workers),
            "busy_workers": sum(1 for w in self._workers.values() if w.is_busy),
            "workers": worker_stats,
            "circuit_breakers": circuit_status,
            "health_score": self._calculate_health_score(),
            "recommendation": self._get_recommendation(),
        }
    
    def _calculate_health_score(self) -> float:
        stats = self._global_stats
        total = stats["total_requests"]
        if total == 0:
            return 100.0
        
        success_rate = stats["successful_requests"] / total
        score = success_rate * 70
        
        timeout_rate = stats["timeout_requests"] / total
        score -= timeout_rate * 20
        
        open_circuits = sum(1 for cb in self._circuit_breakers.values() 
                           if cb.state == CircuitState.OPEN)
        score -= open_circuits * 10
        
        return max(0, min(100, score))
    
    def _get_recommendation(self) -> str:
        health_score = self._calculate_health_score()
        
        if health_score >= 90:
            return "Pool is healthy"
        elif health_score >= 70:
            return "Pool is degraded"
        elif health_score >= 50:
            return "Pool is struggling - consider restart"
        else:
            return "Pool is unhealthy - restart recommended"
    
    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        return list(self._recent_events)[-limit:]


# Global singleton
_health_monitor: Optional[WorkerPoolHealthMonitor] = None


def get_health_monitor() -> WorkerPoolHealthMonitor:
    """Get the global health monitor instance"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = WorkerPoolHealthMonitor()
    return _health_monitor


async def get_pool_status() -> Dict[str, Any]:
    """Get pool status"""
    return await get_health_monitor().get_pool_status()


# =============================================================================
# Timeout Protection
# =============================================================================

class TimeoutError(Exception):
    """Custom timeout error"""
    pass


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class RequestStuckError(Exception):
    """Raised when a request has been running too long"""
    pass


# Maximum request duration before force-fail (prevent 38-min hangs)
MAX_REQUEST_DURATION = 60.0  # seconds


def with_timeout(
    timeout: float = 60.0,
    service_name: str = "default",
):
    """
    Decorator to add timeout and circuit breaker protection to async functions.
    
    Usage:
        @with_timeout(timeout=30.0, service_name="embedding")
        async def my_embedding_func(texts):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            worker_id = f"{service_name}_{id(asyncio.current_task())}"
            
            # Check circuit breaker
            monitor = get_health_monitor()
            if not await monitor.can_execute_request(service_name):
                elapsed = time.time() - start_time
                logger.warning(
                    f"[Timeout] Circuit breaker OPEN for {service_name}, "
                    f"rejected after {elapsed:.2f}s"
                )
                raise CircuitOpenError(f"Circuit breaker is open for {service_name}")
            
            await monitor.record_request_start(worker_id)
            
            async def _check_duration():
                """Watchdog to detect stuck requests"""
                while True:
                    await asyncio.sleep(5)  # Check every 5 seconds
                    elapsed = time.time() - start_time
                    if elapsed > MAX_REQUEST_DURATION:
                        logger.error(
                            f"[Timeout] Request {worker_id} stuck for {elapsed:.1f}s, "
                            f"exceeds max duration {MAX_REQUEST_DURATION}s"
                        )
                        raise RequestStuckError(
                            f"Request stuck for {elapsed:.1f}s (max: {MAX_REQUEST_DURATION}s)"
                        )
            
            try:
                # Start duration watchdog
                watchdog = asyncio.create_task(_check_duration())
                
                try:
                    # Execute with timeout
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout
                    )
                finally:
                    # Cancel watchdog
                    watchdog.cancel()
                    try:
                        await watchdog
                    except asyncio.CancelledError:
                        pass
                
                elapsed = time.time() - start_time
                await monitor.record_request_success(worker_id, elapsed)
                
                if elapsed > 30:
                    logger.warning(
                        f"[Timeout] {service_name} slow: {elapsed:.1f}s"
                    )
                return result
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                await monitor.record_request_failure(worker_id, "timeout")
                logger.warning(
                    f"[Timeout] ⏱️ {service_name} TIMEOUT after {elapsed:.2f}s"
                )
                raise TimeoutError(
                    f"{service_name} timed out after {timeout}s"
                ) from None
                
            except RequestStuckError:
                await monitor.record_request_failure(worker_id, "stuck")
                raise
                
            except CircuitOpenError:
                raise
                
            except Exception as e:
                elapsed = time.time() - start_time
                await monitor.record_request_failure(worker_id, str(type(e).__name__))
                raise
        
        return wrapper
    return decorator


# Default timeout configuration
DEFAULT_TIMEOUT_CONFIG = {
    "embedding": 60.0,
    "llm": 120.0,
    "rerank": 30.0,
    "default": 60.0,
}


# =============================================================================
# Embedding Batch Fixer
# =============================================================================

class EmbeddingBatchFixer:
    """
    Handles embedding batch splitting to respect API limits.
    
    Many embedding APIs have limits on batch size (e.g., 10 for some providers).
    This class automatically splits large batches into smaller chunks.
    """
    
    # Default limits by provider type
    DEFAULT_LIMITS = {
        "jina": 32,
        "openai": 2048,
        "azure": 64,
        "cohere": 96,
        "alibaba": 10,
        "qwen": 10,
        "dashscope": 10,
        "ollama": 256,
        "ryoais": 256,
        "default": 16,
    }
    
    def __init__(self, provider_name: str = None, max_batch_size: int = None):
        self.provider_name = (provider_name or "default").lower()
        self._max_batch_size = max_batch_size
        self._validator = get_validator() if VALIDATOR_AVAILABLE else None
    
    @property
    def max_batch_size(self) -> int:
        """Get the effective max batch size for this provider"""
        if self._max_batch_size is not None:
            return self._max_batch_size
        
        if self._validator:
            limits = self._validator.get_provider_limits(self.provider_name)
            api_max = limits.get('max_batch_size')
            if api_max is not None:
                return api_max
        
        for pattern, limit in self.DEFAULT_LIMITS.items():
            if pattern in self.provider_name:
                return limit
        
        return self.DEFAULT_LIMITS["default"]
    
    def split_batch(self, items: List[Any]) -> List[List[Any]]:
        """
        Split a batch of items into smaller batches that respect the size limit.
        """
        if not items:
            return []
        
        max_size = self.max_batch_size
        
        if len(items) <= max_size:
            return [items]
        
        batches = []
        for i in range(0, len(items), max_size):
            batch = items[i:i + max_size]
            batches.append(batch)
        
        logger.info(
            f"[EmbeddingBatchFix] Split {len(items)} items into "
            f"{len(batches)} batches (max {max_size} each)"
        )
        
        return batches
    
    def validate_batch_size(self, batch_size: int) -> Tuple[bool, int, str]:
        """Validate a batch size"""
        max_size = self.max_batch_size
        
        if batch_size > max_size:
            return (
                False,
                max_size,
                f"Batch size {batch_size} exceeds limit {max_size}"
            )
        
        return (True, batch_size, "OK")


# Global cache
_fixer_cache: dict = {}


def get_fixer_for_provider(provider_name: str) -> EmbeddingBatchFixer:
    """Get a cached batch fixer for a provider"""
    if provider_name not in _fixer_cache:
        _fixer_cache[provider_name] = EmbeddingBatchFixer(provider_name)
    return _fixer_cache[provider_name]


def fix_embedding_batches(
    texts: List[str],
    provider_name: str = None,
) -> List[List[str]]:
    """Convenience function to split embedding texts into valid batches."""
    fixer = get_fixer_for_provider(provider_name or "default")
    return fixer.split_batch(texts)


# =============================================================================
# Health Check Router (for FastAPI integration)
# =============================================================================

def create_health_router():
    """Create FastAPI router for health check endpoints"""
    try:
        from fastapi import APIRouter
    except ImportError:
        logger.warning("[HealthRouter] FastAPI not available")
        return None
    
    router = APIRouter(prefix="/health", tags=["health"])
    
    @router.get("/status")
    async def health_status():
        """Get comprehensive health status"""
        monitor = get_health_monitor()
        try:
            status = await monitor.get_pool_status()
            return {
                "status": "healthy" if status["health_score"] >= 70 else "degraded",
                "health_score": status["health_score"],
                "worker_count": status["worker_count"],
                "busy_workers": status["busy_workers"],
                "circuit_breakers": {
                    name: cb["state"]
                    for name, cb in status["circuit_breakers"].items()
                },
                "recommendation": status["recommendation"],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    @router.get("/workers")
    async def worker_details():
        """Get detailed worker information"""
        monitor = get_health_monitor()
        try:
            status = await monitor.get_pool_status()
            return {"workers": status["workers"]}
        except Exception as e:
            return {"workers": {}, "error": str(e)}
    
    @router.get("/circuits")
    async def circuit_breaker_status():
        """Get circuit breaker status"""
        monitor = get_health_monitor()
        try:
            status = await monitor.get_pool_status()
            return {"circuits": status["circuit_breakers"]}
        except Exception as e:
            return {"circuits": {}, "error": str(e)}
    
    return router
