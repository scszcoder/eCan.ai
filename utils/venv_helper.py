#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Virtual environment helper utilities.

Provides unified helpers for detecting, creating and managing virtual
environments.
"""

import os
import sys
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Tuple, List, Callable, Dict
from enum import Enum
from utils.logger_helper import logger_helper as logger
from utils.subprocess_helper import run_no_window


class VenvHelper:
    """Virtual environment helper class.

    Provides unified operations for working with Python virtual environments.
    """
    
    @staticmethod
    def is_packaged_environment() -> bool:
        """
        Detect whether we are running in a PyInstaller packaged environment.

        Returns:
            bool: True if running in a packaged environment, False if in a
            normal development environment.
        """
        return getattr(sys, 'frozen', False)
    
    @staticmethod
    def is_in_virtualenv() -> bool:
        """
        Detect whether the current process is running inside a virtual
        environment.

        Supports detecting:
        - venv (Python 3.3+)
        - virtualenv
        - conda

        Returns:
            bool: True if running inside a virtual environment, otherwise
            False.
        """
        # Method 1: check sys.real_prefix (virtualenv)
        if hasattr(sys, 'real_prefix'):
            return True
        
        # Method 2: check sys.base_prefix (venv)
        if hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
            return True
        
        # Method 3: check VIRTUAL_ENV environment variable
        if os.environ.get('VIRTUAL_ENV'):
            return True
        
        # Method 4: check CONDA_DEFAULT_ENV environment variable
        if os.environ.get('CONDA_DEFAULT_ENV'):
            return True
        
        return False
    
    @staticmethod
    def get_virtualenv_type() -> Optional[str]:
        """
        Get the type of the current virtual environment.

        Returns:
            Optional[str]: one of 'venv', 'virtualenv', 'conda', or None if
            not running inside a virtual environment.
        """
        if not VenvHelper.is_in_virtualenv():
            return None
        
        # Check for conda
        if os.environ.get('CONDA_DEFAULT_ENV'):
            return 'conda'
        
        # Check for virtualenv (has real_prefix)
        if hasattr(sys, 'real_prefix'):
            return 'virtualenv'
        
        # Check for venv (has base_prefix)
        if hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
            return 'venv'
        
        # Check VIRTUAL_ENV environment variable
        if os.environ.get('VIRTUAL_ENV'):
            # Try to distinguish between venv and virtualenv
            venv_path = Path(os.environ['VIRTUAL_ENV'])
            if (venv_path / 'pyvenv.cfg').exists():
                return 'venv'
            else:
                return 'virtualenv'
        
        return None
    
    @staticmethod
    def find_project_venv(project_root: Optional[Path] = None) -> Optional[Path]:
        """
        Locate the virtual environment directory for a project.

        Search order:
        1. .venv
        2. venv
        3. env
        4. .env

        Args:
            project_root: Project root directory. If None, uses the current
                working directory.

        Returns:
            Optional[Path]: Path to the virtual environment directory, or
            None if not found.
        """
        if project_root is None:
            project_root = Path.cwd()
        else:
            project_root = Path(project_root)
        
        # Common virtual environment directory names
        venv_names = ['.venv', 'venv', 'env', '.env']
        
        for venv_name in venv_names:
            venv_path = project_root / venv_name
            if venv_path.exists() and venv_path.is_dir():
                # 验证是否是有效的虚拟环境
                if VenvHelper._is_valid_venv(venv_path):
                    return venv_path
        
        return None
    
    @staticmethod
    def _is_valid_venv(venv_path: Path) -> bool:
        """
        Check whether the given directory is a valid virtual environment.

        Args:
            venv_path: Path to the virtual environment directory.

        Returns:
            bool: True if this looks like a valid virtual environment
            directory.
        """
        # Check pyvenv.cfg (venv)
        if (venv_path / 'pyvenv.cfg').exists():
            return True
        
        # Check for Python executable
        if sys.platform.startswith('win'):
            python_exe = venv_path / 'Scripts' / 'python.exe'
        else:
            python_exe = venv_path / 'bin' / 'python'
        
        return python_exe.exists()
    
    @staticmethod
    def get_venv_python(venv_path: Path, prefer_pythonw: bool = False) -> Optional[Path]:
        """
        Get the Python interpreter path for a given virtual environment.

        Args:
            venv_path: Path to the virtual environment.
            prefer_pythonw: On Windows, whether to prefer pythonw.exe (no
                console window) when available.

        Returns:
            Optional[Path]: Path to the Python interpreter, or None if it
            cannot be found.
        """
        if sys.platform.startswith('win'):
            # Windows
            if prefer_pythonw:
                pythonw = venv_path / 'Scripts' / 'pythonw.exe'
                if pythonw.exists():
                    return pythonw
            
            python_exe = venv_path / 'Scripts' / 'python.exe'
            if python_exe.exists():
                return python_exe
        else:
            # macOS/Linux
            python_exe = venv_path / 'bin' / 'python'
            if python_exe.exists():
                return python_exe
            
            python3_exe = venv_path / 'bin' / 'python3'
            if python3_exe.exists():
                return python3_exe
        
        return None
    
    @staticmethod
    def find_python_interpreter(
        project_root: Optional[Path] = None,
        prefer_pythonw: bool = False
    ) -> Path:
        """
        Intelligently locate an appropriate Python interpreter.

        Search order:
        1. If running in a packaged environment, return the current
           interpreter.
        2. If already in a virtual environment, return the current
           interpreter (optionally switching to pythonw.exe on Windows).
        3. If a project root is provided, try to locate a project virtual
           environment under it.
        4. Fallback to the current interpreter.

        Args:
            project_root: Project root directory.
            prefer_pythonw: On Windows, whether to prefer pythonw.exe.

        Returns:
            Path: Path to the selected Python interpreter.
        """
        # 1. Packaged environment: use the current interpreter
        if VenvHelper.is_packaged_environment():
            logger.debug("[VenvHelper] Running in packaged environment, using current interpreter")
            return Path(sys.executable)
        
        # 2. Already inside a virtual environment: use the current interpreter
        if VenvHelper.is_in_virtualenv():
            current_exe = Path(sys.executable)
            
            # Windows: try to switch to pythonw.exe
            if prefer_pythonw and sys.platform.startswith('win'):
                if current_exe.name == 'python.exe':
                    pythonw = current_exe.parent / 'pythonw.exe'
                    if pythonw.exists():
                        logger.debug(f"[VenvHelper] Switching to pythonw.exe: {pythonw}")
                        return pythonw
            
            logger.debug(f"[VenvHelper] Already in virtualenv, using current interpreter: {current_exe}")
            return current_exe
        
        # 3. Look for a project virtual environment
        if project_root:
            venv_path = VenvHelper.find_project_venv(project_root)
            if venv_path:
                python_exe = VenvHelper.get_venv_python(venv_path, prefer_pythonw)
                if python_exe:
                    logger.debug(f"[VenvHelper] Found project venv Python: {python_exe}")
                    return python_exe
        
        # 4. Fallback: use the current interpreter
        logger.debug(f"[VenvHelper] Using current interpreter: {sys.executable}")
        return Path(sys.executable)
    
    @staticmethod
    def create_venv(
        venv_path: Path,
        system_site_packages: bool = False,
        with_pip: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a virtual environment (trying multiple strategies).

        Attempt order:
        1. subprocess + ``python -m venv``
        2. ``virtualenv`` command
        3. ``venv`` module (only in non-packaged environments)

        Args:
            venv_path: Path where the virtual environment should be created.
            system_site_packages: Whether to include system site-packages.
            with_pip: Whether to install pip into the environment.

        Returns:
            Tuple[bool, Optional[str]]: (success flag, error message if any).
        """
        venv_path = Path(venv_path)
        
        # Should not create virtual environments from inside a packaged build
        if VenvHelper.is_packaged_environment():
            error_msg = "Cannot create venv in packaged environment"
            logger.error(f"[VenvHelper] {error_msg}")
            return False, error_msg
        
        # Method 1: subprocess + python -m venv
        success, error = VenvHelper._create_venv_subprocess(
            venv_path, system_site_packages, with_pip
        )
        if success:
            return True, None
        
        logger.warning(f"[VenvHelper] subprocess method failed: {error}")
        
        # Method 2: virtualenv command
        success, error = VenvHelper._create_venv_virtualenv(
            venv_path, system_site_packages
        )
        if success:
            return True, None
        
        logger.warning(f"[VenvHelper] virtualenv method failed: {error}")
        
        # Method 3: venv module (last resort)
        success, error = VenvHelper._create_venv_module(
            venv_path, system_site_packages, with_pip
        )
        if success:
            return True, None
        
        logger.error(f"[VenvHelper] All venv creation methods failed")
        return False, "All venv creation methods failed"
    
    @staticmethod
    def _create_venv_subprocess(
        venv_path: Path,
        system_site_packages: bool,
        with_pip: bool
    ) -> Tuple[bool, Optional[str]]:
        """Create a venv using subprocess and ``python -m venv``."""
        try:
            # Use pythonw.exe on Windows development environment to avoid console window
            # In PyInstaller frozen environment, sys.executable is the .exe file, not python.exe
            python_exe = sys.executable
            if (sys.platform == 'win32' and 
                not getattr(sys, 'frozen', False) and 
                python_exe.endswith('python.exe')):
                pythonw_exe = python_exe.replace('python.exe', 'pythonw.exe')
                if os.path.exists(pythonw_exe):
                    python_exe = pythonw_exe
            
            cmd = [python_exe, "-m", "venv", str(venv_path)]
            if system_site_packages:
                cmd.append("--system-site-packages")
            if not with_pip:
                cmd.append("--without-pip")
            
            result = run_no_window(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info(f"[VenvHelper] Created venv using subprocess: {venv_path}")
                return True, None
            else:
                return False, result.stderr
        
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def _create_venv_virtualenv(
        venv_path: Path,
        system_site_packages: bool
    ) -> Tuple[bool, Optional[str]]:
        """Create a venv using the ``virtualenv`` command."""
        try:
            cmd = ["virtualenv", str(venv_path)]
            if system_site_packages:
                cmd.append("--system-site-packages")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info(f"[VenvHelper] Created venv using virtualenv: {venv_path}")
                return True, None
            else:
                return False, result.stderr
        
        except FileNotFoundError:
            return False, "virtualenv command not found"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def _create_venv_module(
        venv_path: Path,
        system_site_packages: bool,
        with_pip: bool
    ) -> Tuple[bool, Optional[str]]:
        """Create a venv using the built-in ``venv`` module (development only)."""
        try:
            import venv
            
            builder = venv.EnvBuilder(
                system_site_packages=system_site_packages,
                with_pip=with_pip
            )
            builder.create(str(venv_path))
            
            logger.info(f"[VenvHelper] Created venv using venv module: {venv_path}")
            return True, None
        
        except ImportError:
            return False, "venv module not available"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def install_requirements(
        venv_path: Path,
        requirements_file: Path,
        upgrade: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Install dependencies inside a virtual environment.

        Args:
            venv_path: Path to the virtual environment.
            requirements_file: Path to the ``requirements.txt`` file.
            upgrade: Whether to upgrade already-installed packages.

        Returns:
            Tuple[bool, Optional[str]]: (success flag, error message if any).
        """
        python_exe = VenvHelper.get_venv_python(venv_path)
        if not python_exe:
            return False, f"Python executable not found in venv: {venv_path}"
        
        if not requirements_file.exists():
            return False, f"Requirements file not found: {requirements_file}"
        
        try:
            cmd = [str(python_exe), "-m", "pip", "install", "-r", str(requirements_file)]
            if upgrade:
                cmd.append("--upgrade")
            
            result = run_no_window(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )
            
            if result.returncode == 0:
                logger.info(f"[VenvHelper] Installed requirements successfully")
                return True, None
            else:
                return False, result.stderr
        
        except Exception as e:
            return False, str(e)


# 便捷函数
def is_packaged() -> bool:
    """检测是否在打包环境中"""
    return VenvHelper.is_packaged_environment()


def is_in_venv() -> bool:
    """检测是否在虚拟环境中"""
    return VenvHelper.is_in_virtualenv()


def find_python(project_root: Optional[Path] = None, prefer_pythonw: bool = False) -> Path:
    """查找 Python 解释器"""
    return VenvHelper.find_python_interpreter(project_root, prefer_pythonw)


def create_venv(venv_path: Path, system_site_packages: bool = False) -> Tuple[bool, Optional[str]]:
    """创建虚拟环境"""
    return VenvHelper.create_venv(venv_path, system_site_packages)


# ============================================================================
# VenvStatus Enum
# ============================================================================

class VenvStatus(Enum):
    """Virtual environment creation status."""
    NOT_STARTED = "not_started"
    CREATING = "creating"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# AsyncVenvHelper - Non-blocking venv creation and dependency installation
# ============================================================================

class AsyncVenvHelper:
    """Asynchronous virtual environment helper.
    
    Provides non-blocking operations for creating virtual environments and
    installing dependencies in the background without blocking application startup.
    
    Key Features:
    - Async venv creation using asyncio.create_subprocess_exec
    - Progress callbacks for status reporting
    - Background task creation for non-blocking execution
    - Status tracking for multiple venvs
    - Automatic PyInstaller environment detection
    
    Example:
        # Background task (non-blocking)
        task = AsyncVenvHelper.create_background_task(
            venv_path=Path("my_skill/.venv"),
            requirements_file=Path("my_skill/requirements.txt"),
            completion_callback=lambda success, error: print(f"Done: {success}")
        )
        
        # Or await directly
        success, error = await AsyncVenvHelper.ensure_venv_async(
            venv_path=Path("my_skill/.venv"),
            requirements_file=Path("my_skill/requirements.txt")
        )
    """
    
    # Track venv creation status
    _venv_status: Dict[str, VenvStatus] = {}
    _venv_tasks: Dict[str, asyncio.Task] = {}
    
    @staticmethod
    async def create_venv_async(
        venv_path: Path,
        system_site_packages: bool = False,
        with_pip: bool = True,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Create a virtual environment asynchronously.
        
        Args:
            venv_path: Path where the virtual environment should be created.
            system_site_packages: Whether to include system site-packages.
            with_pip: Whether to install pip into the environment.
            progress_callback: Optional callback(message, progress_percent).
        
        Returns:
            Tuple[bool, Optional[str]]: (success flag, error message if any).
        """
        venv_path = Path(venv_path)
        venv_key = str(venv_path)
        
        # Should not create virtual environments from inside a packaged build
        if VenvHelper.is_packaged_environment():
            error_msg = "Cannot create venv in packaged environment"
            logger.info(f"[AsyncVenvHelper] {error_msg} - skipping")
            return True, None  # Return success in packaged environment
        
        # Update status
        AsyncVenvHelper._venv_status[venv_key] = VenvStatus.CREATING
        
        if progress_callback:
            progress_callback("Starting venv creation...", 0)
        
        # Try subprocess method
        success, error = await AsyncVenvHelper._create_venv_subprocess_async(
            venv_path, system_site_packages, with_pip, progress_callback
        )
        
        if success:
            AsyncVenvHelper._venv_status[venv_key] = VenvStatus.COMPLETED
            if progress_callback:
                progress_callback("Venv created successfully", 100)
            return True, None
        
        logger.error(f"[AsyncVenvHelper] Venv creation failed: {error}")
        AsyncVenvHelper._venv_status[venv_key] = VenvStatus.FAILED
        if progress_callback:
            progress_callback("Venv creation failed", 0)
        return False, error
    
    @staticmethod
    async def _create_venv_subprocess_async(
        venv_path: Path,
        system_site_packages: bool,
        with_pip: bool,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Create a venv using subprocess asynchronously."""
        try:
            # Use pythonw.exe on Windows development environment to avoid console window
            python_exe = sys.executable
            if (sys.platform == 'win32' and 
                not getattr(sys, 'frozen', False) and 
                python_exe.endswith('python.exe')):
                pythonw_exe = python_exe.replace('python.exe', 'pythonw.exe')
                if os.path.exists(pythonw_exe):
                    python_exe = pythonw_exe
            
            cmd = [python_exe, "-m", "venv", str(venv_path)]
            if system_site_packages:
                cmd.append("--system-site-packages")
            if not with_pip:
                cmd.append("--without-pip")
            
            if progress_callback:
                progress_callback(f"Running: {' '.join(cmd)}", 10)
            
            logger.info(f"[AsyncVenvHelper] Creating venv: {' '.join(cmd)}")
            
            # Create subprocess asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=120
                )
            except asyncio.TimeoutError:
                process.kill()
                return False, "Venv creation timed out after 120 seconds"
            
            if process.returncode == 0:
                logger.info(f"[AsyncVenvHelper] ✅ Created venv: {venv_path}")
                if progress_callback:
                    progress_callback("Venv created", 80)
                return True, None
            else:
                error_msg = stderr.decode('utf-8', errors='replace') if stderr else "Unknown error"
                logger.error(f"[AsyncVenvHelper] ❌ Venv creation failed: {error_msg}")
                return False, error_msg
        
        except Exception as e:
            logger.error(f"[AsyncVenvHelper] ❌ Exception during venv creation: {e}")
            return False, str(e)
    
    @staticmethod
    async def install_requirements_async(
        venv_path: Path,
        requirements_file: Path,
        upgrade: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Install dependencies asynchronously.
        
        Args:
            venv_path: Path to the virtual environment.
            requirements_file: Path to the requirements.txt file.
            upgrade: Whether to upgrade already-installed packages.
            progress_callback: Optional callback(message, progress_percent).
        
        Returns:
            Tuple[bool, Optional[str]]: (success flag, error message if any).
        """
        venv_key = str(venv_path)
        AsyncVenvHelper._venv_status[venv_key] = VenvStatus.INSTALLING
        
        # In packaged environment, skip installation
        if VenvHelper.is_packaged_environment():
            logger.info(f"[AsyncVenvHelper] Packaged environment - skipping pip install")
            AsyncVenvHelper._venv_status[venv_key] = VenvStatus.COMPLETED
            return True, None
        
        python_exe = VenvHelper.get_venv_python(venv_path)
        if not python_exe:
            error_msg = f"Python executable not found in venv: {venv_path}"
            AsyncVenvHelper._venv_status[venv_key] = VenvStatus.FAILED
            return False, error_msg
        
        if not requirements_file.exists():
            error_msg = f"Requirements file not found: {requirements_file}"
            AsyncVenvHelper._venv_status[venv_key] = VenvStatus.FAILED
            return False, error_msg
        
        try:
            cmd = [str(python_exe), "-m", "pip", "install", "-r", str(requirements_file)]
            if upgrade:
                cmd.append("--upgrade")
            
            if progress_callback:
                progress_callback(f"Installing dependencies...", 0)
            
            logger.info(f"[AsyncVenvHelper] Installing requirements: {requirements_file}")
            
            # Create subprocess asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Stream output and update progress
            stdout_lines = []
            stderr_lines = []
            
            async def read_stream(stream, lines_list, is_stderr=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:  # Only log non-empty lines
                        lines_list.append(decoded)
                        
                        # Update progress based on output
                        if progress_callback and not is_stderr:
                            if "Collecting" in decoded:
                                progress_callback(f"Collecting packages...", 20)
                            elif "Downloading" in decoded:
                                progress_callback(f"Downloading...", 40)
                            elif "Installing" in decoded:
                                progress_callback(f"Installing...", 60)
                            elif "Successfully installed" in decoded:
                                progress_callback(f"Installation complete", 90)
            
            # Read both streams concurrently
            await asyncio.gather(
                read_stream(process.stdout, stdout_lines, False),
                read_stream(process.stderr, stderr_lines, True)
            )
            
            # Wait for process to complete
            await process.wait()
            
            if process.returncode == 0:
                logger.info(f"[AsyncVenvHelper] ✅ Installed requirements successfully")
                AsyncVenvHelper._venv_status[venv_key] = VenvStatus.COMPLETED
                if progress_callback:
                    progress_callback("Dependencies installed successfully", 100)
                return True, None
            else:
                error_msg = '\n'.join(stderr_lines) if stderr_lines else "Unknown error"
                logger.error(f"[AsyncVenvHelper] ❌ pip install failed: {error_msg}")
                AsyncVenvHelper._venv_status[venv_key] = VenvStatus.FAILED
                if progress_callback:
                    progress_callback("Installation failed", 0)
                return False, error_msg
        
        except Exception as e:
            logger.error(f"[AsyncVenvHelper] ❌ Exception during installation: {e}")
            AsyncVenvHelper._venv_status[venv_key] = VenvStatus.FAILED
            if progress_callback:
                progress_callback(f"Error: {str(e)}", 0)
            return False, str(e)
    
    @staticmethod
    def get_venv_status(venv_path: Path) -> VenvStatus:
        """Get the current status of a venv creation/installation."""
        venv_key = str(venv_path)
        return AsyncVenvHelper._venv_status.get(venv_key, VenvStatus.NOT_STARTED)
    
    @staticmethod
    async def ensure_venv_async(
        venv_path: Path,
        requirements_file: Optional[Path] = None,
        system_site_packages: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Ensure venv exists and dependencies are installed (async).
        
        This is a high-level convenience method that:
        1. Creates venv if it doesn't exist
        2. Installs requirements if provided
        
        Args:
            venv_path: Path to the virtual environment.
            requirements_file: Optional path to requirements.txt.
            system_site_packages: Whether to include system site-packages.
            progress_callback: Optional callback(message, progress_percent).
        
        Returns:
            Tuple[bool, Optional[str]]: (success flag, error message if any).
        """
        venv_path = Path(venv_path)
        
        # In packaged environment, skip venv creation
        if VenvHelper.is_packaged_environment():
            logger.info(f"[AsyncVenvHelper] Packaged environment - skipping venv setup")
            if progress_callback:
                progress_callback("Packaged environment (no venv needed)", 100)
            return True, None
        
        # Check if venv already exists
        if not venv_path.exists():
            if progress_callback:
                progress_callback("Creating virtual environment...", 0)
            
            success, error = await AsyncVenvHelper.create_venv_async(
                venv_path,
                system_site_packages=system_site_packages,
                progress_callback=progress_callback
            )
            
            if not success:
                return False, error
        else:
            logger.info(f"[AsyncVenvHelper] Venv already exists: {venv_path}")
            if progress_callback:
                progress_callback("Virtual environment exists", 50)
        
        # Install requirements if provided
        if requirements_file and requirements_file.exists():
            if progress_callback:
                progress_callback("Installing dependencies...", 50)
            
            success, error = await AsyncVenvHelper.install_requirements_async(
                venv_path,
                requirements_file,
                progress_callback=progress_callback
            )
            
            if not success:
                return False, error
        
        if progress_callback:
            progress_callback("Setup complete", 100)
        
        return True, None
    
    @staticmethod
    def create_background_task(
        venv_path: Path,
        requirements_file: Optional[Path] = None,
        system_site_packages: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        completion_callback: Optional[Callable[[bool, Optional[str]], None]] = None
    ) -> asyncio.Task:
        """Create a background task for venv setup.
        
        This method creates an asyncio task that runs in the background.
        The application can continue running while the venv is being created.
        
        Args:
            venv_path: Path to the virtual environment.
            requirements_file: Optional path to requirements.txt.
            system_site_packages: Whether to include system site-packages.
            progress_callback: Optional callback(message, progress_percent).
            completion_callback: Optional callback(success, error_message).
        
        Returns:
            asyncio.Task: The background task.
        
        Example:
            task = AsyncVenvHelper.create_background_task(
                venv_path=Path("my_skill/.venv"),
                requirements_file=Path("my_skill/requirements.txt"),
                completion_callback=lambda success, error: 
                    print(f"Venv ready: {success}")
            )
            # Application continues without waiting
            # Task runs in background
        """
        venv_key = str(venv_path)
        
        async def task_wrapper():
            try:
                success, error = await AsyncVenvHelper.ensure_venv_async(
                    venv_path,
                    requirements_file,
                    system_site_packages,
                    progress_callback
                )
                
                if completion_callback:
                    completion_callback(success, error)
                
                return success, error
            except Exception as e:
                logger.error(f"[AsyncVenvHelper] ❌ Background task failed: {e}")
                if completion_callback:
                    completion_callback(False, str(e))
                return False, str(e)
        
        # Create and store the task
        task = asyncio.create_task(task_wrapper())
        AsyncVenvHelper._venv_tasks[venv_key] = task
        
        return task


# Convenience async functions
async def create_venv_async(
    venv_path: Path,
    system_site_packages: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Tuple[bool, Optional[str]]:
    """Create virtual environment asynchronously"""
    return await AsyncVenvHelper.create_venv_async(
        venv_path,
        system_site_packages=system_site_packages,
        progress_callback=progress_callback
    )


async def install_requirements_async(
    venv_path: Path,
    requirements_file: Path,
    upgrade: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Tuple[bool, Optional[str]]:
    """Install requirements asynchronously"""
    return await AsyncVenvHelper.install_requirements_async(
        venv_path,
        requirements_file,
        upgrade=upgrade,
        progress_callback=progress_callback
    )
