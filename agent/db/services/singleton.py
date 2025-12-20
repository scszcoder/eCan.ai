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

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        # Each class has its own instance dictionary and lock
        cls._instances = weakref.WeakValueDictionary()
        cls._lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        """
        Create or return existing singleton instance.

        Uses database path, engine, or session as unique identifier
        to support multiple database connections.
        """
        # Use database path as unique identifier for instance
        db_manager = kwargs.get('db_manager')
        db_path = kwargs.get('db_path')
        engine = kwargs.get('engine')
        session = kwargs.get('session')

        # Generate unique key, including class name to ensure instances of different classes don't conflict
        class_name = cls.__name__
        if db_manager:
            key = f"{class_name}_db_manager_{id(db_manager)}"
        elif db_path:
            key = f"{class_name}_db_path_{db_path}"
        elif engine:
            key = f"{class_name}_engine_{id(engine)}"
        elif session:
            key = f"{class_name}_session_{id(session)}"
        else:
            key = f"{class_name}_default"

        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[key] = instance
        return cls._instances[key]
