"""
更新包管理器
处理下载、验证和安装更新包
"""

import os
import hashlib
import tempfile
import zipfile
import tarfile
import shutil
import subprocess
import time
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

import requests
from utils.logger_helper import logger_helper as logger
from .config import ota_config

# 尝试导入加密库
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding, ed25519
    from cryptography.exceptions import InvalidSignature
    CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("cryptography library not available, digital signature verification will be limited")
    CRYPTO_AVAILABLE = False


class UpdatePackage:
    """更新包信息"""
    
    def __init__(self, version: str, download_url: str, file_size: int, 
                 signature: str, description: str = ""):
        self.version = version
        self.download_url = download_url
        self.file_size = file_size
        self.signature = signature
        self.description = description
        self.download_path: Optional[Path] = None
        self.is_downloaded = False
        self.is_verified = False
    
    def __str__(self):
        return f"UpdatePackage(version={self.version}, size={self.file_size})"


class PackageManager:
    """更新包管理器"""
    
    def __init__(self, download_dir: Optional[str] = None):
        self.download_dir = Path(download_dir) if download_dir else Path(tempfile.gettempdir()) / "ecbot_updates"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.current_package: Optional[UpdatePackage] = None
        self._downloaded_files = []  # 跟踪下载的文件
        
        logger.info(f"Package manager initialized with download dir: {self.download_dir}")
    
    def download_package(self, package: UpdatePackage, progress_callback=None, max_retries=3) -> bool:
        """下载更新包"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Downloading update package: {package.version} (attempt {attempt + 1}/{max_retries})")
                
                # 创建下载路径
                filename = self._get_filename_from_url(package.download_url)
                download_path = self.download_dir / filename
                
                # 如果文件已存在，删除它
                if download_path.exists():
                    download_path.unlink()
                
                # 开始下载
                response = requests.get(package.download_url, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                with open(download_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            if progress_callback and total_size > 0:
                                progress = int((downloaded_size / total_size) * 100)
                                progress_callback(progress)
                
                package.download_path = download_path
                package.is_downloaded = True
                self._downloaded_files.append(download_path)  # 跟踪下载的文件
                
                # 验证文件大小
                if package.file_size > 0 and download_path.stat().st_size != package.file_size:
                    logger.error(f"File size mismatch: expected {package.file_size}, got {download_path.stat().st_size}")
                    if attempt < max_retries - 1:
                        logger.info("Retrying download...")
                        continue
                    return False
                
                logger.info(f"Package downloaded successfully: {download_path}")
                return True
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error during download (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
            except IOError as e:
                logger.error(f"File I/O error during download: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error during download: {e}")
                if attempt < max_retries - 1:
                    continue
                
        logger.error(f"Failed to download package after {max_retries} attempts")
        return False
    
    def verify_package(self, package: UpdatePackage, public_key_path: Optional[str] = None) -> bool:
        """验证更新包"""
        if not package.is_downloaded or not package.download_path:
            logger.error("Package not downloaded")
            return False
        
        try:
            logger.info(f"Verifying package: {package.version}")
            
            # 1. 验证文件完整性（哈希）
            file_hash = self._calculate_file_hash(package.download_path)
            logger.info(f"Package hash: {file_hash}")
            
            # 2. 基本哈希/数字签名验证
            sig_required = ota_config.get('signature_required', True)
            if package.signature:
                if self._is_hash_signature(package.signature):
                    # 简单哈希验证
                    if file_hash != package.signature:
                        logger.error(f"Hash verification failed: expected {package.signature}, got {file_hash}")
                        return False
                    logger.info("Hash verification successful")
                else:
                    # 数字签名验证（Ed25519/RSA-PSS）
                    if not public_key_path:
                        public_key_path = ota_config.get_public_key_path()
                    ok = self._verify_digital_signature(package.download_path, package.signature, public_key_path)
                    if not ok:
                        logger.error("Digital signature verification failed")
                        return False
                    logger.info("Digital signature verification successful")
            else:
                if ota_config.get('signature_verification', True) and sig_required:
                    logger.error("Missing signature while signature_required=true")
                    return False
            
            # 3. 文件格式验证
            if not self._verify_package_format(package.download_path):
                logger.error("Package format verification failed")
                return False
            
            # 4. 恶意软件扫描（基础检查）
            if not self._basic_malware_scan(package.download_path):
                logger.error("Package failed security scan")
                return False
            
            package.is_verified = True
            logger.info("Package verification successful")
            return True
            
        except Exception as e:
            logger.error(f"Package verification failed: {e}")
            return False
    
    def _is_hash_signature(self, signature: str) -> bool:
        """判断签名是否为简单哈希"""
        # MD5: 32字符, SHA1: 40字符, SHA256: 64字符
        return len(signature) in [32, 40, 64] and all(c in '0123456789abcdefABCDEF' for c in signature)
    
    def _verify_digital_signature(self, file_path: Path, signature: str, public_key_path: Optional[str]) -> bool:
        """验证数字签名"""
        try:
            # 检查加密库可用性
            if not CRYPTO_AVAILABLE:
                error_msg = "Cryptography library not available for signature verification"
                if ota_config.get('signature_required', True):
                    logger.error(f"{error_msg} (signature_required=true)")
                    return False
                logger.warning(f"{error_msg}, skipping verification")
                return True

            # 检查公钥文件
            if not public_key_path:
                error_msg = "Public key path not provided"
                if ota_config.get('signature_required', True):
                    logger.error(f"{error_msg} (signature_required=true)")
                    return False
                logger.warning(f"{error_msg}, skipping verification")
                return True
            
            if not os.path.exists(public_key_path):
                error_msg = f"Public key file not found: {public_key_path}"
                if ota_config.get('signature_required', True):
                    logger.error(f"{error_msg} (signature_required=true)")
                    return False
                logger.warning(f"{error_msg}, skipping verification")
                return True
            
            # 检查签名格式
            if not signature or len(signature.strip()) == 0:
                error_msg = "Empty or invalid signature"
                if ota_config.get('signature_required', True):
                    logger.error(f"{error_msg} (signature_required=true)")
                    return False
                logger.warning(f"{error_msg}, skipping verification")
                return True
            
            # 读取公钥
            with open(public_key_path, 'rb') as key_file:
                public_key = serialization.load_pem_public_key(key_file.read())
            
            # 读取文件内容
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # 解码签名（假设是base64编码）
            import base64
            try:
                signature_bytes = base64.b64decode(signature)
            except Exception:
                # 如果不是base64，尝试直接使用
                signature_bytes = signature.encode('utf-8')
            
            # 验证签名（支持 RSA-PSS 与 Ed25519）
            if isinstance(public_key, rsa.RSAPublicKey):
                logger.info("Verifying RSA-PSS signature")
                public_key.verify(
                    signature_bytes,
                    file_data,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
            elif isinstance(public_key, ed25519.Ed25519PublicKey):
                logger.info("Verifying Ed25519 signature")
                # Sparkle 2 edSignature 使用 Ed25519 对整个下载文件签名（Base64 编码）
                public_key.verify(signature_bytes, file_data)
            else:
                key_type = type(public_key).__name__
                logger.error(f"Unsupported public key type: {key_type}")
                return False
            
            logger.info("Digital signature verification successful")
            return True
            
        except InvalidSignature as e:
            logger.error(f"Digital signature verification failed: Invalid signature - {e}")
            return False
        except ValueError as e:
            logger.error(f"Digital signature verification failed: Invalid key or signature format - {e}")
            return False
        except Exception as e:
            logger.error(f"Digital signature verification error: {type(e).__name__}: {e}")
            return False
    
    def _verify_package_format(self, file_path: Path) -> bool:
        """验证包格式"""
        try:
            if file_path.suffix == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    # 检查ZIP文件完整性
                    bad_file = zip_ref.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in ZIP: {bad_file}")
                        return False
                    
                    # 检查危险文件路径
                    for name in zip_ref.namelist():
                        if '..' in name or name.startswith('/'):
                            logger.error(f"Dangerous path in ZIP: {name}")
                            return False
                            
            elif file_path.suffix in ['.tar', '.gz', '.bz2']:
                with tarfile.open(file_path, 'r:*') as tar_ref:
                    # 检查危险文件路径
                    for member in tar_ref.getmembers():
                        if '..' in member.name or member.name.startswith('/'):
                            logger.error(f"Dangerous path in TAR: {member.name}")
                            return False
            
            return True
            
        except Exception as e:
            logger.error(f"Package format verification failed: {e}")
            return False
    
    def _basic_malware_scan(self, file_path: Path) -> bool:
        """基础恶意软件扫描"""
        try:
            # 检查文件大小是否合理
            file_size = file_path.stat().st_size
            max_size = 500 * 1024 * 1024  # 500MB
            if file_size > max_size:
                logger.warning(f"Package size {file_size} exceeds maximum {max_size}")
                return False
            
            # 检查文件扩展名
            allowed_extensions = {'.zip', '.tar', '.gz', '.bz2', '.dmg', '.exe', '.msi'}
            if file_path.suffix not in allowed_extensions:
                logger.error(f"Disallowed file extension: {file_path.suffix}")
                return False
            
            # TODO: 可以集成第三方杀毒引擎
            # 例如 ClamAV 或其他安全扫描工具
            
            return True
            
        except Exception as e:
            logger.error(f"Malware scan failed: {e}")
            return False
    
    def install_package(self, package: UpdatePackage, install_dir: str) -> bool:
        """安装更新包"""
        if not package.is_verified:
            logger.error("Package not verified")
            return False
        
        backup_path = None
        try:
            logger.info(f"Installing package: {package.version}")
            
            # 检查安装目录
            if not os.path.exists(install_dir):
                logger.error(f"Install directory does not exist: {install_dir}")
                return False
            
            # 创建备份
            if self._should_backup(install_dir):
                backup_path = self._create_backup(install_dir)
                logger.info(f"Backup created: {backup_path}")
            
            # 解压并安装
            success = self._extract_and_install(package.download_path, install_dir)
            
            if success:
                logger.info("Package installation successful")
                self.current_package = package
                return True
            else:
                # 恢复备份
                if backup_path and backup_path.exists():
                    self._restore_backup(backup_path, install_dir)
                    logger.info("Backup restored after failed installation")
                return False
                
        except PermissionError as e:
            logger.error(f"Permission denied during installation: {e}")
            if backup_path and backup_path.exists():
                self._restore_backup(backup_path, install_dir)
            return False
        except OSError as e:
            logger.error(f"OS error during installation: {e}")
            if backup_path and backup_path.exists():
                self._restore_backup(backup_path, install_dir)
            return False
        except Exception as e:
            logger.error(f"Unexpected error during installation: {e}")
            if backup_path and backup_path.exists():
                self._restore_backup(backup_path, install_dir)
            return False
    
    def cleanup(self, keep_current=False):
        """清理下载的文件"""
        try:
            # 清理单个下载的文件
            for file_path in self._downloaded_files[:]:
                try:
                    if file_path.exists():
                        # 如果要保留当前包，跳过它
                        if keep_current and self.current_package and file_path == self.current_package.download_path:
                            continue
                        file_path.unlink()
                        logger.info(f"Cleaned up file: {file_path}")
                    self._downloaded_files.remove(file_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up file {file_path}: {e}")
            
            # 清理空目录
            if self.download_dir.exists():
                try:
                    # 只删除空目录
                    if not any(self.download_dir.iterdir()):
                        self.download_dir.rmdir()
                        logger.info("Download directory cleaned up")
                except OSError:
                    # 目录不为空，这是正常的
                    pass
                    
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def cleanup_old_files(self, max_age_days=7):
        """清理旧文件"""
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 3600
            
            for file_path in self.download_dir.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        try:
                            file_path.unlink()
                            logger.info(f"Cleaned up old file: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up old file {file_path}: {e}")
                            
        except Exception as e:
            logger.error(f"Old file cleanup failed: {e}")
    
    def _get_filename_from_url(self, url: str) -> str:
        """从URL获取文件名"""
        parsed = urlparse(url)
        return os.path.basename(parsed.path)
    
    def _calculate_file_hash(self, file_path: Path, algorithm='sha256') -> str:
        """计算文件哈希"""
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha1':
            hasher = hashlib.sha1()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _should_backup(self, install_dir: str) -> bool:
        """是否应该创建备份"""
        # 这里可以根据配置或文件大小决定
        return True
    
    def _create_backup(self, install_dir: str) -> Path:
        """创建备份"""
        backup_dir = self.download_dir / f"backup_{int(time.time())}"
        shutil.copytree(install_dir, backup_dir)
        return backup_dir
    
    def _restore_backup(self, backup_path: Path, install_dir: str):
        """恢复备份"""
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
        shutil.copytree(backup_path, install_dir)
    
    def _extract_and_install(self, package_path: Path, install_dir: str) -> bool:
        """解压并安装包；在开发模式下提供最小占位安装器支持 .dmg/.exe/.msi（默认关闭）。"""
        try:
            # 开发模式占位安装器路径
            from .config import ota_config
            if package_path.suffix.lower() in ['.dmg', '.exe', '.msi']:
                if not ota_config.is_dev_mode() or not ota_config.get("dev_installer_enabled", False):
                    logger.error(f"Installer format not implemented yet: {package_path.suffix}")
                    return False
                return self._dev_install_installer(package_path)

            extract_dir = self.download_dir / "extract"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir()
            
            # 解压文件
            if package_path.suffix == '.zip':
                with zipfile.ZipFile(package_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif package_path.suffix in ['.tar', '.gz', '.bz2']:
                with tarfile.open(package_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir)
            else:
                logger.error(f"Unsupported package format: {package_path.suffix}")
                return False
            
            # 查找安装脚本
            install_script = extract_dir / "install.py"
            if install_script.exists():
                # 执行安装脚本
                result = subprocess.run([sys.executable, str(install_script), install_dir], 
                                     capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Install script failed: {result.stderr}")
                    return False
            else:
                # 直接复制文件
                for item in extract_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, Path(install_dir) / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, Path(install_dir) / item.name)
            
            return True
            
        except Exception as e:
            logger.error(f"Extract and install failed: {e}")
            return False

    def _dev_install_installer(self, package_path: Path) -> bool:
        """开发模式：最小占位安装器
        - macOS .dmg：hdiutil attach -> 复制到目标目录 -> hdiutil detach
        - Windows .exe/.msi：直接调用，是否静默由配置控制
        """
        try:
            from .config import ota_config
            suffix = package_path.suffix.lower()
            if suffix == '.dmg' and sys.platform == 'darwin':
                target_dir = Path(ota_config.get("dmg_target_dir", "/Applications"))
                # 挂载 dmg
                attach = subprocess.run(["hdiutil", "attach", str(package_path), "-nobrowse", "-quiet"], capture_output=True, text=True)
                if attach.returncode != 0:
                    logger.error(f"Failed to attach dmg: {attach.stderr}")
                    return False
                # 查找挂载点（简单假设第一个Volume）
                try:
                    import plistlib
                    info = subprocess.run(["hdiutil", "info", "-plist"], capture_output=True)
                    plist = plistlib.loads(info.stdout)
                    mount_points = []
                    for img in plist.get('images', []):
                        for ent in img.get('system-entities', []):
                            mp = ent.get('mount-point')
                            if mp:
                                mount_points.append(mp)
                    mount_point = mount_points[-1] if mount_points else None
                    if not mount_point:
                        logger.error("Mount point not found for dmg")
                        return False
                    # 复制 .app 到目标目录（如果存在）
                    apps = [p for p in Path(mount_point).glob('*.app')]
                    if not apps:
                        logger.error("No .app found in dmg")
                        return False
                    for app in apps:
                        subprocess.run(["cp", "-R", str(app), str(target_dir)], check=False)
                finally:
                    # 卸载 dmg
                    subprocess.run(["hdiutil", "detach", mount_point or ""], capture_output=True)
                return True
            elif suffix in ('.exe', '.msi') and sys.platform.startswith('win'):
                quiet = ota_config.get("dev_installer_quiet", True)
                args = [str(package_path)]
                if quiet and suffix == '.msi':
                    args = ["msiexec", "/i", str(package_path), "/quiet"]
                elif quiet and suffix == '.exe':
                    # 常见静默参数；不同安装器可能不一致，仅作占位
                    args.append("/quiet")
                result = subprocess.run(args)
                return result.returncode == 0
            else:
                logger.error(f"Dev installer not supported for {suffix} on {sys.platform}")
                return False
        except Exception as e:
            logger.error(f"Dev installer failed: {e}")
            return False


# 全局包管理器实例
package_manager = PackageManager() 