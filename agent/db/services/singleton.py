"""
Singleton pattern implementation for database services.

This module provides thread-safe singleton metaclass for database services
to ensure single instance per database connection.
"""

import threading
import weakref


class SingletonMeta(type):
    """
    Thread-safe singleton metaclass.
    
    Provides singleton implementation with weak references to allow
    garbage collection when instances are no longer needed.
    """
    _instances = weakref.WeakValueDictionary()
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        """
        Create or return existing singleton instance.
        
        Uses database path, engine, or session as unique identifier
        to support multiple database connections.
        """
        # 使用数据库路径作为实例的唯一标识
        db_manager = kwargs.get('db_manager')
        db_path = kwargs.get('db_path')
        engine = kwargs.get('engine')
        session = kwargs.get('session')
        
        # 生成唯一键
        if db_manager:
            key = f"db_manager_{id(db_manager)}"
        elif db_path:
            key = f"db_path_{db_path}"
        elif engine:
            key = f"engine_{id(engine)}"
        elif session:
            key = f"session_{id(session)}"
        else:
            key = "default"
            
        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[key] = instance
        return cls._instances[key]
