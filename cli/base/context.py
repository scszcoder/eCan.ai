#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Context - Provides runtime context for all CLI commands.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class CLIContext:
    """
    Global CLI context that persists across command execution.

    Provides:
    - Project root detection
    - Session management (auth)
    - Database service access
    - Configuration access
    - Environment variables
    """

    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)
    _session: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _session_loaded: bool = field(default=False, init=False)
    _db_service: Optional[Any] = field(default=None, init=False, repr=False)
    env: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.env = dict(os.environ)

    @property
    def session(self) -> Optional[Dict[str, Any]]:
        """Load and return session data."""
        if not self._session_loaded:
            self._session = self._load_session()
            self._session_loaded = True
        return self._session

    @property
    def is_authenticated(self) -> bool:
        """Check if user is logged in."""
        return bool(self.session and self.session.get('username'))

    @property
    def username(self) -> Optional[str]:
        """Get current username.

        ``ECAN_CLI_USER`` (set by a trusted caller — e.g. the app's Fast
        Deploy handler, which runs the CLI as a subprocess scoped to the
        CURRENTLY logged-in user) takes precedence over any
        ``.ecan_session.json``: a stale session file from an earlier
        ``ecan auth login`` must not silently redirect identity — and the
        per-user DB path — to a different user (deep-trace finding
        2026-08-27: deploys landed in an old login's DB). This does NOT
        grant auth (``is_authenticated`` still requires a real session).
        """
        env_user = os.environ.get('ECAN_CLI_USER')
        if env_user:
            return env_user
        if self.session:
            return self.session.get('username')
        return None

    def _load_session(self) -> Optional[Dict[str, Any]]:
        """Load session from file."""
        session_file = self.project_root / ".ecan_session.json"
        if session_file.exists():
            try:
                with open(session_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def save_session(self, data: Dict[str, Any]):
        """Save session to file (atomically, with 0600 permissions).

        The session may carry an auth token, so: write to a temp file then
        ``os.replace`` (an interrupted write can't truncate the real file),
        and restrict the file to the owner (best-effort; a no-op on
        filesystems that don't support POSIX modes).
        """
        session_file = self.project_root / ".ecan_session.json"
        tmp = session_file.with_suffix(".json.tmp")
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, session_file)
        try:
            os.chmod(session_file, 0o600)
        except OSError:
            pass
        self._session = data
        self._session_loaded = True

    def clear_session(self):
        """Clear session."""
        session_file = self.project_root / ".ecan_session.json"
        if session_file.exists():
            session_file.unlink()
        self._session = None
        self._session_loaded = True

    def require_auth(self, message: str = None):
        """
        Require authentication. Exit with error if not authenticated.

        Args:
            message: Custom error message

        Raises:
            SystemExit: If not authenticated
        """
        if not self.is_authenticated:
            msg = message or "Please login first: ecan auth login"
            print(f"\033[93m{msg}\033[0m", file=sys.stderr)
            sys.exit(1)
        return self.session

    @property
    def db(self):
        """Get database service (lazy initialization)."""
        if self._db_service is None:
            self._db_service = self._get_db_service()
        return self._db_service

    def _get_db_service(self):
        """
        Initialize and return the database service wrapper.

        Returns a wrapper that provides a unified interface to all database services
        (agent_service, skill_service, task_service, vehicle_service, etc.)
        """
        try:
            from agent.db.ec_db_mgr import ECDBMgr
            from agent.db.services.db_vehicle_service import DBVehicleService

            # Open the SAME per-user database the app uses
            # ({appdata}/{log_user}/ecan_base.db) instead of a stray ecan_base.db
            # in the current working directory. Without this, CLI writes land in a
            # different (often empty) DB than the running app reads.
            db_dir = None
            try:
                if self.username:
                    from utils.user_path_helper import get_user_data_dir
                    db_dir = get_user_data_dir(user_email=self.username)
            except Exception:
                db_dir = None

            ec_db = ECDBMgr(db_dir)

            # Create wrapper with all services
            class DBServices:
                def __init__(self, ec_db_mgr):
                    self.agent_service = ec_db_mgr.agent_service
                    self.skill_service = ec_db_mgr.skill_service
                    self.task_service = ec_db_mgr.task_service
                    self.org_service = ec_db_mgr.org_service
                    self.avatar_service = getattr(ec_db_mgr, 'avatar_service', None)
                    self._vehicle_service = None

                @property
                def vehicle_service(self):
                    if self._vehicle_service is None:
                        self._vehicle_service = DBVehicleService(engine=self.agent_service.engine)
                    return self._vehicle_service

            return DBServices(ec_db)
        except ImportError as e:
            # Raise (don't sys.exit): SystemExit is a BaseException and would
            # escape callers' `except Exception` (e.g. `status`), aborting the
            # whole command instead of letting them report a friendly error.
            raise RuntimeError(f"Error importing database manager: {e}") from e

    @property
    def config(self) -> Dict[str, Any]:
        """Load and return configuration."""
        config_file = self.project_root / ".env.web"
        config = {}

        if config_file.exists():
            for line in config_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()

        for key in ['ECAN_MODE', 'ECAN_WS_HOST', 'ECAN_WS_PORT', 'ECAN_LOG_LEVEL']:
            if key in os.environ:
                config[key] = os.environ[key]

        return config

    def get_version(self) -> str:
        """Get application version."""
        version_file = self.project_root / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        return "unknown"


_global_context: Optional[CLIContext] = None


def get_context() -> CLIContext:
    """Get or create global CLI context."""
    global _global_context
    if _global_context is None:
        _global_context = CLIContext()
    return _global_context


def reset_context():
    """Reset global context (for testing)."""
    global _global_context
    _global_context = None
