#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""\neCan.ai OTA Installer Module\nHandles installation of update packages and application restart logic\n\nSupported formats:\n- Windows: EXE, MSI\n- macOS: PKG, DMG\n- Linux: AppImage, DEB, RPM (planned)\n"""

import os
import sys
import subprocess
import time
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from utils.logger_helper import logger_helper as logger
from ota.config.loader import ota_config
from ota.gui.i18n import get_translator

# Get translator instance
_tr = get_translator()


class InstallationManager:
    """Installation Manager"""
    
    def __init__(self, progress_callback=None):
        """
        Initialize Installation Manager
        
        Args:
            progress_callback: Optional callback function(progress: int, phase: str)
                              Called when installation progress updates
        """
        self.platform = sys.platform
        self.backup_dir = None
        self.progress_callback = progress_callback
        
    def install_package(self, package_path: Path, install_options: Dict[str, Any] = None) -> bool:
        """Install update package"""
        if not install_options:
            install_options = {}
            
        try:
            logger.info(f"Starting installation: {package_path}")
            
            # Create backup
            if install_options.get('create_backup', True):
                if not self._create_backup():
                    logger.warning("Failed to create backup, continuing installation...")
            
            # Select installation method based on file type
            if package_path.suffix.lower() == '.exe':
                return self._install_exe(package_path, install_options)
            elif package_path.suffix.lower() == '.msi':
                return self._install_msi(package_path, install_options)
            elif package_path.suffix.lower() == '.pkg':
                return self._install_pkg(package_path, install_options)
            elif package_path.suffix.lower() == '.dmg':
                return self._install_dmg(package_path, install_options)
            else:
                logger.error(f"Unsupported package format: {package_path.suffix}")
                return False
                
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False
    
    def _create_backup(self) -> bool:
        """Create backup of current application"""
        try:
            # ✅ Skip backup in development environment
            if not getattr(sys, 'frozen', False):
                logger.info("Running in development environment, skipping backup")
                return True
            
            # Get current application path (packaged application only)
            app_path = Path(sys.executable).parent
            
            # Create backup directory
            backup_root = Path(tempfile.gettempdir()) / "ecan_backup"
            backup_root.mkdir(exist_ok=True)
            
            timestamp = int(time.time())
            self.backup_dir = backup_root / f"backup_{timestamp}"
            
            logger.info(f"Creating backup: {app_path} -> {self.backup_dir}")
            
            # Copy application files
            shutil.copytree(
                app_path, 
                self.backup_dir, 
                ignore=shutil.ignore_patterns('*.log', '__pycache__'),
                symlinks=True  # ✅ Copy symlinks as symlinks, don't follow them
            )
            
            logger.info(f"Backup created successfully: {self.backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False
    
    def _install_exe(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install Windows EXE package - OTA silent update"""
        try:
            logger.info(f"Installing Windows EXE: {package_path}")
            
            # For OTA updates, use truly silent installation
            if install_options.get('silent', True):
                if getattr(sys, 'frozen', False):
                    # Get current installation directory
                    install_dir = Path(sys.executable).parent
                    logger.info(f"Target installation directory: {install_dir}")
                    
                    # Use Inno Setup silent installation parameters with progress
                    # /SILENT = Silent with progress bar (not /VERYSILENT)
                    # /SUPPRESSMSGBOXES = Suppress message boxes
                    # /NORESTART = Don't restart computer
                    # /CLOSEAPPLICATIONS = Close running applications
                    # /DIR= = Installation directory (must use quotes if path has spaces)
                    cmd = [
                        str(package_path),
                        '/SILENT',              # ✅ Shows progress bar
                        '/SUPPRESSMSGBOXES',
                        '/NORESTART',
                        '/CLOSEAPPLICATIONS',
                        f'/DIR={install_dir}'
                    ]
                    
                    logger.info(f"Executing OTA update with progress: {' '.join(cmd)}")
                    logger.info("Using Inno Setup parameters: /SILENT (with progress) /SUPPRESSMSGBOXES /NORESTART")
                    
                    # Set OTA installation flag to skip exit confirmation dialog
                    from ota.core.download_manager import download_manager
                    download_manager.set_installing(True)
                    
                    # Launch installer without waiting
                    try:
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                        )
                        
                        logger.info(f"Installer launched (PID: {process.pid})")
                        logger.info("Application will exit in 3 seconds for file replacement...")
                        
                        # Schedule application exit
                        import threading
                        def delayed_exit():
                            time.sleep(3)
                            logger.info("Exiting for installer to replace files...")
                            os._exit(0)
                        
                        threading.Thread(target=delayed_exit, daemon=True).start()
                        
                        return True
                        
                    except Exception as e:
                        logger.error(f"Failed to launch installer: {e}")
                        return False
                else:
                    # Development environment - use /SILENT for OTA testing
                    logger.warning("Running in development mode, using /SILENT for OTA testing")
                    
                    # Set OTA installation flag to skip exit confirmation dialog
                    from ota.core.download_manager import download_manager
                    download_manager.set_installing(True)
                    
                    cmd = [
                        str(package_path),
                        '/SILENT',              # Shows progress bar, skips wizard pages
                        '/SUPPRESSMSGBOXES',
                        '/NORESTART',
                    ]
                    logger.info(f"Development OTA command: {' '.join(cmd)}")
                    subprocess.Popen(cmd)
                    
                    # Schedule application exit for development environment
                    import threading
                    def delayed_exit():
                        time.sleep(3)
                        logger.info("Development mode: Exiting for installer to replace files...")
                        os._exit(0)
                    
                    threading.Thread(target=delayed_exit, daemon=True).start()
                    logger.info("Development mode: Application will exit in 3 seconds...")
                    
                    return True
            else:
                # Non-silent mode - launch installer with UI
                logger.info("Launching installer with UI")
                subprocess.Popen([str(package_path)])
                return True
                
        except Exception as e:
            logger.error(f"EXE installation error: {e}")
            return False
    
    def _install_msi(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install Windows MSI package - OTA silent update"""
        try:
            logger.info(f"Installing Windows MSI: {package_path}")
            
            # Build msiexec command for silent OTA update
            cmd = ["msiexec", "/i", str(package_path)]
            
            if install_options.get('silent', True):
                # Silent installation parameters with progress:
                # /qb = Basic UI with progress bar (not /qn which is completely silent)
                # /norestart = Don't restart automatically
                cmd.extend(["/qb", "/norestart"])
                
                # If in packaged environment, specify installation directory
                if getattr(sys, 'frozen', False):
                    install_dir = Path(sys.executable).parent
                    cmd.append(f'INSTALLDIR="{install_dir}"')
                    cmd.append('REINSTALLMODE=vamus')  # Reinstall all files
                    cmd.append('REINSTALL=ALL')  # Reinstall all features
            
            # Execute installation in background
            logger.info(f"Executing silent MSI update: {' '.join(cmd)}")
            
            # Launch installer without waiting
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            logger.info(f"MSI installer launched (PID: {process.pid})")
            
            # Schedule application exit
            import threading
            def delayed_exit():
                time.sleep(3)
                logger.info("Exiting for MSI installer to replace files...")
                os._exit(0)
            
            threading.Thread(target=delayed_exit, daemon=True).start()
            
            return True
                
        except Exception as e:
            logger.error(f"MSI installation error: {e}")
            return False
    
    def _install_pkg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install macOS PKG package - OTA update with progress
        
        Note: macOS PKG installation requires administrator privileges.
        
        Installation approach:
        - Use AppleScript with 'installer' command for silent installation with progress
        - Shows: Password prompt + Progress in terminal/notification
        - No installation wizard UI
        """
        try:
            logger.info(f"Installing macOS PKG: {package_path}")
            
            # For OTA updates, use installer command with admin privileges
            if install_options.get('silent', True):
                logger.info("Starting PKG installation (no wizard, with progress)...")
                
                # Use osascript with a different approach for real-time output
                # We'll use a shell script that runs installer and outputs progress
                try:
                    logger.info("⚠️  macOS security requires administrator password for PKG installation")
                    logger.info("Installation mode:")
                    logger.info("  • Password prompt: YES (required)")
                    logger.info("  • Installation wizard: NO")
                    logger.info("  • Progress logging: YES")
                    
                    # Create a temporary script for installation with real-time output
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                        script_path = f.name
                        f.write(f'''#!/bin/bash
installer -pkg "{package_path}" -target / -verboseR 2>&1
''')
                    
                    # Make script executable
                    os.chmod(script_path, 0o755)
                    
                    # Launch installer with osascript for password prompt
                    # Use a different approach: run with sudo through osascript
                    applescript = f'''
                    do shell script "{script_path}" with administrator privileges
                    '''
                    
                    # Launch installer in background
                    process = subprocess.Popen(
                        ["osascript", "-e", applescript],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,  # Merge stderr to stdout
                        text=True,
                        bufsize=0,  # Unbuffered for real-time output
                        universal_newlines=True
                    )
                    
                    logger.info(f"PKG installer launched (PID: {process.pid})")
                    logger.info("Waiting for user to enter password and installation to complete...")
                    
                    # Show initial notification
                    try:
                        subprocess.run([
                            "osascript", "-e",
                            f'display notification "{_tr.tr("installing_update")}" with title "{_tr.tr("app_update")}"'
                        ], check=False)
                    except Exception:
                        pass
                    
                    # Since AppleScript doesn't support real-time output streaming,
                    # we'll simulate progress based on time estimation
                    try:
                        import time as time_module
                        import threading
                        
                        start_time = time_module.time()
                        timeout = 600  # 10 minutes
                        
                        # Estimated installation phases and durations (in seconds)
                        phases = [
                            (0, 5, _tr.tr("preparing_install")),
                            (5, 10, _tr.tr("verifying_package")),
                            (10, 50, _tr.tr("writing_files")),
                            (50, 55, _tr.tr("running_scripts")),
                            (55, 58, _tr.tr("writing_receipt")),
                            (58, 60, _tr.tr("verifying_package")),
                        ]
                        
                        # Start a thread to simulate progress
                        def simulate_progress():
                            elapsed = 0
                            while process.poll() is None and elapsed < timeout:
                                elapsed = time_module.time() - start_time
                                
                                # Find current phase
                                current_phase = _tr.tr("installing")
                                progress = 0
                                
                                for start_sec, end_sec, phase_name in phases:
                                    if start_sec <= elapsed < end_sec:
                                        # Calculate progress within this phase
                                        phase_progress = (elapsed - start_sec) / (end_sec - start_sec)
                                        # Map to overall progress (0-100)
                                        overall_start = (start_sec / 60) * 100
                                        overall_end = (end_sec / 60) * 100
                                        progress = overall_start + (overall_end - overall_start) * phase_progress
                                        current_phase = phase_name
                                        break
                                
                                # Cap at 95% until actually complete
                                progress = min(95, progress)
                                
                                # Call progress callback
                                if self.progress_callback:
                                    try:
                                        self.progress_callback(int(progress), current_phase)
                                    except Exception as e:
                                        logger.debug(f"Progress callback error: {e}")
                                
                                time_module.sleep(0.5)  # Update every 0.5 seconds
                        
                        # Start progress simulation thread
                        progress_thread = threading.Thread(target=simulate_progress, daemon=True)
                        progress_thread.start()
                        
                        # Wait for installation to complete
                        stdout, stderr = process.communicate(timeout=timeout)
                        
                        # Stop progress thread
                        progress_thread.join(timeout=1)
                        
                        # Send 100% progress
                        if self.progress_callback:
                            try:
                                self.progress_callback(100, _tr.tr("install_complete"))
                            except Exception as e:
                                logger.debug(f"Progress callback error: {e}")
                        
                        # Clean up temporary script
                        try:
                            os.unlink(script_path)
                        except Exception:
                            pass
                    
                    except subprocess.TimeoutExpired:
                        logger.error("Installation timeout (10 minutes)")
                        process.kill()
                        # Clean up temporary script
                        try:
                            os.unlink(script_path)
                        except Exception:
                            pass
                        return False
                    
                    # Check result
                    try:
                        
                        if process.returncode == 0:
                            logger.info("✅ PKG installation completed successfully")
                            if stdout:
                                logger.info(f"Installation output: {stdout}")
                            
                            # Show completion notification
                            try:
                                subprocess.run([
                                    "osascript", "-e",
                                    f'display notification "{_tr.tr("install_complete_restart")}" with title "{_tr.tr("app_update")}"'
                                ])
                            except Exception as e:
                                logger.warning(f"Failed to show notification: {e}")
                            
                            # Schedule application restart
                            logger.info("Installation complete, application will restart in 3 seconds...")
                            
                            import threading
                            def delayed_restart():
                                time.sleep(3)
                                logger.info("Restarting application...")
                                self._restart_application()
                            
                            threading.Thread(target=delayed_restart, daemon=True).start()
                            
                            return True
                        else:
                            logger.error(f"❌ PKG installation failed: {stderr}")
                            return False
                            
                    except subprocess.TimeoutExpired:
                        logger.error("Installation timeout (10 minutes)")
                        process.kill()
                        return False
                        
                except Exception as e:
                    logger.error(f"Failed to launch PKG installer: {e}")
                    return False
            else:
                # Non-silent mode - launch installer with full UI
                logger.info("Launching PKG installer with full UI...")
                subprocess.Popen(["open", str(package_path)])
                return True
                    
        except Exception as e:
            logger.error(f"PKG installation error: {e}")
            return False
    
    def _install_dmg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install macOS DMG package"""
        try:
            logger.info(f"Installing macOS DMG: {package_path}")
            
            # Mount DMG
            mount_result = subprocess.run(
                ["hdiutil", "attach", str(package_path), "-nobrowse", "-quiet"],
                capture_output=True, text=True
            )
            
            if mount_result.returncode != 0:
                logger.error(f"Failed to mount DMG: {mount_result.stderr}")
                return False
            
            try:
                # Find mount point
                mount_point = self._find_dmg_mount_point(package_path)
                if not mount_point:
                    logger.error("Could not find DMG mount point")
                    return False
                
                # Find .app file
                app_files = list(Path(mount_point).glob("*.app"))
                if not app_files:
                    logger.error("No .app file found in DMG")
                    return False
                
                # Copy to Applications directory
                target_dir = Path("/Applications")
                for app_file in app_files:
                    target_path = target_dir / app_file.name
                    
                    # If target exists, delete it first
                    if target_path.exists():
                        shutil.rmtree(target_path)
                    
                    # Copy application
                    shutil.copytree(app_file, target_path)
                    logger.info(f"Copied {app_file.name} to {target_path}")
                
                return True
                
            finally:
                # Unmount DMG
                subprocess.run(
                    ["hdiutil", "detach", mount_point or ""],
                    capture_output=True
                )
                
        except Exception as e:
            logger.error(f"DMG installation error: {e}")
            return False
    
    def _find_dmg_mount_point(self, dmg_path: Path) -> Optional[str]:
        """Find DMG mount point"""
        try:
            result = subprocess.run(
                ["hdiutil", "info", "-plist"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                return None
            
            import plistlib
            plist_data = plistlib.loads(result.stdout.encode())
            
            for image in plist_data.get('images', []):
                image_path = image.get('image-path')
                if image_path and Path(image_path).name == dmg_path.name:
                    for entity in image.get('system-entities', []):
                        mount_point = entity.get('mount-point')
                        if mount_point:
                            return mount_point
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find mount point: {e}")
            return None
    
    def restart_application(self, delay_seconds: int = 3) -> bool:
        """Restart application"""
        try:
            logger.info(f"Restarting application in {delay_seconds} seconds...")
            
            if getattr(sys, 'frozen', False):
                # Packaged application
                app_executable = sys.executable
            else:
                # Development environment
                app_executable = sys.executable
                app_args = [sys.argv[0]]
            
            # Create restart script
            restart_script = self._create_restart_script(app_executable, delay_seconds)
            
            if restart_script:
                # Execute restart script
                if self.platform.startswith('win'):
                    subprocess.Popen([restart_script], shell=True)
                else:
                    subprocess.Popen(['sh', restart_script])
                
                logger.info("Restart script launched")
                
                # Exit current application
                time.sleep(1)
                os._exit(0)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
            return False
    
    def _create_restart_script(self, app_executable: str, delay_seconds: int) -> Optional[str]:
        """Create restart script"""
        try:
            script_dir = Path(tempfile.gettempdir()) / "ecan_restart"
            script_dir.mkdir(exist_ok=True)
            
            if self.platform.startswith('win'):
                # Windows batch script
                script_path = script_dir / "restart.bat"
                script_content = f"""@echo off
echo Waiting {delay_seconds} seconds before restart...
timeout /t {delay_seconds} /nobreak >nul
echo Restarting eCan...
start "" "{app_executable}"
del "%~f0"
"""
            else:
                # Unix shell script
                script_path = script_dir / "restart.sh"
                script_content = f"""#!/bin/bash
echo "Waiting {delay_seconds} seconds before restart..."
sleep {delay_seconds}
echo "Restarting eCan..."
{app_executable} &
rm "$0"
"""
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Set execute permission (Unix)
            if not self.platform.startswith('win'):
                os.chmod(script_path, 0o755)
            
            logger.info(f"Restart script created: {script_path}")
            return str(script_path)
            
        except Exception as e:
            logger.error(f"Failed to create restart script: {e}")
            return None
    
    def restore_backup(self) -> bool:
        """Restore backup"""
        if not self.backup_dir or not self.backup_dir.exists():
            logger.error("No backup available to restore")
            return False
        
        try:
            # Get current application path
            if getattr(sys, 'frozen', False):
                app_path = Path(sys.executable).parent
            else:
                app_path = Path(__file__).parent.parent.parent
            
            logger.info(f"Restoring backup: {self.backup_dir} -> {app_path}")
            
            # Delete current application
            if app_path.exists():
                shutil.rmtree(app_path)
            
            # Restore backup
            shutil.copytree(self.backup_dir, app_path)
            
            logger.info("Backup restored successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def cleanup_backup(self):
        """Clean up backup files"""
        if self.backup_dir and self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir)
                logger.info(f"Backup cleaned up: {self.backup_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup backup: {e}")
    
    def _restart_application(self):
        """
        Restart the application after installation
        
        This method will:
        1. Get the application executable path
        2. Launch a new instance
        3. Exit the current instance
        """
        try:
            if getattr(sys, 'frozen', False):
                # ✅ Packaged application
                if self.platform == 'darwin':
                    # macOS: Get .app bundle path
                    exe_path = Path(sys.executable)
                    # Navigate up to find .app bundle
                    app_bundle = exe_path
                    while app_bundle.suffix != '.app' and app_bundle.parent != app_bundle:
                        app_bundle = app_bundle.parent
                    
                    if app_bundle.suffix == '.app':
                        logger.info(f"Restarting application: {app_bundle}")
                        # Use 'open' command to launch the app
                        subprocess.Popen(['open', '-n', str(app_bundle)])
                        
                        # Exit current instance to release lock
                        logger.info("Exiting current instance in 1 second...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.error("Could not find .app bundle")
                        return
                        
                elif self.platform.startswith('win'):
                    # Windows: Use delayed restart script to avoid single instance lock conflict
                    exe_path = sys.executable
                    logger.info(f"Restarting application: {exe_path}")
                    
                    restart_script = self._create_restart_script(exe_path, delay_seconds=3)
                    if restart_script:
                        subprocess.Popen([restart_script], shell=True)
                        logger.info("Restart script launched, exiting current instance...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.warning("Failed to create restart script, manual restart required")
                    
                else:
                    # Linux: Use delayed restart script to avoid single instance lock conflict
                    exe_path = sys.executable
                    logger.info(f"Restarting application: {exe_path}")
                    
                    restart_script = self._create_restart_script(exe_path, delay_seconds=3)
                    if restart_script:
                        subprocess.Popen(['sh', restart_script])
                        logger.info("Restart script launched, exiting current instance...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.warning("Failed to create restart script, manual restart required")
                
            else:
                # ✅ Development environment - restart using python
                logger.info("Running in development environment")
                logger.info("Attempting to restart application...")
                
                # Get the main script path
                import __main__
                if hasattr(__main__, '__file__'):
                    main_script = Path(__main__.__file__).resolve()
                    logger.info(f"Restarting: python3 {main_script}")
                    
                    # Create a delayed restart script to avoid single instance lock conflict
                    restart_script = self._create_restart_script(
                        f"python3 {main_script}",
                        delay_seconds=3
                    )
                    
                    if restart_script:
                        # Launch restart script
                        if self.platform == 'darwin':
                            subprocess.Popen(['sh', restart_script])
                        else:
                            subprocess.Popen([restart_script])
                        
                        logger.info("Restart script launched, exiting current instance...")
                        time.sleep(1)
                        os._exit(0)
                    else:
                        logger.warning("Failed to create restart script, manual restart required")
                else:
                    logger.warning("Could not determine main script path")
                    logger.info("Please manually restart the application")
                
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
    
    def _parse_installer_progress(self, line: str) -> float:
        """
        Parse progress percentage from installer output
        
        Args:
            line: Output line from installer command
            
        Returns:
            Progress percentage (0-100) or None if not found
        """
        try:
            # installer output format: "installer:%12.345678"
            if 'installer:%' in line:
                # Extract percentage
                parts = line.split('installer:%')
                if len(parts) > 1:
                    percent_str = parts[1].strip()
                    # Get first number (may have more text after)
                    percent = float(percent_str.split()[0])
                    return min(100.0, max(0.0, percent))
        except Exception as e:
            logger.debug(f"Failed to parse progress from line: {line[:50]}... Error: {e}")
        
        return None
    
    def _show_installation_progress_dialog(self):
        """
        Show Qt progress dialog for installation
        
        Returns:
            Progress dialog object or None if Qt is not available
        """
        try:
            from PyQt5.QtWidgets import QProgressDialog, QApplication
            from PyQt5.QtCore import Qt
            
            # Get or create QApplication instance
            app = QApplication.instance()
            if app is None:
                logger.warning("No QApplication instance, cannot show progress dialog")
                return None
            
            # Create progress dialog
            dialog = QProgressDialog(
                _tr.tr("installing_update"),
                None,  # No cancel button
                0,
                100
            )
            dialog.setWindowTitle(_tr.tr("app_update"))
            dialog.setWindowModality(Qt.WindowModal)
            dialog.setMinimumDuration(0)  # Show immediately
            dialog.setValue(0)
            dialog.show()
            
            # Process events to show dialog
            app.processEvents()
            
            logger.info("Installation progress dialog shown")
            return dialog
            
        except Exception as e:
            logger.warning(f"Failed to show progress dialog: {e}")
            return None
    
    def _update_progress_dialog(self, dialog, progress: float, status_line: str = ""):
        """
        Update progress dialog with current progress
        
        Args:
            dialog: Qt progress dialog
            progress: Progress percentage (0-100)
            status_line: Current status line from installer
        """
        try:
            from PyQt5.QtWidgets import QApplication
            
            # Update progress value
            dialog.setValue(int(progress))
            
            # Update label text with phase information
            if 'PHASE:' in status_line:
                phase = status_line.split('PHASE:')[-1].strip()
                if phase:
                    text = _tr.tr("installing_update_with_phase").format(progress=int(progress), phase=phase)
                    dialog.setLabelText(text)
            else:
                text = _tr.tr("installing_update_progress").format(progress=int(progress))
                dialog.setLabelText(text)
            
            # Process events to update UI
            app = QApplication.instance()
            if app:
                app.processEvents()
            
            logger.debug(f"Progress updated: {progress:.1f}%")
            
        except Exception as e:
            logger.debug(f"Failed to update progress dialog: {e}")
    
    def _close_progress_dialog(self, dialog):
        """
        Close progress dialog
        
        Args:
            dialog: Qt progress dialog
        """
        try:
            if dialog:
                dialog.close()
                logger.info("Installation progress dialog closed")
        except Exception as e:
            logger.warning(f"Failed to close progress dialog: {e}")


# Global installation manager instance
installation_manager = InstallationManager()
