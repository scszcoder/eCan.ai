import sys
import os
import tempfile
import getpass

def install_single_instance():
    """
    跨平台单实例保护，支持 Windows 和 macOS/Linux。
    用用户名区分，防止多用户冲突。
    进程退出自动清理锁。
    """
    username = getpass.getuser()
    lock_file_path = os.path.join(tempfile.gettempdir(), f'ecbot_main_{username}.lock')
    if sys.platform == 'win32':
        import msvcrt
        try:
            lock_file = open(lock_file_path, 'w')
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                print("ECBot main process already running, exiting...")
                sys.exit(0)
        except Exception as e:
            print(f"Lock file error: {e}")
            sys.exit(0)
        import atexit
        def cleanup_lock():
            try:
                lock_file.close()
                os.remove(lock_file_path)
            except Exception:
                pass
        atexit.register(cleanup_lock)
    else:
        import fcntl
        try:
            lock_file = open(lock_file_path, 'w')
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            print("ECBot main process already running, exiting...")
            sys.exit(0)
        import atexit
        def cleanup_lock():
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                os.unlink(lock_file_path)
            except Exception:
                pass
        atexit.register(cleanup_lock)