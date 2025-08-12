"""
PyInstaller hook for pywintypes
解决 pywintypes 在 PyInstaller 中的路径检查问题
"""

import sys
print("[HOOK] hook-pywintypes.py 正在执行...")

# 仅在 Windows 上启用该 hook，避免 macOS/Linux 打包时引入 win32 系列导致失败
if sys.platform.startswith('win'):
    from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

    # 收集 pywintypes 的所有内容
    datas, binaries, hiddenimports = collect_all('pywintypes')

    # 收集动态链接库
    pywintypes_libs = collect_dynamic_libs('pywintypes')
    binaries += pywintypes_libs

    # 添加 win32 相关模块
    win32_modules = [
        'win32api', 'win32con', 'win32file', 'win32pipe', 'win32process',
        'win32security', 'win32service', 'win32serviceutil', 'win32event',
        'win32evtlog', 'win32gui', 'win32clipboard', 'win32print',
    ]
    hiddenimports += win32_modules

    print(f"[HOOK] pywintypes hook 执行完成:")
    print(f"   - 隐藏导入: {len(hiddenimports)} 个模块")
    print(f"   - 数据文件: {len(datas)} 个文件")
    print(f"   - 二进制文件: {len(binaries)} 个文件")
else:
    # 非 Windows 平台，提供空的占位，避免 PyInstaller 报未定义变量
    datas, binaries, hiddenimports = [], [], []
    print("[HOOK] 非 Windows 平台，跳过 pywintypes 相关处理")
