import sys
import os
import tempfile
import getpass
import time
import hashlib

def install_single_instance():
    """
    Cross-platform single instance protection for Windows and macOS/Linux.
    Uses username and executable path to distinguish between different users and versions.
    Automatically cleans up locks when process exits.
    Enhanced race condition protection.
    """
    username = getpass.getuser()

    # Use executable path to create unique identifier, avoiding conflicts between different versions
    executable_path = sys.executable
    if hasattr(sys, 'frozen'):
        # PyInstaller environment, use actual executable file path
        executable_path = sys.argv[0]

    # Create unique identifier based on username and executable path
    unique_id = hashlib.md5(f"{username}_{executable_path}".encode()).hexdigest()[:16]
    lock_file_path = os.path.join(tempfile.gettempdir(), f'ecbot_main_{unique_id}.lock')

    print(f"[SINGLE_INSTANCE] Using lock file: {lock_file_path}")
    print(f"[SINGLE_INSTANCE] Executable: {executable_path}")
    print(f"[SINGLE_INSTANCE] User: {username}")

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
                print(f"[SINGLE_INSTANCE] Successfully acquired lock on attempt {attempt + 1}")
                return

            if attempt < max_retries - 1:
                print(f"[SINGLE_INSTANCE] Attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # exponential backoff
        except Exception as e:
            print(f"[SINGLE_INSTANCE] Attempt {attempt + 1} error: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2

    print("[SINGLE_INSTANCE] ECBot main process already running, exiting...")
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