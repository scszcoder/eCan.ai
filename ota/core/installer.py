#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot OTA安装器模块
处理安装包的安装和应用重启逻辑
"""

import os
import sys
import subprocess
import time
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from utils.logger_helper import logger_helper as logger
from .config import ota_config


class InstallationManager:
    """安装管理器"""
    
    def __init__(self):
        self.platform = sys.platform
        self.backup_dir = None
        
    def install_package(self, package_path: Path, install_options: Dict[str, Any] = None) -> bool:
        """安装更新包"""
        if not install_options:
            install_options = {}
            
        try:
            logger.info(f"Starting installation: {package_path}")
            
            # 创建备份
            if install_options.get('create_backup', True):
                if not self._create_backup():
                    logger.warning("Failed to create backup, continuing installation...")
            
            # 根据文件类型选择安装方法
            if package_path.suffix.lower() == '.exe':
                return self._install_exe(package_path, install_options)
            elif package_path.suffix.lower() == '.msi':
                return self._install_msi(package_path, install_options)
            elif package_path.suffix.lower() == '.dmg':
                return self._install_dmg(package_path, install_options)
            else:
                logger.error(f"Unsupported package format: {package_path.suffix}")
                return False
                
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False
    
    def _create_backup(self) -> bool:
        """创建当前应用的备份"""
        try:
            # 获取当前应用路径
            if getattr(sys, 'frozen', False):
                # 打包后的应用
                app_path = Path(sys.executable).parent
            else:
                # 开发环境
                app_path = Path(__file__).parent.parent.parent
            
            # 创建备份目录
            backup_root = Path(tempfile.gettempdir()) / "ecbot_backup"
            backup_root.mkdir(exist_ok=True)
            
            timestamp = int(time.time())
            self.backup_dir = backup_root / f"backup_{timestamp}"
            
            logger.info(f"Creating backup: {app_path} -> {self.backup_dir}")
            
            # 复制应用文件
            shutil.copytree(app_path, self.backup_dir, ignore=shutil.ignore_patterns('*.log', '__pycache__'))
            
            logger.info(f"Backup created successfully: {self.backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False
    
    def _install_exe(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """安装Windows EXE包"""
        try:
            logger.info(f"Installing Windows EXE: {package_path}")
            
            # 构建安装命令
            cmd = [str(package_path)]
            
            # 添加静默安装参数
            if install_options.get('silent', True):
                # 尝试常见的静默安装参数
                silent_args = ['/S', '/SILENT', '/VERYSILENT', '/quiet', '/q']
                cmd.extend(silent_args[:1])  # 使用第一个参数
            
            # 执行安装
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
        """安装Windows MSI包"""
        try:
            logger.info(f"Installing Windows MSI: {package_path}")
            
            # 构建msiexec命令
            cmd = ["msiexec", "/i", str(package_path)]
            
            if install_options.get('silent', True):
                cmd.extend(["/quiet", "/norestart"])
            
            # 执行安装
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
    
    def _install_dmg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
        """安装macOS DMG包"""
        try:
            logger.info(f"Installing macOS DMG: {package_path}")
            
            # 挂载DMG
            mount_result = subprocess.run(
                ["hdiutil", "attach", str(package_path), "-nobrowse", "-quiet"],
                capture_output=True, text=True
            )
            
            if mount_result.returncode != 0:
                logger.error(f"Failed to mount DMG: {mount_result.stderr}")
                return False
            
            try:
                # 查找挂载点
                mount_point = self._find_dmg_mount_point(package_path)
                if not mount_point:
                    logger.error("Could not find DMG mount point")
                    return False
                
                # 查找.app文件
                app_files = list(Path(mount_point).glob("*.app"))
                if not app_files:
                    logger.error("No .app file found in DMG")
                    return False
                
                # 复制到Applications目录
                target_dir = Path("/Applications")
                for app_file in app_files:
                    target_path = target_dir / app_file.name
                    
                    # 如果目标已存在，先删除
                    if target_path.exists():
                        shutil.rmtree(target_path)
                    
                    # 复制应用
                    shutil.copytree(app_file, target_path)
                    logger.info(f"Copied {app_file.name} to {target_path}")
                
                return True
                
            finally:
                # 卸载DMG
                subprocess.run(
                    ["hdiutil", "detach", mount_point or ""],
                    capture_output=True
                )
                
        except Exception as e:
            logger.error(f"DMG installation error: {e}")
            return False
    
    def _find_dmg_mount_point(self, dmg_path: Path) -> Optional[str]:
        """查找DMG挂载点"""
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
        """重启应用程序"""
        try:
            logger.info(f"Restarting application in {delay_seconds} seconds...")
            
            if getattr(sys, 'frozen', False):
                # 打包后的应用
                app_executable = sys.executable
            else:
                # 开发环境
                app_executable = sys.executable
                app_args = [sys.argv[0]]
            
            # 创建重启脚本
            restart_script = self._create_restart_script(app_executable, delay_seconds)
            
            if restart_script:
                # 执行重启脚本
                if self.platform.startswith('win'):
                    subprocess.Popen([restart_script], shell=True)
                else:
                    subprocess.Popen(['sh', restart_script])
                
                logger.info("Restart script launched")
                
                # 退出当前应用
                time.sleep(1)
                os._exit(0)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart application: {e}")
            return False
    
    def _create_restart_script(self, app_executable: str, delay_seconds: int) -> Optional[str]:
        """创建重启脚本"""
        try:
            script_dir = Path(tempfile.gettempdir()) / "ecbot_restart"
            script_dir.mkdir(exist_ok=True)
            
            if self.platform.startswith('win'):
                # Windows批处理脚本
                script_path = script_dir / "restart.bat"
                script_content = f"""@echo off
echo Waiting {delay_seconds} seconds before restart...
timeout /t {delay_seconds} /nobreak >nul
echo Restarting eCan...
start "" "{app_executable}"
del "%~f0"
"""
            else:
                # Unix shell脚本
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
            
            # 设置执行权限 (Unix)
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


# 全局安装管理器实例
installation_manager = InstallationManager()
