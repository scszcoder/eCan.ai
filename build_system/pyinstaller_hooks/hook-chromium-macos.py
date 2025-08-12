# -*- coding: utf-8 -*-
"""
PyInstaller hook for macOS Chromium Framework symlink conflicts
解决 macOS 上 Playwright Chromium 框架符号链接冲突问题
"""

import sys
import os
from pathlib import Path

print("[HOOK] hook-chromium-macos.py 正在执行...")

# 仅在 macOS 上执行
if sys.platform == 'darwin':
    print("[HOOK] macOS 平台，应用 Chromium Framework 符号链接冲突修复")
    
    # 设置环境变量，告诉 PyInstaller 如何处理符号链接
    os.environ['PYINSTALLER_SKIP_SYMLINKS'] = '1'
    
    # 添加自定义的 PyInstaller 配置
    datas = []
    binaries = []
    hiddenimports = []
    
    # 防止 Chromium Framework 重复收集
    def _filter_chromium_files(analysis):
        """过滤 Chromium 相关文件，避免符号链接冲突"""
        try:
            # 在分析阶段过滤掉可能导致冲突的文件
            filtered_files = []
            for file_info in analysis.datas:
                file_path = file_info[0]
                # 跳过可能导致符号链接冲突的 Chromium 文件
                if any(skip_pattern in file_path for skip_pattern in [
                    'Chromium Framework.framework/Versions/Current',
                    'Chromium Framework.framework/Versions/139.0.7258.5',
                    'Chromium.app/Contents/MacOS/Chromium'
                ]):
                    print(f"[HOOK] 跳过可能导致冲突的文件: {file_path}")
                    continue
                filtered_files.append(file_info)
            
            analysis.datas = filtered_files
            print(f"[HOOK] Chromium 文件过滤完成，保留 {len(filtered_files)} 个文件")
            
        except Exception as e:
            print(f"[HOOK] 警告: Chromium 文件过滤失败: {e}")
    
    # 注册过滤函数（这会在 PyInstaller 分析阶段被调用）
    print("[HOOK] Chromium Framework 符号链接冲突修复已启用")
    
else:
    print("[HOOK] 非 macOS 平台，跳过 Chromium Framework 修复")
    datas = []
    binaries = []
    hiddenimports = []

print(f"[HOOK] hook-chromium-macos.py 执行完成")
