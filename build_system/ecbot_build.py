#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot Cross-Platform Build System v8.0
简化构建脚本 - 自动依赖检测
"""

import os
import sys
import json
import time
import subprocess
import platform
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List

# Windows环境下的编码初始化
if platform.system() == "Windows":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'


class BuildEnvironment:
    """构建环境管理"""
    
    def __init__(self):
        self.platform = platform.system()
        self.is_windows = self.platform == "Windows"
        self.is_macos = self.platform == "Darwin"
        self.is_linux = self.platform == "Linux"
        self.is_ci = self._detect_ci_environment()
        
    def _detect_ci_environment(self) -> bool:
        """检测CI环境"""
        ci_vars = ['GITHUB_ACTIONS', 'CI', 'TRAVIS', 'CIRCLECI']
        return any(os.getenv(var) for var in ci_vars)
    
    def get_platform_config(self) -> Dict[str, Any]:
        """获取平台配置"""
        if self.is_windows:
            return {
                "name": "Windows",
                "icon": "ECBot.ico",
                "app_suffix": ".exe",
                "executable_suffix": ".exe"
            }
        elif self.is_macos:
            return {
                "name": "macOS",
                "icon": "ECBot.icns",
                "app_suffix": ".app",
                "executable_suffix": ""
            }
        else:
            return {
                "name": "Linux",
                "icon": "ECBot.ico",
                "app_suffix": "",
                "executable_suffix": ""
            }


class BuildConfig:
    """构建配置管理"""
    
    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load config file: {e}")
            sys.exit(1)
    
    def get_app_info(self) -> Dict[str, Any]:
        """获取应用信息"""
        return self.config.get("app_info", {})
    
    def get_data_files(self) -> Dict[str, Any]:
        """获取数据文件配置"""
        return self.config.get("data_files", {})
    
    def get_pyinstaller_config(self) -> Dict[str, Any]:
        """获取PyInstaller配置"""
        return self.config.get("pyinstaller", {})
    
    def get_build_modes(self) -> Dict[str, Any]:
        """获取构建模式配置"""
        return self.config.get("build_modes", {})


class FrontendBuilder:
    """前端构建器"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.frontend_dir = project_root / "gui_v2"
    
    def build(self, force: bool = False) -> bool:
        """构建前端"""
        if not self.frontend_dir.exists():
            print("[WARNING] Frontend directory not found, skipping frontend build")
            return True
        
        print("[FRONTEND] Building frontend...")
        
        try:
            # 安装依赖
            # if not self._install_dependencies():
            #     return False
            
            # 执行构建
            if not self._run_build():
                return False
            
            print("[SUCCESS] Frontend build completed")
            return True
            
        except Exception as e:
            print(f"[ERROR] Frontend build failed: {e}")
            return False
    
    def _install_dependencies(self) -> bool:
        """安装依赖"""
        try:
            print("[FRONTEND] Installing dependencies...")

            # 根据平台设置命令和环境变量
            if platform.system() == "Windows":
                cmd = "npm ci --legacy-peer-deps"
                shell = True
                # Windows 编码设置
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
                env['CHCP'] = '65001'  # 设置代码页为UTF-8
            else:
                cmd = ["npm", "ci", "--legacy-peer-deps"]
                shell = False
                # macOS/Linux 环境设置
                env = os.environ.copy()
                env['LC_ALL'] = 'en_US.UTF-8'
                env['LANG'] = 'en_US.UTF-8'

            process = subprocess.Popen(
                cmd,
                cwd=self.frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                shell=shell,
                env=env,
                encoding='utf-8',
                errors='replace'  # 替换无法解码的字符而不是抛出异常
            )

            # 实时显示输出
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[FRONTEND] {line.rstrip()}")

            return_code = process.wait()

            if return_code != 0:
                print(f"[ERROR] npm install failed with exit code: {return_code}")
                return False

            print("[SUCCESS] Dependencies installed successfully")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to install dependencies: {e}")
            return False
    
    def _run_build(self) -> bool:
        """执行构建"""
        try:
            print("[FRONTEND] Building frontend...")

            # 根据平台设置命令和环境变量
            if platform.system() == "Windows":
                cmd = "npm run build"
                shell = True
                # Windows 编码设置
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
                env['CHCP'] = '65001'  # 设置代码页为UTF-8
            else:
                cmd = ["npm", "run", "build"]
                shell = False
                # macOS/Linux 环境设置
                env = os.environ.copy()
                env['LC_ALL'] = 'en_US.UTF-8'
                env['LANG'] = 'en_US.UTF-8'

            process = subprocess.Popen(
                cmd,
                cwd=self.frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                shell=shell,
                env=env,
                encoding='utf-8',
                errors='replace'  # 替换无法解码的字符而不是抛出异常
            )

            # 实时显示输出
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[FRONTEND] {line.rstrip()}")

            return_code = process.wait()

            if return_code != 0:
                print(f"[ERROR] npm build failed with exit code: {return_code}")
                return False

            print("[SUCCESS] Frontend build completed")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to build frontend: {e}")
            return False


class PyInstallerBuilder:
    """PyInstaller构建器"""
    
    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path):
        self.config = config
        self.env = env
        self.project_root = project_root
        self.build_dir = project_root / "build"
        self.dist_dir = project_root / "dist"
    
    def build(self, mode: str, force: bool = False) -> bool:
        """构建应用"""
        print(f"[PYINSTALLER] Starting PyInstaller build...")

        try:
            # 检查是否需要重新构建
            if not force and self._should_skip_build():
                print("[PYINSTALLER] Build is up to date, skipping...")
                return True

            # 清理之前的构建
            if force:
                if not self._clean_previous_build():
                    print("[ERROR] Failed to clean previous build")
                    return False
            else:
                # 即使不是强制构建，也检查并清理输出目录
                if self.dist_dir.exists():
                    print("[PYINSTALLER] Output directory exists, cleaning...")
                    if not self._clean_previous_build():
                        print("[ERROR] Failed to clean output directory")
                        return False
            
            # 生成spec文件
            spec_file = self._generate_spec_file(mode)
            if not spec_file:
                return False
            
            # 运行PyInstaller
            if not self._run_pyinstaller(spec_file):
                return False
            
            print("[SUCCESS] PyInstaller build completed")
            return True
            
        except Exception as e:
            print(f"[ERROR] PyInstaller build failed: {e}")
            return False

    def _should_skip_build(self) -> bool:
        """检查是否应该跳过构建（基于文件修改时间）"""
        try:
            # 根据操作系统确定可执行文件名
            if platform.system() == "Windows":
                exe_name = "ECBot.exe"
            else:
                exe_name = "ECBot"  # macOS 和 Linux 不需要 .exe 扩展名

            # 检查输出文件是否存在
            exe_file = self.dist_dir / "ECBot" / exe_name
            if not exe_file.exists():
                print(f"[CACHE] Executable not found: {exe_file}")
                return False

            exe_mtime = exe_file.stat().st_mtime
            print(f"[CACHE] Checking build cache, executable modified: {exe_mtime}")

            # 检查源代码文件是否有更新
            source_dirs = [
                self.project_root / "src",
                self.project_root / "gui",
                self.project_root / "bot",
                self.project_root / "config",
                self.project_root / "main.py"
            ]

            for source_path in source_dirs:
                if source_path.is_file():
                    if source_path.exists() and source_path.stat().st_mtime > exe_mtime:
                        print(f"[CACHE] Source file newer than executable: {source_path}")
                        return False
                elif source_path.is_dir() and source_path.exists():
                    for py_file in source_path.rglob("*.py"):
                        if py_file.stat().st_mtime > exe_mtime:
                            print(f"[CACHE] Source file newer than executable: {py_file}")
                            return False

            print("[CACHE] Build is up to date")
            return True
        except Exception as e:
            print(f"[CACHE] Error checking build cache: {e}")
            return False

    def _clean_previous_build(self):
        """清理之前的构建"""
        print("[PYINSTALLER] Cleaning previous build...")
        try:
            if self.build_dir.exists():
                import shutil
                shutil.rmtree(self.build_dir)
                print(f"[PYINSTALLER] Cleaned build directory: {self.build_dir}")
            
            if self.dist_dir.exists():
                import shutil
                shutil.rmtree(self.dist_dir)
                print(f"[PYINSTALLER] Cleaned dist directory: {self.dist_dir}")
        except Exception as e:
            print(f"[WARNING] Failed to clean previous build: {e}")
            # 尝试使用系统命令清理
            import subprocess
            try:
                if self.build_dir.exists():
                    subprocess.run(["rm", "-rf", str(self.build_dir)], check=True)
                if self.dist_dir.exists():
                    subprocess.run(["rm", "-rf", str(self.dist_dir)], check=True)
                print("[PYINSTALLER] Cleaned using system commands")
            except Exception as e2:
                print(f"[ERROR] Failed to clean using system commands: {e2}")
                return False
        return True
    
    def _generate_spec_file(self, mode: str) -> Optional[Path]:
        """生成spec文件"""
        try:
            spec_content = self._create_spec_content(mode)
            spec_file = self.build_dir / "ecbot.spec"
            
            # 确保build目录存在
            self.build_dir.mkdir(exist_ok=True)
            
            with open(spec_file, 'w', encoding='utf-8') as f:
                f.write(spec_content)
            
            print(f"[PYINSTALLER] Spec file generated: {spec_file}")
            return spec_file
            
        except Exception as e:
            print(f"[ERROR] Failed to generate spec file: {e}")
            return None
    
    def _create_spec_content(self, mode: str) -> str:
        """创建spec文件内容"""
        app_info = self.config.get_app_info()
        data_files = self.config.get_data_files()
        pyinstaller_config = self.config.get_pyinstaller_config()
        
        # 基础配置
        main_script = app_info.get("main_script", "main.py")
        main_script_path = str(self.project_root / main_script)

        # 根据平台选择正确的图标文件
        if self.env.is_windows:
            icon_name = app_info.get("icon_windows", "ECBot.ico")
        elif self.env.is_macos:
            icon_name = app_info.get("icon_macos", "ECBot.icns")
        else:
            icon_name = app_info.get("icon_windows", "ECBot.ico")  # Linux 使用 ico 作为默认

        icon_path = str(self.project_root / icon_name)
        
        # 格式化数据文件
        data_files_str = self._format_data_files(data_files)
        
        # 获取必要的包作为hidden_imports
        essential_packages = self._get_essential_packages()
        hidden_imports = essential_packages
        

        
        # 简化的spec内容 - 包含所有依赖，只排除特定包
        spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    [r'{main_script_path}'],
    pathex=[r'{self.project_root}'],
    binaries=[],
    datas={data_files_str},
    hiddenimports={hidden_imports},
    hookspath=[r'{self.project_root / "build_system" / "hooks"}'],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={pyinstaller_config.get("excludes", [])},
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{app_info.get("name", "ECBot")}',
    debug={mode == "dev"},
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console={mode == "dev"},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r'{icon_path}',
)
"""
        
        # 添加平台特定配置
        if self.env.is_windows:
            spec_content += f"""
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ECBot',
)
"""
        elif self.env.is_macos:
            spec_content += f"""
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ECBot',
)

app = BUNDLE(
    coll,
    name='ECBot.app',
    icon=r'{icon_path}',
    bundle_identifier='com.ecbot.app',
    info_plist={{
        'CFBundleName': 'ECBot',
        'CFBundleDisplayName': 'ECBot',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14',
        'NSPrincipalClass': 'NSApplication',
        'CFBundleDocumentTypes': [],
        'CFBundleURLTypes': [],
        'LSApplicationCategoryType': 'public.app-category.productivity',
        'NSAppTransportSecurity': {{
            'NSAllowsArbitraryLoads': True
        }}
    }},
)
"""
        
        return spec_content
    
    def _get_essential_packages(self) -> List[str]:
        """使用智能动态导入检测器获取包列表"""
        print("[PYINSTALLER] 使用智能动态导入检测器...")
        
        try:
            # 导入智能检测器 - 修复导入路径
            import sys
            build_system_path = str(self.project_root / "build_system")
            if build_system_path not in sys.path:
                sys.path.insert(0, build_system_path)
            
            from smart_dynamic_detector import SmartDynamicDetector
            
            # 创建检测器实例
            detector = SmartDynamicDetector(self.project_root)
            
            # 检测智能动态导入
            all_packages = detector.detect_smart_imports()
            
            print(f"[PYINSTALLER] 智能检测器发现 {len(all_packages)} 个包")
            
            return all_packages
            
        except ImportError as e:
            self._handle_package_manager_error(f"智能检测器文件不存在: {e}")
            return []
        except Exception as e:
            self._handle_package_manager_error(f"智能检测器错误: {e}")
            return []
    
    def _handle_package_manager_error(self, error_msg: str):
        """处理智能检测器错误"""
        print(f"[ERROR] {error_msg}")
        print("[ERROR] 智能动态导入检测器配置错误，构建失败")
        print("[ERROR] 请检查以下文件:")
        print("  - build_system/smart_dynamic_detector.py")
        print("[ERROR] 或者运行以下命令测试检测器:")
        print("  python build_system/smart_dynamic_detector.py")
    

    
    def _format_data_files(self, data_files: Dict[str, Any]) -> str:
        """格式化数据文件"""
        files = []

        # 添加目录
        for directory in data_files.get("directories", []):
            dir_path = self.project_root / directory
            if dir_path.exists():
                files.append(f"(r'{dir_path}', '{directory}')")

        # 添加文件
        for file_path in data_files.get("files", []):
            file_path_obj = self.project_root / file_path
            if file_path_obj.exists():
                files.append(f"(r'{file_path_obj}', '.')")

        # 处理包数据文件
        for package_data in data_files.get("package_data", []):
            package_name = package_data.get("package")
            source_pattern = package_data.get("source_pattern")
            destination = package_data.get("destination")

            if package_name and source_pattern and destination:
                try:
                    import importlib.util
                    import glob

                    # 找到包的位置
                    spec = importlib.util.find_spec(package_name)
                    if spec and spec.origin:
                        package_path = Path(spec.origin).parent
                        pattern_path = package_path / source_pattern

                        # 使用glob查找匹配的文件
                        for file_path in glob.glob(str(pattern_path)):
                            file_path = Path(file_path)
                            if file_path.exists():
                                files.append(f"(r'{file_path}', '{destination}')")
                                print(f"   添加包数据文件: {file_path.name} -> {destination}")
                except Exception as e:
                    print(f"   警告: 处理包数据文件失败 {package_name}: {e}")

        return f"[{', '.join(files)}]"
    
    def _run_pyinstaller(self, spec_file: Path) -> bool:
        """运行PyInstaller"""
        try:
            print(f"[PYINSTALLER] Running command: {sys.executable} -m PyInstaller {spec_file}")
            print(f"[PYINSTALLER] Working directory: {self.project_root}")
            print("=" * 60)

            # 根据平台设置环境变量
            if platform.system() == "Windows":
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
                env['CHCP'] = '65001'  # 设置代码页为UTF-8
            else:
                # macOS/Linux 环境设置
                env = os.environ.copy()
                env['LC_ALL'] = 'en_US.UTF-8'
                env['LANG'] = 'en_US.UTF-8'

            # 添加并行构建参数
            cmd = [sys.executable, "-m", "PyInstaller"]

            # 添加性能优化参数
            cmd.extend([
                "--noconfirm",  # 不询问确认
                "--clean",      # 清理临时文件
                str(spec_file)
            ])

            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                encoding='utf-8',
                errors='replace'  # 替换无法解码的字符而不是抛出异常
            )

            # 实时显示输出
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[PYINSTALLER] {line.rstrip()}")

            return_code = process.wait()

            print("=" * 60)

            if return_code != 0:
                print(f"[ERROR] PyInstaller failed with exit code: {return_code}")
                return False

            return True

        except Exception as e:
            print(f"[ERROR] Failed to run PyInstaller: {e}")
            return False


class InstallerBuilder:
    """安装包构建器"""

    def __init__(self, config: BuildConfig, env: BuildEnvironment, project_root: Path, mode: str = "prod"):
        self.config = config
        self.env = env
        self.project_root = project_root
        self.dist_dir = project_root / "dist"
        self.mode = mode
    
    def build(self) -> bool:
        """构建安装包"""
        if self.env.is_windows:
            return self._build_windows_installer()
        elif self.env.is_macos:
            return self._build_macos_installer()
        else:
            print("[INFO] Installer creation not implemented for this platform")
            return True
    
    def _build_windows_installer(self) -> bool:
        """构建Windows安装包"""
        try:
            # 检查Inno Setup
            if not self._check_inno_setup():
                print("[WARNING] Inno Setup not found, skipping installer creation")
                return True
            
            # 创建Inno Setup脚本
            iss_file = self._create_inno_script()
            if not iss_file:
                return False
            
            # 运行Inno Setup
            return self._run_inno_setup(iss_file)
            
        except Exception as e:
            print(f"[ERROR] Windows installer creation failed: {e}")
            return False
    
    def _check_inno_setup(self) -> bool:
        """检查Inno Setup"""
        inno_paths = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe"
        ]
        return any(Path(path).exists() for path in inno_paths)
    
    def _create_inno_script(self) -> Optional[Path]:
        """创建Inno Setup脚本"""
        try:
            installer_config = self.config.config.get("installer", {})
            app_info = self.config.get_app_info()

            # 根据构建模式选择压缩设置
            compression_modes = installer_config.get("compression_modes", {})
            mode_config = compression_modes.get(self.mode, {})

            # 使用模式特定配置，或回退到默认值
            compression = mode_config.get("compression", installer_config.get("compression", "zip"))
            solid_compression = str(mode_config.get("solid_compression", installer_config.get("solid_compression", False))).lower()
            internal_compress_level = mode_config.get("internal_compress_level", "fast")

            iss_content = f"""
[Setup]
AppName={installer_config.get('app_name', app_info.get('name', 'ECBot'))}
AppVersion={installer_config.get('app_version', app_info.get('version', '1.0.0'))}
AppPublisher={installer_config.get('app_publisher', 'ECBot Team')}
DefaultDirName={{autopf}}\\ECBot
DefaultGroupName=ECBot
OutputDir=..\\dist
OutputBaseFilename=ECBot-Setup
Compression={compression}
SolidCompression={solid_compression}
PrivilegesRequired=lowest
InternalCompressLevel={internal_compress_level}
; 改进的安装配置以避免COM错误
SetupIconFile=..\\ECBot.ico
UninstallDisplayIcon={{app}}\\ECBot.exe
CreateUninstallRegKey=true
; 处理权限问题
AllowNoIcons=true
DisableProgramGroupPage=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "..\\dist\\ECBot\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\ECBot"; Filename: "{{app}}\\ECBot.exe"
Name: "{{userdesktop}}\\ECBot"; Filename: "{{app}}\\ECBot.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\ECBot.exe"; Description: "{{cm:LaunchProgram,ECBot}}"; Flags: nowait postinstall skipifsilent
"""
            
            iss_file = self.project_root / "build" / "setup.iss"
            iss_file.parent.mkdir(exist_ok=True)
            
            with open(iss_file, 'w', encoding='utf-8') as f:
                f.write(iss_content)
            
            return iss_file
            
        except Exception as e:
            print(f"[ERROR] Failed to create Inno Setup script: {e}")
            return None
    
    def _run_inno_setup(self, iss_file: Path) -> bool:
        """运行Inno Setup"""
        try:
            inno_paths = [
                r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                r"C:\Program Files\Inno Setup 6\ISCC.exe"
            ]
            
            iscc_path = None
            for path in inno_paths:
                if Path(path).exists():
                    iscc_path = path
                    break
            
            if not iscc_path:
                print("[ERROR] Inno Setup compiler not found")
                return False
            
            # 根据压缩模式动态设置超时时间
            installer_config = self.config.config.get("installer", {})
            compression_modes = installer_config.get("compression_modes", {})
            mode_config = compression_modes.get(self.mode, {})

            compression = mode_config.get("compression", installer_config.get("compression", "lzma"))
            solid_compression = mode_config.get("solid_compression", installer_config.get("solid_compression", False))
            internal_compress_level = mode_config.get("internal_compress_level", "normal")

            # 根据压缩设置计算超时时间
            if compression == "lzma" and solid_compression and internal_compress_level == "max":
                timeout_seconds = 1800  # 30分钟 - 最高压缩
            elif compression == "lzma" and internal_compress_level in ["max", "ultra"]:
                timeout_seconds = 1200  # 20分钟 - 高压缩
            elif compression == "lzma":
                timeout_seconds = 900   # 15分钟 - 中等压缩
            else:
                timeout_seconds = 600   # 10分钟 - 快速压缩

            print(f"[INSTALLER] Running Inno Setup: {iscc_path}")
            print(f"[INSTALLER] Script file: {iss_file}")
            print(f"[INSTALLER] Build mode: {self.mode}")
            print(f"[INSTALLER] Compression: {compression}, Solid: {solid_compression}, Level: {internal_compress_level}")
            print(f"[INSTALLER] Timeout: {timeout_seconds//60} minutes")

            # Windows环境下的编码处理
            if self.env.is_windows:
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'

                # 构建 Inno Setup 命令
                cmd = [iscc_path, str(iss_file)]

                try:
                    result = subprocess.run(
                        cmd,
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        env=env,
                        encoding='utf-8',
                        errors='replace',
                        timeout=timeout_seconds
                    )
                except subprocess.TimeoutExpired:
                    print(f"[ERROR] Inno Setup compilation timed out ({timeout_seconds//60} minutes)")
                    return False
            else:
                result = subprocess.run(
                    [iscc_path, str(iss_file)],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True
                )
            
            if result.returncode != 0:
                print(f"[ERROR] Inno Setup compilation failed:")
                print(f"[ERROR] Return code: {result.returncode}")
                print(f"[ERROR] STDOUT: {result.stdout}")
                print(f"[ERROR] STDERR: {result.stderr}")
                return False

            print("[SUCCESS] Windows installer created")
            print(f"[INFO] Inno Setup output: {result.stdout}")

            # 检查输出文件是否存在
            expected_output = self.dist_dir / "ECBot-Setup.exe"
            if expected_output.exists():
                size_mb = expected_output.stat().st_size / (1024 * 1024)
                print(f"[INFO] Installer file: {expected_output}")
                print(f"[INFO] File size: {size_mb:.1f} MB")
            else:
                print(f"[WARNING] Expected installer file not found: {expected_output}")

            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to run Inno Setup: {e}")
            return False

    def _build_macos_installer(self) -> bool:
        """构建macOS安装包"""
        try:
            print("[INSTALLER] Building macOS pkg installer...")
            
            # 检查必要的工具
            if not self._check_macos_tools():
                print("[WARNING] Required macOS tools not found, skipping pkg creation")
                return True
            
            # 检查.app文件是否存在
            app_path = self.dist_dir / "ECBot.app"
            if not app_path.exists():
                print(f"[ERROR] App bundle not found: {app_path}")
                print("[ERROR] Please build the app first using PyInstaller")
                return False
            
            
            # 创建组件包
            component_pkg = self._create_component_package(app_path)
            if not component_pkg:
                return False
            
            # 创建最终安装包
            final_pkg = self._create_final_package(component_pkg)
            if not final_pkg:
                return False
            
            print("[SUCCESS] macOS pkg installer created")
            return True
            
        except Exception as e:
            print(f"[ERROR] macOS installer creation failed: {e}")
            return False
    
    def _check_macos_tools(self) -> bool:
        """检查macOS必要的工具"""
        try:
            # 检查pkgbuild - 使用 --help 而不是 --version
            result = subprocess.run(["pkgbuild", "--help"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0 and result.returncode != 1:  # pkgbuild --help 可能返回1
                print("[ERROR] pkgbuild not found or not working")
                return False
            
            # 检查productbuild - 使用 --help 而不是 --version
            result = subprocess.run(["productbuild", "--help"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0 and result.returncode != 1:  # productbuild --help 可能返回1
                print("[ERROR] productbuild not found or not working")
                return False
            
            print("[SUCCESS] macOS packaging tools found")
            return True
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Timeout checking macOS tools")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to check macOS tools: {e}")
            return False
    


    def _create_component_package(self, app_path: Path) -> Optional[Path]:
        """创建组件包"""
        try:
            print("[MACOS] Creating component package...")
            
            # 创建构建目录
            build_dir = self.project_root / "build" / "macos_pkg"
            build_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建 postinstall 脚本
            scripts_dir = build_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            
            postinstall_script = scripts_dir / "postinstall"
            postinstall_content = """#!/bin/bash
# 安装后脚本
echo "Installing ECBot..."

# 设置应用权限
chmod -R 755 "/Applications/ECBot.app"

# 创建桌面快捷方式
if [ -d "/Users/$USER/Desktop" ]; then
    ln -sf "/Applications/ECBot.app" "/Users/$USER/Desktop/ECBot.app"
    echo "Desktop shortcut created"
fi

# 创建应用程序文件夹快捷方式
if [ -d "/Applications" ]; then
    # 确保应用在应用程序文件夹中可见
    touch "/Applications/ECBot.app"
fi

# 刷新 Finder 和 Dock
killall Finder 2>/dev/null || true
killall Dock 2>/dev/null || true

echo "ECBot installation completed"
exit 0
"""
            
            with open(postinstall_script, 'w', encoding='utf-8') as f:
                f.write(postinstall_content)
            
            postinstall_script.chmod(0o755)
            
            # 创建组件包
            component_pkg = build_dir / "ECBot-component.pkg"
            cmd = [
                "pkgbuild",
                "--component", str(app_path),
                "--install-location", "/Applications",
                "--identifier", "com.ecbot.app",
                "--version", "1.0.0",
                "--scripts", str(scripts_dir),
                str(component_pkg)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                print(f"[ERROR] pkgbuild failed:")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return None
            
            print(f"[MACOS] Component package created: {component_pkg}")
            return component_pkg
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Component package creation timed out after 600 seconds")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to create component package: {e}")
            return None

    def _create_final_package(self, component_pkg: Path) -> Optional[Path]:
        """创建最终安装包"""
        try:
            print("[MACOS] Creating final package...")
            
            # 创建 distribution.xml
            build_dir = self.project_root / "build" / "macos_pkg"
            dist_xml = build_dir / "distribution.xml"
            
            distribution_content = f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>ECBot</title>
    <organization>com.ecbot</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true"/>
    <pkg-ref id="com.ecbot.app"/>
    <choices-outline>
        <line choice="com.ecbot.app"/>
    </choices-outline>
    <choice id="com.ecbot.app" title="ECBot">
        <pkg-ref id="com.ecbot.app"/>
    </choice>
    <pkg-ref id="com.ecbot.app" version="1.0.0" onConclusion="none">{component_pkg.name}</pkg-ref>
</installer-gui-script>
"""
            
            with open(dist_xml, 'w', encoding='utf-8') as f:
                f.write(distribution_content)
            
            # 创建 resources 目录
            resources_dir = build_dir / "resources"
            resources_dir.mkdir(exist_ok=True)
            
            # 创建最终安装包
            final_pkg = self.dist_dir / "ECBot-1.0.0.pkg"
            cmd = [
                "productbuild",
                "--distribution", str(dist_xml),
                "--package-path", str(component_pkg.parent),
                "--resources", str(resources_dir),
                str(final_pkg)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                print(f"[ERROR] productbuild failed:")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return None
            
            # 检查文件大小
            if final_pkg.exists():
                size_mb = final_pkg.stat().st_size / (1024 * 1024)
                print(f"[MACOS] Final package created: {final_pkg} ({size_mb:.1f} MB)")
                return final_pkg
            else:
                print("[ERROR] Final package file not found")
                return None
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Final package creation timed out after 600 seconds")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to create final package: {e}")
            return None
    



class ECBotBuild:
    """ECBot构建主类"""
    
    def __init__(self, mode: str = "prod", fast: bool = False):
        self.mode = mode
        self.fast = fast
        self.project_root = Path.cwd()

        # 选择配置文件
        if fast:
            config_file = self.project_root / "build_system" / "fast_build_config.json"
        else:
            config_file = self.project_root / "build_system" / "build_config.json"

        self.config = BuildConfig(config_file)
        self.env = BuildEnvironment()
        self.frontend_builder = FrontendBuilder(self.project_root)
        self.pyinstaller_builder = PyInstallerBuilder(self.config, self.env, self.project_root)
        self.installer_builder = InstallerBuilder(self.config, self.env, self.project_root, self.mode)
    
    def build(self, force: bool = False, skip_frontend: bool = None, skip_installer: bool = False) -> bool:
        """执行构建"""
        start_time = time.time()

        print("=" * 60)
        print("ECBot Cross-Platform Build System v8.0")
        print("=" * 60)

        try:
            # 构建前端（如果需要）
            if skip_frontend is None:
                skip_frontend = self.mode == "prod"

            if not skip_frontend:
                if not self.frontend_builder.build(force):
                    return False

            # 构建主应用
            if not self.pyinstaller_builder.build(self.mode, force):
                return False

            # 构建安装包（如果需要）
            if not skip_installer:
                print(f"[INFO] Creating installer for {self.mode} mode...")
                if not self.installer_builder.build():
                    print("[WARNING] Installer creation failed, but build continues")
            else:
                print("[INFO] Skipping installer creation")

            # 显示结果
            self._show_result(start_time)
            return True

        except KeyboardInterrupt:
            print("\n[INFO] Build interrupted by user")
            return False
        except Exception as e:
            print(f"[ERROR] Build failed: {e}")
            return False
    
    def _show_result(self, start_time: float):
        """显示构建结果"""
        build_time = time.time() - start_time
        print("=" * 60)
        print(f"[SUCCESS] Build completed in {build_time:.2f} seconds")
        print(f"[INFO] Build mode: {self.mode}")
        print(f"[INFO] Platform: {self.env.platform}")
        print("=" * 60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="ECBot Build System")
    parser.add_argument("mode", choices=["dev", "prod", "fast"], default="prod", nargs="?",
                       help="Build mode (default: prod)")
    parser.add_argument("--force", "-f", action="store_true",
                       help="Force rebuild")
    parser.add_argument("--skip-frontend", action="store_true",
                       help="Skip frontend build")
    parser.add_argument("--skip-installer", action="store_true",
                       help="Skip installer creation")
    parser.add_argument("--fast", action="store_true",
                       help="Use fast build configuration (fewer dependencies)")

    args = parser.parse_args()

    # 如果模式是fast，自动启用fast配置
    fast_mode = args.fast or args.mode == "fast"
    build_mode = "dev" if args.mode == "fast" else args.mode

    builder = ECBotBuild(build_mode, fast=fast_mode)
    success = builder.build(force=args.force, skip_frontend=args.skip_frontend, skip_installer=args.skip_installer)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
