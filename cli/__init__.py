"""
eCan.ai CLI Package

Command categories:
    - QUERY: List, get, search, show, status
    - CONTROL: Start, stop, login, logout, run
    - OPERATION: Add, create, update, remove, delete
"""

from .main import cli

__all__ = ['cli']
