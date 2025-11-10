import sys
import os
import tempfile
import getpass
import time
import hashlib

def _is_process_running(pid):
    """Check if a process with given PID is currently running (cross-platform, no console subprocess)."""
    if not pid:
        return False

    try:
        pid = int(pid)
        # Use psutil universally to avoid spawning console tools like tasklist/ps
        try:
            import psutil  # lazy import
        except Exception:
            psutil = None

        if psutil is not None:
            if not psutil.pid_exists(pid):
                return False
            try:
                p = psutil.Process(pid)
                # is_running() may be True briefly for zombies; filter them out when possible
                status = getattr(psutil, 'STATUS_ZOMBIE', 'zombie')
                return p.is_running() and getattr(p, 'status', lambda: None)() != status
            except psutil.NoSuchProcess:
                return False
            except Exception:
                # Fallback minimal check when detailed query fails
                return True
        else:
            # Last-resort fallback without creating new processes
            if sys.platform == 'win32':
                # On Windows without psutil, use OpenProcess check via ctypes (no window)
                try:
                    import ctypes
                    from ctypes import wintypes
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                    OpenProcess = kernel32.OpenProcess
                    OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    OpenProcess.restype = wintypes.HANDLE
                    CloseHandle = kernel32.CloseHandle
                    CloseHandle.argtypes = [wintypes.HANDLE]
                    CloseHandle.restype = wintypes.BOOL
                    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    if h:
                        CloseHandle(h)
                        return True
                    return False
                except Exception:
                    return False
            else:
                # Unix-like: signal 0
                os.kill(pid, 0)
                return True
    except (OSError, ProcessLookupError, ValueError):
        return False
    except Exception:
        return False

def _clean_stale_lock(lock_file_path):
    """Clean up stale lock file if the owning process is no longer running"""
    try:
        if not os.path.exists(lock_file_path):
            return True
        
        # Read lock file to get PID
        with open(lock_file_path, 'r') as f:
            content = f.read()
            
        # Parse PID from lock file
        pid = None
        for line in content.split('\n'):
            if line.startswith('pid:'):
                pid = line.split(':', 1)[1].strip()
                break
        
        # Check if the process is still running
        if not _is_process_running(pid):
            print(f"[SINGLE_INSTANCE] Found stale lock file (PID {pid} not running), cleaning up...")
            try:
                os.remove(lock_file_path)
                print("[SINGLE_INSTANCE] Stale lock file removed successfully")
                return True
            except Exception as e:
                print(f"[SINGLE_INSTANCE] Failed to remove stale lock: {e}")
                return False
        else:
            print(f"[SINGLE_INSTANCE] Lock file is valid (PID {pid} is running)")
            return False
            
    except Exception as e:
        print(f"[SINGLE_INSTANCE] Error checking stale lock: {e}")
        # If we can't determine, assume lock is valid (safer)
        return False

def install_single_instance():
    """
    Cross-platform single instance protection for Windows and macOS/Linux.
    Uses username and a fixed per-user AppID to distinguish between different users.
    Automatically cleans up locks when process exits.
    Enhanced with stale lock detection and PID validation.
    """
    username = getpass.getuser()

    # Windows: add a global named mutex to prevent multiple instances across sessions/users
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes

            mutex_name = "Global\\eCan.AI.SingleInstance"
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            CreateMutexW = kernel32.CreateMutexW
            CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            CreateMutexW.restype = wintypes.HANDLE

            handle = CreateMutexW(None, False, mutex_name)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())

            # ERROR_ALREADY_EXISTS = 183
            ERROR_ALREADY_EXISTS = 183
            last_error = ctypes.get_last_error()
            if last_error == ERROR_ALREADY_EXISTS:
                print("[SINGLE_INSTANCE] [ERROR] Another instance detected by Global mutex, exiting...")
                try:
                    # Close the handle we just opened
                    kernel32.CloseHandle(handle)
                except Exception:
                    pass
                sys.exit(0)

            # Keep mutex handle globally and ensure it's released on exit
            globals()['_ecan_global_mutex_handle'] = handle
            import atexit
            def _release_mutex():
                try:
                    h = globals().get('_ecan_global_mutex_handle')
                    if h:
                        kernel32.CloseHandle(h)
                        globals().pop('_ecan_global_mutex_handle', None)
                except Exception:
                    pass
            atexit.register(_release_mutex)
            print(f"[SINGLE_INSTANCE] Global mutex acquired: {mutex_name}")
        except Exception as e:
            print(f"[SINGLE_INSTANCE] Global mutex setup failed (continuing with file lock): {e}")

    # Create a fixed per-user unique identifier (same for dev/frozen and different paths)
    app_id = 'eCan.AI'
    unique_id = hashlib.md5(f"{username}_{app_id}".encode()).hexdigest()[:16]
    lock_file_path = os.path.join(tempfile.gettempdir(), f'ecbot_main_{unique_id}.lock')

    print(f"[SINGLE_INSTANCE] Using lock file: {lock_file_path}")
    print(f"[SINGLE_INSTANCE] User: {username}")

    # First, try to clean up stale lock files
    _clean_stale_lock(lock_file_path)

    # Add retry mechanism to handle race conditions
    max_retries = 3
    retry_delay = 0.1  # 100ms

    for attempt in range(max_retries):
        try:
            if sys.platform == 'win32':
                success = _install_single_instance_windows(lock_file_path, attempt)
            else:
                success = _install_single_instance_unix(lock_file_path, attempt)

            if success:
                print(f"[SINGLE_INSTANCE] [OK] Successfully acquired lock on attempt {attempt + 1}")
                return

            if attempt < max_retries - 1:
                print(f"[SINGLE_INSTANCE] Attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # exponential backoff
                # Try cleaning stale lock again before retry
                _clean_stale_lock(lock_file_path)
        except Exception as e:
            print(f"[SINGLE_INSTANCE] Attempt {attempt + 1} error: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2

    # Write error to a log file for debugging packaged EXE
    try:
        log_path = os.path.join(tempfile.gettempdir(), f'ecbot_startup_error_{unique_id}.log')
        with open(log_path, 'w') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ECBot startup failed\n")
            f.write(f"Reason: Another instance is already running\n")
            f.write(f"Lock file: {lock_file_path}\n")
            f.write(f"User: {username}\n")
            f.write(f"Executable: {executable_path}\n")
            if os.path.exists(lock_file_path):
                f.write(f"\nLock file contents:\n")
                with open(lock_file_path, 'r') as lf:
                    f.write(lf.read())
        print(f"[SINGLE_INSTANCE] Error log written to: {log_path}")
    except Exception:
        pass
    
    print("[SINGLE_INSTANCE] [ERROR] ECBot main process already running, exiting...")
    print(f"[SINGLE_INSTANCE] If you believe this is an error, please delete: {lock_file_path}")
    sys.exit(0)

def _install_single_instance_windows(lock_file_path, attempt):
    """Windows platform single instance protection implementation"""
    import msvcrt
    try:
        # Try to create and lock file
        lock_file = open(lock_file_path, 'w')
        lock_file.write(f"pid:{os.getpid()}\ntime:{time.time()}\nattempt:{attempt}\n")
        lock_file.flush()

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            lock_file.close()
            return False

        # Successfully acquired lock, set up cleanup function
        import atexit

        # Keep global reference to lock file to prevent garbage collection
        globals()['_lock_file_handle'] = lock_file

        def cleanup_lock():
            try:
                if '_lock_file_handle' in globals():
                    handle = globals()['_lock_file_handle']
                    try:
                        # Check if file handle is still valid
                        if not handle.closed:
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                            handle.close()
                    except (OSError, ValueError) as e:
                        # File handle may be invalid, ignore unlock errors
                        print(f"[SINGLE_INSTANCE] Lock handle cleanup warning: {e}")
                    finally:
                        del globals()['_lock_file_handle']

                # Try to delete lock file
                if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)
                print("[SINGLE_INSTANCE] Lock file cleaned up")
            except Exception as e:
                print(f"[SINGLE_INSTANCE] Lock cleanup error: {e}")
        atexit.register(cleanup_lock)
        return True

    except Exception as e:
        print(f"[SINGLE_INSTANCE] Windows lock error: {e}")
        return False

def _install_single_instance_unix(lock_file_path, attempt):
    """Unix/Linux/macOS platform single instance protection implementation"""
    import fcntl
    try:
        # Try to create and lock file
        lock_file = open(lock_file_path, 'w')
        lock_file.write(f"pid:{os.getpid()}\ntime:{time.time()}\nattempt:{attempt}\n")
        lock_file.flush()

        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError) as e:
            lock_file.close()
            return False

        # Successfully acquired lock, set up cleanup function
        import atexit

        # Keep global reference to lock file to prevent garbage collection
        globals()['_lock_file_handle'] = lock_file

        def cleanup_lock():
            try:
                if '_lock_file_handle' in globals():
                    handle = globals()['_lock_file_handle']
                    try:
                        # Check if file handle is still valid
                        if not handle.closed:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                            handle.close()
                    except (OSError, ValueError) as e:
                        # File handle may be invalid, ignore unlock errors
                        print(f"[SINGLE_INSTANCE] Lock handle cleanup warning: {e}")
                    finally:
                        del globals()['_lock_file_handle']

                # Try to delete lock file
                if os.path.exists(lock_file_path):
                    os.unlink(lock_file_path)
                print("[SINGLE_INSTANCE] Lock file cleaned up")
            except Exception as e:
                print(f"[SINGLE_INSTANCE] Lock cleanup error: {e}")
        atexit.register(cleanup_lock)
        return True

    except Exception as e:
        print(f"[SINGLE_INSTANCE] Unix lock error: {e}")
        return False