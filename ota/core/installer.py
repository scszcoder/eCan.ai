#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""\nECBot OTA Installer Module\nHandles installation of update packages and application restart logic\n\nSupported formats:\n- Windows: EXE, MSI\n- macOS: PKG, DMG\n- Linux: AppImage, DEB, RPM (planned)\n"""

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


class InstallationManager:
    """Installation Manager"""
    
    def __init__(self):
        self.platform = sys.platform
        self.backup_dir = None
        
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
            backup_root = Path(tempfile.gettempdir()) / "ecbot_backup"
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
        """Install Windows EXE package"""
        try:
            logger.info(f"Installing Windows EXE: {package_path}")
            
            # Build installation command
            cmd = [str(package_path)]
            
            # Add silent installation parameters
            if install_options.get('silent', True):
                # Try common silent installation parameters
                silent_args = ['/S', '/SILENT', '/VERYSILENT', '/quiet', '/q']
                cmd.extend(silent_args[:1])  # Use first parameter
            
            # Execute installation
            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("EXE installation completed successfully")
                return True
            else:
                logger.error(f"EXE installation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Installation timeout")
            return False
        except Exception as e:
            logger.error(f"EXE installation error: {e}")
            return False
    
    def _install_msi(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install Windows MSI package"""
        try:
            logger.info(f"Installing Windows MSI: {package_path}")
            
            # Build msiexec command
            cmd = ["msiexec", "/i", str(package_path)]
            
            if install_options.get('silent', True):
                cmd.extend(["/quiet", "/norestart"])
            
            # Execute installation
            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("MSI installation completed successfully")
                return True
            else:
                logger.error(f"MSI installation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Installation timeout")
            return False
        except Exception as e:
            logger.error(f"MSI installation error: {e}")
            return False
    
    def _install_pkg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """Install macOS PKG package"""
        try:
            logger.info(f"Installing macOS PKG: {package_path}")
            
            # PKG requires administrator privileges
            # Build installation command
            cmd = ["sudo", "installer", "-pkg", str(package_path), "-target", "/"]
            
            # Add verbose logging option
            if install_options.get('verbose', False):
                cmd.extend(["-verbose"])
            
            # Check if in interactive environment
            if install_options.get('silent', False) or not sys.stdin.isatty():
                # Non-interactive environment, use open command to launch installer
                logger.info("Launching macOS Installer...")
                
                try:
                    # ✅ Use 'open -W' to wait for installer to complete
                    # -W flag waits until the application quits before returning
                    result = subprocess.run(
                        ["open", "-W", str(package_path)],
                        capture_output=True, text=True, timeout=600  # 10 minutes timeout
                    )
                    
                    if result.returncode == 0:
                        logger.info("PKG installer completed successfully")
                        
                        # ✅ Auto-restart application if requested
                        if install_options.get('auto_restart', True):
                            logger.info("Installation complete, restarting application...")
                            self._restart_application()
                        
                        return True
                    else:
                        logger.error(f"Failed to launch PKG installer: {result.stderr}")
                        
                        # Fallback: Try using osascript
                        logger.info("Trying alternative method with administrator privileges...")
                        applescript = f'''
                        do shell script "installer -pkg {package_path} -target /" with administrator privileges
                        '''
                        
                        result = subprocess.run(
                            ["osascript", "-e", applescript],
                            capture_output=True, text=True, timeout=300
                        )
                        
                        if result.returncode == 0:
                            logger.info("PKG installation completed successfully")
                            
                            # ✅ Auto-restart application if requested
                            if install_options.get('auto_restart', True):
                                logger.info("Installation complete, restarting application...")
                                self._restart_application()
                            
                            return True
                        else:
                            logger.error(f"PKG installation failed: {result.stderr}")
                            return False
                        
                except subprocess.TimeoutExpired:
                    logger.error("Installation timeout (10 minutes)")
                    return False
            else:
                # Interactive environment, use sudo directly
                logger.info(f"Executing: {' '.join(cmd)}")
                logger.info("You may be prompted for your administrator password...")
                
                result = subprocess.run(cmd, timeout=300)
                
                if result.returncode == 0:
                    logger.info("PKG installation completed successfully")
                    return True
                else:
                    logger.error(f"PKG installation failed with return code: {result.returncode}")
                    return False
                    
        except subprocess.TimeoutExpired:
            logger.error("Installation timeout")
            return False
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
            script_dir = Path(tempfile.gettempdir()) / "ecbot_restart"
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
"{app_executable}" &
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
        """恢复备份"""
        if not self.backup_dir or not self.backup_dir.exists():
            logger.error("No backup available to restore")
            return False
        
        try:
            # 获取当前应用路径
            if getattr(sys, 'frozen', False):
                app_path = Path(sys.executable).parent
            else:
                app_path = Path(__file__).parent.parent.parent
            
            logger.info(f"Restoring backup: {self.backup_dir} -> {app_path}")
            
            # 删除当前应用
            if app_path.exists():
                shutil.rmtree(app_path)
            
            # 恢复备份
            shutil.copytree(self.backup_dir, app_path)
            
            logger.info("Backup restored successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def cleanup_backup(self):
        """清理备份文件"""
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
                    else:
                        logger.error("Could not find .app bundle")
                        return
                        
                elif self.platform.startswith('win'):
                    # Windows: Restart exe
                    exe_path = sys.executable
                    logger.info(f"Restarting application: {exe_path}")
                    subprocess.Popen([exe_path])
                    
                else:
                    # Linux: Restart executable
                    exe_path = sys.executable
                    logger.info(f"Restarting application: {exe_path}")
                    subprocess.Popen([exe_path])
                
                # ✅ Exit current instance after a short delay
                logger.info("Exiting current instance in 2 seconds...")
                time.sleep(2)
                os._exit(0)
                
            else:
                # ✅ Development environment - don't restart
                logger.info("Running in development environment, skipping auto-restart")
                logger.info("Please manually restart the application to use the new version")
                
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")


# 全局安装管理器实例
installation_manager = InstallationManager()
