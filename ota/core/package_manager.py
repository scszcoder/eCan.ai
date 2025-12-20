"""
Update package manager
Handles downloading, verification and installation of update packages
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
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

import requests
from utils.logger_helper import logger_helper as logger
from ota.config.loader import ota_config

# Try to import cryptography library
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding, ed25519
    from cryptography.exceptions import InvalidSignature
    CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("cryptography library not available, digital signature verification will be limited")
    CRYPTO_AVAILABLE = False


class UpdatePackage:
    """Update package information"""
    
    def __init__(self, version: str, download_url: str, file_size: int, 
                 signature: str, description: str = "", alternate_url: str = None):
        self.version = version
        self.download_url = download_url
        self.alternate_url = alternate_url  # Accelerated/alternate download URL
        self.file_size = file_size
        self.signature = signature
        self.description = description
        self.download_path: Optional[Path] = None
        self.is_downloaded = False
        self.is_verified = False
    
    def __str__(self):
        return f"UpdatePackage(version={self.version}, size={self.file_size})"


class PackageManager:
    """Update package manager"""
    
    def __init__(self, download_dir: Optional[str] = None):
        self.download_dir = Path(download_dir) if download_dir else Path(tempfile.gettempdir()) / "ecan_updates"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.current_package: Optional[UpdatePackage] = None
        self._downloaded_files = []  # Track downloaded files
        
        logger.info(f"Package manager initialized with download dir: {self.download_dir}")
        
        # Clean up old downloaded packages on startup
        self._cleanup_old_packages()
    
    def download_package(self, package: UpdatePackage, progress_callback=None, cancel_check=None, max_retries=3) -> bool:
        """Download update package with automatic fallback to alternate URL
        
        Args:
            package: Update package to download
            progress_callback: Optional callback for progress updates
            cancel_check: Optional callable that returns True if download should be cancelled
            max_retries: Maximum number of retry attempts
        """
        # Try primary URL first, then alternate URL if available
        urls_to_try = []
        urls_to_try.append((package.download_url, "primary"))
        if package.alternate_url:
            urls_to_try.append((package.alternate_url, "alternate (accelerated)"))
            logger.info(f"Alternate URL available for fallback: {package.alternate_url}")
        
        logger.info(f"[DOWNLOAD] Starting download with {len(urls_to_try)} URL(s) to try")
        
        for url_index, (download_url, url_type) in enumerate(urls_to_try):
            logger.info(f"[DOWNLOAD] Trying {url_type} URL: {download_url}")
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"[DOWNLOAD] Downloading update package: {package.version} from {url_type} URL (attempt {attempt + 1}/{max_retries})")
                    
                    # Create download path
                    filename = self._get_filename_from_url(package.download_url)
                    download_path = self.download_dir / filename
                    
                    # If file already exists, try to delete it (with retry for locked files)
                    if download_path.exists():
                        max_delete_attempts = 3  # Reduced to 3 attempts
                        file_deleted = False
                        
                        for delete_attempt in range(max_delete_attempts):
                            try:
                                download_path.unlink()
                                logger.info(f"Deleted existing file: {download_path}")
                                file_deleted = True
                                break
                            except PermissionError as e:
                                if delete_attempt < max_delete_attempts - 1:
                                    wait_time = 1  # Fixed 1 second wait
                                    logger.warning(f"File is locked, waiting {wait_time}s before retry ({delete_attempt + 1}/{max_delete_attempts}): {e}")
                                    time.sleep(wait_time)
                                else:
                                    # If still locked after retries, use a different filename
                                    logger.warning(f"File is locked after {max_delete_attempts} attempts, using alternative filename")
                                    import uuid
                                    base_name = download_path.stem
                                    extension = download_path.suffix
                                    unique_id = str(uuid.uuid4())[:8]
                                    new_filename = f"{base_name}_{unique_id}{extension}"
                                    download_path = self.download_dir / new_filename
                                    logger.info(f"Using alternative download path: {download_path}")
                                    file_deleted = True  # Not deleted, but we have a new path
                                    break
                    
                    # Start download with aggressive timeout settings
                    logger.info(f"Initiating HTTP request to download URL...")
                    import socket
                    
                    # Use shorter timeouts to detect slow connections quickly
                    connect_timeout = 30  # 30s to establish connection
                    read_timeout = 15     # 15s between data chunks (aggressive!)
                    
                    try:
                        # Use simple requests.get with timeout tuple
                        response = requests.get(
                            download_url, 
                            stream=True, 
                            timeout=(connect_timeout, read_timeout)
                        )
                        response.raise_for_status()
                        logger.info(f"HTTP connection established (connect_timeout={connect_timeout}s, read_timeout={read_timeout}s)")
                    except requests.exceptions.Timeout as e:
                        logger.warning(f"Connection/read timeout after {connect_timeout}s/{read_timeout}s: {e}")
                        logger.warning(f"Switching to alternate URL if available...")
                        raise
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Request failed: {e}")
                        raise
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    logger.info(f"Download started: total size = {total_size / (1024*1024):.2f} MB")
                    
                    # Track download progress for logging
                    last_log_progress = -1
                    download_start_time = time.time()
                    chunk_count = 0
                    slow_download_timeout = read_timeout  # Use same timeout for slow download detection
                    # Thread-safe progress tracking
                    progress_lock = threading.Lock()
                    last_progress_size = 0
                    download_stalled = threading.Event()
                    
                    def monitor_progress():
                        """Background thread to monitor download progress"""
                        nonlocal last_progress_size
                        monitor_start = time.time()
                        logger.info(f"[MONITOR] Progress monitor started, will check every {read_timeout}s")
                        
                        # Minimum acceptable speed: 100 KB/s (about 1.5 MB per 15s)
                        min_bytes_per_interval = 100 * 1024 * read_timeout  # 100 KB/s
                        
                        while not download_stalled.is_set():
                            time.sleep(read_timeout)
                            
                            with progress_lock:
                                current_size = downloaded_size
                            
                            elapsed = time.time() - monitor_start
                            bytes_downloaded_this_interval = current_size - last_progress_size
                            
                            if current_size == last_progress_size:
                                # No progress in the last interval
                                logger.warning(f"[MONITOR] No progress detected after {read_timeout}s!")
                                logger.warning(f"[MONITOR] Downloaded: {current_size} bytes in {elapsed:.1f}s")
                                logger.warning(f"[MONITOR] Triggering download abort to switch URL...")
                                download_stalled.set()
                                # Close the response to trigger exception in iter_content
                                try:
                                    response.close()
                                except:
                                    pass
                                break
                            elif bytes_downloaded_this_interval < min_bytes_per_interval:
                                # Progress too slow
                                speed_kbps = bytes_downloaded_this_interval / (1024 * read_timeout)
                                logger.warning(f"[MONITOR] Download too slow: {speed_kbps:.1f} KB/s (minimum: 100 KB/s)")
                                logger.warning(f"[MONITOR] Downloaded {bytes_downloaded_this_interval} bytes in {read_timeout}s")
                                logger.warning(f"[MONITOR] Triggering download abort to switch to faster URL...")
                                download_stalled.set()
                                try:
                                    response.close()
                                except:
                                    pass
                                break
                            else:
                                speed_kbps = bytes_downloaded_this_interval / (1024 * read_timeout)
                                logger.info(f"[MONITOR] Progress OK: {current_size} bytes ({current_size/(1024*1024):.2f} MB, speed: {speed_kbps:.1f} KB/s)")
                                last_progress_size = current_size
                    
                    # Start progress monitor thread
                    monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
                    monitor_thread.start()
                    
                    with open(download_path, 'wb') as f:
                        try:
                            logger.info(f"[DOWNLOAD] Starting iter_content loop with background monitor...")
                            for chunk in response.iter_content(chunk_size=8192):
                                # Check if monitor detected stall
                                if download_stalled.is_set():
                                    logger.warning(f"[DOWNLOAD] Monitor detected stall, aborting download")
                                    raise requests.exceptions.Timeout("Download stalled: no progress detected by monitor")
                                
                                chunk_count += 1
                                current_time = time.time()
                                
                                # Check for cancellation
                                if cancel_check and cancel_check():
                                    logger.info("Download cancelled by user")
                                    # Stop monitor thread
                                    download_stalled.set()
                                    logger.info(f"[MONITOR] Stopped due to user cancellation")
                                    f.close()
                                    try:
                                        download_path.unlink()
                                        logger.info(f"Cleaned up partial download: {download_path}")
                                    except Exception as e:
                                        logger.warning(f"Failed to clean up partial download: {e}")
                                    return False
                                
                                # Check for slow download (0% progress after timeout)
                                if downloaded_size == 0:
                                    elapsed = current_time - download_start_time
                                    if elapsed > slow_download_timeout:
                                        logger.warning(f"Download too slow: 0% progress after {slow_download_timeout}s (received {chunk_count} chunks)")
                                        logger.warning(f"Switching to alternate URL if available...")
                                        f.close()
                                        try:
                                            download_path.unlink()
                                            logger.info(f"Cleaned up slow download: {download_path}")
                                        except Exception as e:
                                            logger.warning(f"Failed to clean up: {e}")
                                        raise requests.exceptions.Timeout(f"Download stalled: 0% progress after {slow_download_timeout}s")
                                
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    last_chunk_time = current_time
                                    if progress_callback and total_size > 0:
                                        progress = int((downloaded_size / total_size) * 100)
                                        progress_callback(progress)
                                        
                                        # Log every 10% progress
                                        if progress >= last_log_progress + 10:
                                            logger.info(f"Download progress: {progress}% ({downloaded_size / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB)")
                                            last_log_progress = progress
                        except socket.timeout:
                            logger.warning(f"Socket timeout after {slow_download_timeout}s - no data received")
                            logger.warning(f"Downloaded {downloaded_size} bytes ({chunk_count} chunks) before timeout")
                            logger.warning(f"Switching to alternate URL if available...")
                            f.close()
                            try:
                                download_path.unlink()
                                logger.info(f"Cleaned up timed-out download: {download_path}")
                            except Exception as e:
                                logger.warning(f"Failed to clean up: {e}")
                            raise requests.exceptions.Timeout(f"Socket timeout: no data for {slow_download_timeout}s")
                        finally:
                            # Stop the monitor thread
                            download_stalled.set()
                            logger.info(f"[MONITOR] Stopping progress monitor")
                    
                    package.download_path = download_path
                    package.is_downloaded = True
                    self._downloaded_files.append(download_path)  # Track downloaded files
                    
                    # Verify file size
                    if package.file_size > 0 and download_path.stat().st_size != package.file_size:
                        logger.error(f"File size mismatch: expected {package.file_size}, got {download_path.stat().st_size}")
                        if attempt < max_retries - 1:
                            logger.info("Retrying download...")
                            continue
                        # Try next URL if available
                        break
                    
                    # Set as current package for installation
                    self.current_package = package
                    
                    logger.info(f"Package downloaded successfully from {url_type} URL: {download_path}")
                    return True
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Network error during download from {url_type} URL (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.info(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    # Try next URL if available
                    logger.warning(f"All {max_retries} attempts failed for {url_type} URL")
                    break
                except IOError as e:
                    logger.error(f"File I/O error during download: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error during download from {url_type} URL: {e}")
                    if attempt < max_retries - 1:
                        continue
                    # Try next URL if available
                    break
                
        logger.error(f"Failed to download package after {max_retries} attempts")
        return False
    
    def verify_package(self, package: UpdatePackage, public_key_path: Optional[str] = None) -> bool:
        """Verify update package"""
        if not package.is_downloaded or not package.download_path:
            logger.error("Package not downloaded")
            return False
        
        try:
            logger.info(f"Verifying package: {package.version}")
            
            # 1. Verify file integrity (hash)
            file_hash = self._calculate_file_hash(package.download_path)
            logger.info(f"Package hash: {file_hash}")
            
            # 2. Basic hash/digital signature verification
            sig_required = ota_config.get('signature_required', True)
            if package.signature:
                if self._is_hash_signature(package.signature):
                    # Simple hash verification
                    if file_hash != package.signature:
                        logger.error(f"Hash verification failed: expected {package.signature}, got {file_hash}")
                        return False
                    logger.info("Hash verification successful")
                else:
                    # Digital signature verification (Ed25519/RSA-PSS)
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
            
            # 3. File format verification
            if not self._verify_package_format(package.download_path):
                logger.error("Package format verification failed")
                return False
            
            # 4. Malware scan (basic check)
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
        """Check if signature is a simple hash"""
        # MD5: 32 chars, SHA1: 40 chars, SHA256: 64 chars
        return len(signature) in [32, 40, 64] and all(c in '0123456789abcdefABCDEF' for c in signature)
    
    def _verify_digital_signature(self, file_path: Path, signature: str, public_key_path: Optional[str]) -> bool:
        """Verify digital signature"""
        try:
            # Check cryptography library availability
            if not CRYPTO_AVAILABLE:
                error_msg = "Cryptography library not available for signature verification"
                if ota_config.get('signature_required', True):
                    logger.error(f"{error_msg} (signature_required=true)")
                    return False
                logger.warning(f"{error_msg}, skipping verification")
                return True

            # Check public key file
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
            
            # Check signature format
            if not signature or len(signature.strip()) == 0:
                error_msg = "Empty or invalid signature"
                if ota_config.get('signature_required', True):
                    logger.error(f"{error_msg} (signature_required=true)")
                    return False
                logger.warning(f"{error_msg}, skipping verification")
                return True
            
            # Read public key
            with open(public_key_path, 'rb') as key_file:
                public_key = serialization.load_pem_public_key(key_file.read())
            
            # Read file content
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Decode signature (assume base64 encoded)
            import base64
            try:
                signature_bytes = base64.b64decode(signature)
            except Exception:
                # If not base64, try to use directly
                signature_bytes = signature.encode('utf-8')
            
            # Verify signature (support RSA-PSS and Ed25519)
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
                # Sparkle 2 edSignature uses Ed25519 to sign entire download file (Base64 encoded)
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
        """Verify package format"""
        try:
            if file_path.suffix == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    # Check ZIP file integrity
                    bad_file = zip_ref.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in ZIP: {bad_file}")
                        return False
                    
                    # Check dangerous file paths
                    for name in zip_ref.namelist():
                        if '..' in name or name.startswith('/'):
                            logger.error(f"Dangerous path in ZIP: {name}")
                            return False
                            
            elif file_path.suffix in ['.tar', '.gz', '.bz2']:
                with tarfile.open(file_path, 'r:*') as tar_ref:
                    # Check dangerous file paths
                    for member in tar_ref.getmembers():
                        if '..' in member.name or member.name.startswith('/'):
                            logger.error(f"Dangerous path in TAR: {member.name}")
                            return False
            
            return True
            
        except Exception as e:
            logger.error(f"Package format verification failed: {e}")
            return False
    
    def _basic_malware_scan(self, file_path: Path) -> bool:
        """Basic malware scan"""
        try:
            # Check if file size is reasonable
            file_size = file_path.stat().st_size
            # Use a conservative upper bound to avoid accidentally accepting huge binaries
            max_size = 1024 * 1024 * 1024  # 1G
            if file_size > max_size:
                logger.warning(f"Package size {file_size} exceeds maximum {max_size}")
                return False

            # Check file extension
            allowed_extensions = {'.zip', '.tar', '.gz', '.bz2', '.dmg', '.exe', '.msi', '.pkg'}
            if file_path.suffix not in allowed_extensions:
                logger.error(f"Disallowed file extension: {file_path.suffix}")
                return False

            # Basic security scan completed

            return True

        except Exception as e:
            logger.error(f"Malware scan failed: {e}")
            return False
    
    def install_package(self, package: UpdatePackage, install_dir: str) -> bool:
        """Install update package"""
        if not package.is_verified:
            logger.error("Package not verified")
            return False
        
        backup_path = None
        try:
            logger.info(f"Installing package: {package.version}")
            
            # Check install directory
            if not os.path.exists(install_dir):
                logger.error(f"Install directory does not exist: {install_dir}")
                return False
            
            # Create backup
            if self._should_backup(install_dir):
                backup_path = self._create_backup(install_dir)
                logger.info(f"Backup created: {backup_path}")
            
            # Extract and install
            success = self._extract_and_install(package.download_path, install_dir)
            
            if success:
                logger.info("Package installation successful")
                self.current_package = package
                return True
            else:
                # Restore backup
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
        """Clean up downloaded files"""
        try:
            # Clean up individual downloaded files
            for file_path in self._downloaded_files[:]:
                try:
                    if file_path.exists():
                        # If keeping current package, skip it
                        if keep_current and self.current_package and file_path == self.current_package.download_path:
                            continue
                        file_path.unlink()
                        logger.info(f"Cleaned up file: {file_path}")
                    self._downloaded_files.remove(file_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up file {file_path}: {e}")
            
            # Clean up empty directories
            if self.download_dir.exists():
                try:
                    # Only delete empty directories
                    if not any(self.download_dir.iterdir()):
                        self.download_dir.rmdir()
                        logger.info("Download directory cleaned up")
                except OSError:
                    # Directory not empty, this is normal
                    pass
                    
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def cleanup_old_files(self, max_age_days=7):
        """Clean up old files"""
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
        """Get filename from URL"""
        parsed = urlparse(url)
        return os.path.basename(parsed.path)
    
    def _calculate_file_hash(self, file_path: Path, algorithm='sha256') -> str:
        """Calculate file hash"""
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
        """Whether should create backup"""
        # Can decide based on configuration or file size
        return True
    
    def _create_backup(self, install_dir: str) -> Path:
        """Create backup"""
        backup_dir = self.download_dir / f"backup_{int(time.time())}"
        shutil.copytree(install_dir, backup_dir)
        return backup_dir
    
    def _restore_backup(self, backup_path: Path, install_dir: str):
        """Restore backup"""
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
        shutil.copytree(backup_path, install_dir)
    
    def _extract_and_install(self, package_path: Path, install_dir: str) -> bool:
        """Extract and install package; provides minimal placeholder installer support for .dmg/.exe/.msi in dev mode (disabled by default)."""
        try:
            # Dev mode placeholder installer path
            if package_path.suffix.lower() in ['.dmg', '.exe', '.msi']:
                if not ota_config.is_dev_mode() or not ota_config.get("dev_installer_enabled", False):
                    logger.error(f"Installer format not implemented yet: {package_path.suffix}")
                    return False
                return self._dev_install_installer(package_path)

            extract_dir = self.download_dir / "extract"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir()
            
            # Extract files
            if package_path.suffix == '.zip':
                with zipfile.ZipFile(package_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif package_path.suffix in ['.tar', '.gz', '.bz2']:
                with tarfile.open(package_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir)
            else:
                logger.error(f"Unsupported package format: {package_path.suffix}")
                return False
            
            # Find install script
            install_script = extract_dir / "install.py"
            if install_script.exists():
                # Execute install script
                result = subprocess.run([sys.executable, str(install_script), install_dir], 
                                     capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Install script failed: {result.stderr}")
                    return False
            else:
                # Copy files directly
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
        """Dev mode: minimal placeholder installer
        - macOS .dmg: hdiutil attach -> copy to target directory -> hdiutil detach
        - Windows .exe/.msi: direct call, silent mode controlled by config
        """
        try:
            suffix = package_path.suffix.lower()
            if suffix == '.dmg' and sys.platform == 'darwin':
                target_dir = Path(ota_config.get("dmg_target_dir", "/Applications"))
                # Mount dmg
                attach = subprocess.run(["hdiutil", "attach", str(package_path), "-nobrowse", "-quiet"], capture_output=True, text=True)
                if attach.returncode != 0:
                    logger.error(f"Failed to attach dmg: {attach.stderr}")
                    return False
                # Find mount point (simple assumption: first Volume)
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
                    # Copy .app to target directory (if exists)
                    apps = [p for p in Path(mount_point).glob('*.app')]
                    if not apps:
                        logger.error("No .app found in dmg")
                        return False
                    for app in apps:
                        subprocess.run(["cp", "-R", str(app), str(target_dir)], check=False)
                finally:
                    # Unmount dmg
                    subprocess.run(["hdiutil", "detach", mount_point or ""], capture_output=True)
                return True
            elif suffix in ('.exe', '.msi') and sys.platform.startswith('win'):
                quiet = ota_config.get("dev_installer_quiet", True)
                args = [str(package_path)]
                if quiet and suffix == '.msi':
                    args = ["msiexec", "/i", str(package_path), "/quiet"]
                elif quiet and suffix == '.exe':
                    # Common silent parameters; different installers may vary, placeholder only
                    args.append("/quiet")
                result = subprocess.run(args)
                return result.returncode == 0
            else:
                logger.error(f"Dev installer not supported for {suffix} on {sys.platform}")
                return False
        except Exception as e:
            logger.error(f"Dev installer failed: {e}")
            return False
    
    def _cleanup_old_packages(self, max_age_days: int = 7):
        """Clean up old downloaded packages on startup
        
        Args:
            max_age_days: Delete packages older than this many days (default: 7)
        """
        try:
            if not self.download_dir.exists():
                return
            
            import time
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            cleaned_count = 0
            cleaned_size = 0
            
            # Iterate through all files in download directory
            for file_path in self.download_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                try:
                    # Get file age
                    file_age = current_time - file_path.stat().st_mtime
                    
                    # Delete if older than max_age_days
                    if file_age > max_age_seconds:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        cleaned_count += 1
                        cleaned_size += file_size
                        logger.info(f"[Cleanup] Deleted old package: {file_path.name} (age: {file_age / 86400:.1f} days)")
                    
                except Exception as e:
                    logger.warning(f"[Cleanup] Failed to delete {file_path.name}: {e}")
            
            if cleaned_count > 0:
                size_mb = cleaned_size / (1024 * 1024)
                logger.info(f"[Cleanup] Cleaned up {cleaned_count} old package(s), freed {size_mb:.2f} MB")
            else:
                logger.info("[Cleanup] No old packages to clean up")
                
        except Exception as e:
            logger.error(f"[Cleanup] Failed to clean up old packages: {e}")


# Global package manager instance
package_manager = PackageManager() 