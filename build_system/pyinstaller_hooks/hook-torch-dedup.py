"""
PyTorch 去重 Hook
解决 PyTorch 在 bin 和 lib 目录中的重复文件问题
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
import os
from pathlib import Path

# 收集 torch 的动态库，但避免重复
binaries = []
datas = []

# 已处理的文件名集合 (避免重复)
processed_files = set()

def add_file_if_not_duplicate(src_path, dst_path, file_list):
    """添加文件到列表，如果不是重复的话"""
    filename = os.path.basename(src_path).lower()
    
    if filename not in processed_files:
        file_list.append((src_path, dst_path))
        processed_files.add(filename)
        return True
    else:
        print(f"[TORCH-DEDUP] 跳过重复文件: {filename}")
        return False

# 收集 torch 动态库
try:
    torch_binaries = collect_dynamic_libs('torch')
    for src, dst in torch_binaries:
        add_file_if_not_duplicate(src, dst, binaries)
except Exception as e:
    print(f"[TORCH-DEDUP] 收集动态库时出错: {e}")

# 收集 torch 数据文件
try:
    torch_datas = collect_data_files('torch')
    for src, dst in torch_datas:
        # 只处理二进制文件 (.dll, .so, .dylib, .pyd)
        if any(src.lower().endswith(ext) for ext in ['.dll', '.so', '.dylib', '.pyd']):
            add_file_if_not_duplicate(src, dst, datas)
        else:
            # 非二进制文件直接添加
            datas.append((src, dst))
except Exception as e:
    print(f"[TORCH-DEDUP] 收集数据文件时出错: {e}")

print(f"[TORCH-DEDUP] 处理完成，去重后文件数: {len(processed_files)}")
