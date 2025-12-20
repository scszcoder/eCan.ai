# -*- coding: utf-8 -*-
"""
Thread-safe port allocator for eCan.ai agent system
Solves the concurrent port allocation conflict during parallel agent initialization
"""

import threading
import socket
from typing import List, Set
from utils.logger_helper import logger_helper as logger


class ThreadSafePortAllocator:
    """
    Thread-safe port allocator that prevents multiple agents from getting the same port
    during parallel initialization.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._allocated_ports: Set[int] = set()
        
    def get_free_ports(self, n: int, port_range: List[int], used_ports: List[int] = None) -> List[int]:
        """
        Thread-safely allocate n free ports from the given range.
        
        Args:
            n: Number of ports needed
            port_range: [start_port, end_port] range
            used_ports: List of already used ports (optional)
            
        Returns:
            List of allocated port numbers
            
        Raises:
            RuntimeError: If not enough free ports available
        """
        if used_ports is None:
            used_ports = []
            
        with self._lock:
            # Clean up: remove used ports from allocated set (they're already in use)
            # This prevents double-counting ports that were allocated and are now in use
            if used_ports:
                used_set = set(used_ports)
                removed = self._allocated_ports & used_set
                if removed:
                    self._allocated_ports -= used_set
                    logger.debug(f"[PortAllocator] 🧹 Cleaned up {len(removed)} ports from allocated (now in use): {sorted(removed)}")
            
            # Get all ports in range
            all_ports = list(range(port_range[0], port_range[1] + 1))
            
            # Filter out used ports and already allocated ports
            unavailable_ports = set(used_ports) | self._allocated_ports
            free_ports = [port for port in all_ports if port not in unavailable_ports]
            
            # Log detailed port status
            # logger.info(f"[PortAllocator] 🔍 Port allocation request: need {n} ports")
            # logger.info(f"[PortAllocator]    📊 Port range: {port_range[0]}-{port_range[1]} (total: {len(all_ports)})")
            # logger.info(f"[PortAllocator]    🔴 Used by agents: {sorted(used_ports) if used_ports else 'none'}")
            # logger.info(f"[PortAllocator]    🟡 Allocated (pending): {sorted(self._allocated_ports) if self._allocated_ports else 'none'}")
            # logger.info(f"[PortAllocator]    🟢 Available: {len(free_ports)} ports {sorted(free_ports[:10])}{'...' if len(free_ports) > 10 else ''}")
            
            # Check if we have enough free ports
            if len(free_ports) < n:
                available_count = len(free_ports)
                logger.error(f"[PortAllocator] ❌ Insufficient ports: only {available_count} available, but {n} requested")
                logger.error(f"[PortAllocator]    Port range: {port_range}, Used: {used_ports}, Allocated: {list(self._allocated_ports)}")
                raise RuntimeError(f"Only {available_count} free ports available, but {n} requested.")
            
            # Allocate the first n free ports
            allocated_ports = free_ports[:n]
            
            # Mark these ports as allocated
            self._allocated_ports.update(allocated_ports)
            
            # logger.info(f"[PortAllocator] ✅ Allocated {n} ports: {allocated_ports}")
            # logger.info(f"[PortAllocator]    Total allocated now: {len(self._allocated_ports)} ports {sorted(self._allocated_ports)}")
            return allocated_ports
    
    def release_ports(self, ports: List[int]):
        """
        Release previously allocated ports back to the free pool.
        
        Args:
            ports: List of port numbers to release
        """
        with self._lock:
            released = []
            not_found = []
            for port in ports:
                if port in self._allocated_ports:
                    self._allocated_ports.discard(port)
                    released.append(port)
                else:
                    not_found.append(port)
            
            if released:
                logger.info(f"[PortAllocator] 🔓 Released {len(released)} ports: {released}")
            if not_found:
                logger.warning(f"[PortAllocator] ⚠️ Ports not in allocated list: {not_found}")
            logger.info(f"[PortAllocator]    Remaining allocated: {len(self._allocated_ports)} ports {sorted(self._allocated_ports) if self._allocated_ports else 'none'}")
    
    def release_port(self, port: int):
        """
        Release a single port back to the free pool.
        
        Args:
            port: Port number to release
        """
        self.release_ports([port])
    
    def get_allocated_ports(self) -> List[int]:
        """
        Get list of currently allocated ports.
        
        Returns:
            List of allocated port numbers
        """
        with self._lock:
            return list(self._allocated_ports)
    
    def clear_all_allocations(self):
        """
        Clear all port allocations. Use with caution.
        """
        with self._lock:
            count = len(self._allocated_ports)
            self._allocated_ports.clear()
            logger.info(f"[PortAllocator] Cleared all {count} port allocations")
    
    def is_port_available(self, port: int, used_ports: List[int] = None) -> bool:
        """
        Check if a specific port is available for allocation.
        
        Args:
            port: Port number to check
            used_ports: List of already used ports (optional)
            
        Returns:
            True if port is available, False otherwise
        """
        if used_ports is None:
            used_ports = []
            
        with self._lock:
            return port not in used_ports and port not in self._allocated_ports


# Global instance for the application
_global_port_allocator = ThreadSafePortAllocator()


def get_port_allocator() -> ThreadSafePortAllocator:
    """
    Get the global port allocator instance.
    
    Returns:
        ThreadSafePortAllocator instance
    """
    return _global_port_allocator


def allocate_free_ports(n: int, port_range: List[int], used_ports: List[int] = None) -> List[int]:
    """
    Convenience function to allocate free ports using the global allocator.
    
    Args:
        n: Number of ports needed
        port_range: [start_port, end_port] range
        used_ports: List of already used ports (optional)
        
    Returns:
        List of allocated port numbers
    """
    return _global_port_allocator.get_free_ports(n, port_range, used_ports)


def release_allocated_ports(ports: List[int]):
    """
    Convenience function to release ports using the global allocator.
    
    Args:
        ports: List of port numbers to release
    """
    _global_port_allocator.release_ports(ports)


# Test function
def test_port_allocator():
    """
    Test the port allocator functionality.
    """
    allocator = ThreadSafePortAllocator()
    
    # Test basic allocation
    ports1 = allocator.get_free_ports(2, [3600, 3610], [])
    print(f"Allocated ports: {ports1}")
    
    # Test concurrent allocation
    ports2 = allocator.get_free_ports(2, [3600, 3610], [])
    print(f"Allocated more ports: {ports2}")
    
    # Test with used ports
    ports3 = allocator.get_free_ports(1, [3600, 3610], [3605])
    print(f"Allocated avoiding used port: {ports3}")
    
    # Release ports
    allocator.release_ports(ports1)
    print(f"Released ports: {ports1}")
    
    # Allocate again
    ports4 = allocator.get_free_ports(2, [3600, 3610], [])
    print(f"Re-allocated ports: {ports4}")


if __name__ == "__main__":
    test_port_allocator()
