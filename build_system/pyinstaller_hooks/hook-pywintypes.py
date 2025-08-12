"""
PyInstaller hook for pywintypes
解决 pywintypes 在 PyInstaller 中的路径检查问题
"""

print("[HOOK] hook-pywintypes.py 正在执行...")

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# 收集 pywintypes 的所有内容
datas, binaries, hiddenimports = collect_all('pywintypes')

# 收集动态链接库
pywintypes_libs = collect_dynamic_libs('pywintypes')
binaries += pywintypes_libs

# 添加 win32 相关模块
win32_modules = [
    'win32api',
    'win32con', 
    'win32file',
    'win32pipe',
    'win32process',
    'win32security',
    'win32service',
    'win32serviceutil',
    'win32event',
    'win32evtlog',
    'win32gui',
    'win32clipboard',
    'win32print',
]

hiddenimports += win32_modules

print(f"[HOOK] pywintypes hook 执行完成:")
print(f"   - 隐藏导入: {len(hiddenimports)} 个模块")
print(f"   - 数据文件: {len(datas)} 个文件")
print(f"   - 二进制文件: {len(binaries)} 个文件")
