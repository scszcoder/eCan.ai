"""
PyInstaller hook for MCP library on macOS
解决 MCP 库在 macOS PyInstaller 中的特定问题
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

print("[HOOK] hook-mcp-macos.py 正在执行...")

# 只在 macOS 上应用
if sys.platform == 'darwin':
    # 收集 MCP 库的所有模块
    datas, binaries, hiddenimports = collect_all('mcp')
    
    # 添加 macOS 特定的 MCP 模块
    macos_mcp_modules = collect_submodules('mcp.os.unix')
    hiddenimports += macos_mcp_modules
    
    # 添加可能需要的 Unix 工具模块
    unix_modules = [
        'mcp.os.unix.utilities',
        'mcp.os.unix.socket_utils',
        'mcp.os.unix.process_utils',
    ]
    
    for module in unix_modules:
        try:
            hiddenimports.append(module)
        except ImportError:
            pass  # 模块不存在时忽略
    
    # 添加数据文件
    mcp_datas = collect_data_files('mcp')
    datas += mcp_datas
    
    print(f"[HOOK] macOS MCP hook 执行完成:")
    print(f"   - 隐藏导入: {len(hiddenimports)} 个模块")
    print(f"   - 数据文件: {len(datas)} 个文件")
    print(f"   - 二进制文件: {len(binaries)} 个文件")
else:
    # 非 macOS 平台
    datas = []
    binaries = []
    hiddenimports = []
    print("[HOOK] 非 macOS 平台，跳过 macOS 特定 hook")
