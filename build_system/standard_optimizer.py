#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller 标准优化器
使用 PyInstaller 的标准优化方法，而不是自定义缓存系统
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any


class PyInstallerOptimizer:
    """PyInstaller 标准优化器"""
    
    def __init__(self, config_path: str = "build_system/build_config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.project_root = Path.cwd()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载构建配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[OPTIMIZER] Failed to load config: {e}")
            return {}
    
    def generate_optimized_spec(self, mode: str = "fast") -> str:
        """生成优化的 .spec 文件"""
        app_info = self.config.get('app_info', {})
        pyinstaller_config = self.config.get('pyinstaller', {})
        build_mode = self.config.get('build_modes', {}).get(mode, {})
        optimization = pyinstaller_config.get('optimization', {})
        
        # 合并配置
        final_config = {**pyinstaller_config, **build_mode}
        
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 标准优化配置
# 生成时间: {self._get_timestamp()}

import sys
from pathlib import Path

# 项目根目录
project_root = Path(r"{self.project_root}")

# 数据文件收集
data_files = []
'''
        
        # 添加数据文件
        data_files = self.config.get('data_files', {})
        if data_files.get('directories'):
            spec_content += "\n# 目录数据文件\n"
            for directory in data_files['directories']:
                spec_content += f'data_files.append((r"{directory}", r"{directory}"))\n'
        
        if data_files.get('files'):
            spec_content += "\n# 单个数据文件\n"
            for file in data_files['files']:
                spec_content += f'data_files.append((r"{file}", "."))\n'
        
        # 智能检测器集成
        spec_content += '''
# 智能动态检测器
try:
    from build_system.smart_dynamic_detector import SmartDynamicDetector
    detector = SmartDynamicDetector(project_root)
    smart_hiddenimports = detector.detect_smart_imports()
    print(f"[OPTIMIZER] Smart detector found {len(smart_hiddenimports)} hidden imports")
except Exception as e:
    print(f"[OPTIMIZER] Smart detector failed: {e}")
    smart_hiddenimports = []

'''
        
        # 基础隐藏导入
        base_hiddenimports = pyinstaller_config.get('hidden_imports', [])

        # 强制包含的模块
        force_includes = pyinstaller_config.get('force_includes', [])
        
        # Analysis 配置
        spec_content += f'''
# Analysis 配置
a = Analysis(
    [r"{app_info.get('main_script', 'main.py')}"],
    pathex=[str(project_root)],
    binaries=[],
    datas=data_files,
    hiddenimports={base_hiddenimports} + smart_hiddenimports + {force_includes},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={pyinstaller_config.get('excludes', [])},
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

'''
        
        # 收集数据和二进制文件
        collect_data = pyinstaller_config.get('collect_data', [])
        collect_binaries = pyinstaller_config.get('collect_binaries', [])
        collect_submodules = pyinstaller_config.get('collect_submodules', [])
        
        if collect_data:
            spec_content += f'''
# 安全收集数据文件
from PyInstaller.utils.hooks import collect_data_files

def safe_collect_data_files(module_name):
    """安全地收集数据文件，确保格式正确"""
    try:
        datas = collect_data_files(module_name)
        valid_datas = []
        for item in datas:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                # 确保是三元组格式 (source, dest, type)
                if len(item) == 2:
                    valid_datas.append((str(item[0]), str(item[1]), 'DATA'))
                else:
                    valid_datas.append((str(item[0]), str(item[1]), str(item[2])))
        return valid_datas
    except Exception as e:
        print(f"[OPTIMIZER] Failed to collect data for {{module_name}}: {{e}}")
        return []

# 收集数据文件
for module in {collect_data}:
    valid_datas = safe_collect_data_files(module)
    if valid_datas:
        a.datas.extend(valid_datas)
        print(f"[OPTIMIZER] Collected data for {{module}}: {{len(valid_datas)}} files")

'''
        
        if collect_binaries:
            spec_content += f'''
# 安全收集二进制文件
from PyInstaller.utils.hooks import collect_dynamic_libs

def safe_collect_binaries(module_name):
    """安全地收集二进制文件，确保格式正确"""
    try:
        binaries = collect_dynamic_libs(module_name)
        valid_binaries = []
        for item in binaries:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                # 确保是三元组格式 (source, dest, type)
                if len(item) == 2:
                    valid_binaries.append((str(item[0]), str(item[1]), 'BINARY'))
                else:
                    valid_binaries.append((str(item[0]), str(item[1]), str(item[2])))
        return valid_binaries
    except Exception as e:
        print(f"[OPTIMIZER] Failed to collect binaries for {{module_name}}: {{e}}")
        return []

# 收集二进制文件
for module in {collect_binaries}:
    valid_binaries = safe_collect_binaries(module)
    if valid_binaries:
        a.binaries.extend(valid_binaries)
        print(f"[OPTIMIZER] Collected binaries for {{module}}: {{len(valid_binaries)}} files")

'''
        
        if collect_submodules:
            spec_content += f'''
# 安全收集子模块
from PyInstaller.utils.hooks import collect_submodules

def safe_collect_submodules(module_name):
    """安全地收集子模块"""
    try:
        submodules = collect_submodules(module_name)
        # 确保子模块名称是字符串格式
        valid_submodules = [str(mod) for mod in submodules if mod]
        return valid_submodules
    except Exception as e:
        print(f"[OPTIMIZER] Failed to collect submodules for {{module_name}}: {{e}}")
        return []

# 收集子模块
for module in {collect_submodules}:
    valid_submodules = safe_collect_submodules(module)
    if valid_submodules:
        a.hiddenimports.extend(valid_submodules)
        print(f"[OPTIMIZER] Collected submodules for {{module}}: {{len(valid_submodules)}} modules")

'''
        
        # PYZ 配置
        spec_content += f'''
# PYZ 配置（Python 字节码归档）
pyz = PYZ(
    a.pure, 
    a.zipped_data,
    cipher=None
)

'''
        
        # EXE 配置
        onefile = final_config.get('onefile', False)
        console = final_config.get('console', False)
        debug = final_config.get('debug', False)
        strip_debug = final_config.get('strip_debug', True)
        upx_compress = final_config.get('upx_compress', False)

        # onefile 模式特定优化
        if onefile:
            print("[OPTIMIZER] Applying onefile-specific optimizations...")
            # 减少不必要的数据收集
            if final_config.get('collect_data') == 'minimal':
                print("  • Minimal data collection enabled")
            if final_config.get('lazy_imports', False):
                print("  • Lazy imports enabled")
            if upx_compress:
                print("  • UPX compression enabled")
        
        # 根据模式生成不同的 EXE 配置
        if onefile:
            spec_content += f'''
# EXE 配置 (onefile 模式)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="{app_info.get('name', 'app')}",
    debug={debug},
    bootloader_ignore_signals=False,
    strip={strip_debug},
    upx={upx_compress},
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console},
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r"{app_info.get('icon_windows', 'eCan.ico')}"
)

'''
        else:
            spec_content += f'''
# EXE 配置 (onedir 模式)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="{app_info.get('name', 'app')}",
    debug={debug},
    bootloader_ignore_signals=False,
    strip={strip_debug},
    upx={upx_compress},
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console},
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r"{app_info.get('icon_windows', 'eCan.ico')}"
)

'''
        
        # COLLECT 配置（仅在 onedir 模式下）
        if not onefile:
            spec_content += f'''
# 数据验证和清理
print("[OPTIMIZER] Validating TOC entries...")

# 验证并修复数据格式
def validate_toc_entries(entries, entry_type):
    """验证并修复TOC条目格式"""
    valid_entries = []
    for entry in entries:
        if isinstance(entry, (tuple, list)):
            if len(entry) == 2:
                # 二元组转换为三元组 (source, dest, type)
                valid_entries.append((entry[0], entry[1], 'DATA'))
            elif len(entry) >= 3:
                # 已经是三元组或更多，保留前三个元素
                valid_entries.append((entry[0], entry[1], entry[2]))
    return valid_entries

a.binaries = validate_toc_entries(a.binaries, 'BINARY')
a.zipfiles = validate_toc_entries(a.zipfiles, 'ZIPFILE')
a.datas = validate_toc_entries(a.datas, 'DATA')

print(f"[OPTIMIZER] Validated binaries: {{len(a.binaries)}} entries")
print(f"[OPTIMIZER] Validated zipfiles: {{len(a.zipfiles)}} entries")
print(f"[OPTIMIZER] Validated datas: {{len(a.datas)}} entries")

# COLLECT 配置（目录模式）
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip={strip_debug},
    upx={upx_compress},
    upx_exclude=[],
    name="{app_info.get('name', 'app')}"
)

'''
        
        # macOS 特定配置
        if sys.platform == 'darwin':
            installer_config = self.config.get('installer', {})
            macos_config = installer_config.get('macos', {})
            spec_content += f'''
# macOS App Bundle 配置
app = BUNDLE(
    coll,
    name="{macos_config.get('app_name', app_info.get('name', 'eCan'))}.app",
    icon=r"{app_info.get('icon_macos', 'eCan.icns')}",
    bundle_identifier="{macos_config.get('bundle_identifier', 'com.ecan.app')}",
    version="{macos_config.get('app_version', app_info.get('version', '1.0.0'))}",
    info_plist={{
        'CFBundleName': "{macos_config.get('app_name', app_info.get('name', 'eCan'))}",
        'CFBundleDisplayName': "{macos_config.get('app_name', app_info.get('name', 'eCan'))}",
        'CFBundleVersion': "{macos_config.get('app_version', app_info.get('version', '1.0.0'))}",
        'CFBundleShortVersionString': "{macos_config.get('app_version', app_info.get('version', '1.0.0'))}",
        'CFBundleGetInfoString': "{macos_config.get('copyright', 'Copyright © 2025 eCan.AI Team')}",
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
        'NSRequiresAquaSystemAppearance': False,
    }}
)
'''
        
        return spec_content
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def build_optimized(self, mode: str = "fast", spec_file: str = None) -> bool:
        """使用标准优化构建应用"""
        try:
            # 生成 spec 文件
            if not spec_file:
                spec_file = f"eCan_{mode}.spec"
            
            spec_content = self.generate_optimized_spec(mode)
            
            # 写入 spec 文件
            with open(spec_file, 'w', encoding='utf-8') as f:
                f.write(spec_content)
            
            print(f"[OPTIMIZER] Generated optimized spec file: {spec_file}")
            
            # 构建命令
            build_mode = self.config.get('build_modes', {}).get(mode, {})
            
            cmd = [
                sys.executable, "-m", "PyInstaller",
                spec_file,
                "--noconfirm"
            ]
            
            # 智能缓存逻辑
            use_cache = build_mode.get('use_cache', False)
            clean = build_mode.get('clean', True)

            if clean and not use_cache:
                cmd.append("--clean")
                print("[OPTIMIZER] Cache disabled, cleaning previous build")
            elif use_cache:
                print("[OPTIMIZER] Cache enabled, preserving previous build")
            else:
                cmd.append("--clean")
                print("[OPTIMIZER] Cleaning previous build")
            
            if build_mode.get('parallel', True):
                workers = self.config.get('pyinstaller', {}).get('workers', 0)
                if workers > 0:
                    cmd.extend(["--parallel", str(workers)])
            
            # 执行构建
            print(f"[OPTIMIZER] Building with command: {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=self.project_root)
            
            if result.returncode == 0:
                print(f"[OPTIMIZER] Build successful in {mode} mode")
                return True
            else:
                print(f"[OPTIMIZER] Build failed with return code {result.returncode}")
                return False
                
        except Exception as e:
            print(f"[OPTIMIZER] Build error: {e}")
            return False
    
    def print_optimization_info(self):
        """打印优化信息"""
        print("PyInstaller 标准优化器")
        print("=" * 50)
        
        optimization = self.config.get('pyinstaller', {}).get('optimization', {})
        
        print("优化选项:")
        for key, value in optimization.items():
            print(f"  • {key}: {value}")
        
        print(f"\n可用构建模式:")
        for mode, config in self.config.get('build_modes', {}).items():
            print(f"  • {mode}: onefile={config.get('onefile', False)}, "
                  f"debug={config.get('debug', False)}, "
                  f"optimize={config.get('optimize', False)}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PyInstaller 标准优化器")
    parser.add_argument("--mode", default="fast", choices=["dev", "fast", "prod"],
                       help="构建模式")
    parser.add_argument("--spec", help="自定义 spec 文件名")
    parser.add_argument("--info", action="store_true", help="显示优化信息")
    
    args = parser.parse_args()
    
    optimizer = PyInstallerOptimizer()
    
    if args.info:
        optimizer.print_optimization_info()
    else:
        success = optimizer.build_optimized(args.mode, args.spec)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
