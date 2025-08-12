"""
PyInstaller hook for MCP library
解决 MCP 库在 PyInstaller 中的导入问题
"""

# 添加调试信息，验证 hook 是否被执行
print("[HOOK] hook-mcp.py 正在执行...")

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# 收集 MCP 库的所有模块
datas, binaries, hiddenimports = collect_all('mcp')

# 手动添加可能缺失的子模块
additional_imports = collect_submodules('mcp.server')
additional_imports += collect_submodules('mcp.client') 
additional_imports += collect_submodules('mcp.os.win32')

hiddenimports += additional_imports

# 添加数据文件
mcp_datas = collect_data_files('mcp')
datas += mcp_datas

# 输出调试信息
print(f"[HOOK] MCP hook 执行完成:")
print(f"   - 隐藏导入: {len(hiddenimports)} 个模块")
print(f"   - 数据文件: {len(datas)} 个文件")
print(f"   - 二进制文件: {len(binaries)} 个文件")
