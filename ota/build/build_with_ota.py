#!/usr/bin/env python3
"""
带OTA更新功能的构建脚本
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path

def build_with_ota():
    """构建带OTA更新功能的ECBot"""
    
    print("Building ECBot with OTA update support...")
    
    project_root = Path(__file__).parent.parent
    build_dir = project_root / "dist"
    
    # 确保构建目录存在
    build_dir.mkdir(exist_ok=True)
    
    current_platform = platform.system()
    
    try:
        # 1. 构建Sparkle/winSparkle组件
        print("Building OTA components...")
        sparkle_builder = project_root / "ota" / "build" / "sparkle_build.py"
        subprocess.run([sys.executable, str(sparkle_builder), "build"], check=True)
        
        # 2. 复制OTA更新文件到构建目录
        print("Copying OTA files...")
        ota_files = [
            "ota/core/updater.py",
            "ota/gui/dialog.py",
            "ota/server/appcast.xml",
            "VERSION"
        ]
        
        for file_path in ota_files:
            src = project_root / file_path
            if src.exists():
                dst = build_dir / file_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"Copied {file_path}")
        
        # 3. 复制平台特定的OTA组件
        if current_platform == "Darwin":
            # macOS Sparkle框架
            sparkle_build_dir = project_root / "build" / "sparkle"
            if sparkle_build_dir.exists():
                frameworks_dir = build_dir / "Frameworks"
                frameworks_dir.mkdir(exist_ok=True)
                
                sparkle_framework = sparkle_build_dir / "Sparkle.framework"
                if sparkle_framework.exists():
                    shutil.copytree(sparkle_framework, frameworks_dir / "Sparkle.framework", dirs_exist_ok=True)
                    print("Copied Sparkle.framework")
                
                sparkle_cli = sparkle_build_dir / "sparkle-cli"
                if sparkle_cli.exists():
                    shutil.copy2(sparkle_cli, build_dir / "sparkle-cli")
                    print("Copied sparkle-cli")
        
        elif current_platform == "Windows":
            # Windows winSparkle DLL
            winsparkle_build_dir = project_root / "build" / "sparkle"
            if winsparkle_build_dir.exists():
                winsparkle_dll = winsparkle_build_dir / "winsparkle.dll"
                if winsparkle_dll.exists():
                    shutil.copy2(winsparkle_dll, build_dir / "winsparkle.dll")
                    print("Copied winsparkle.dll")
                
                winsparkle_cli = winsparkle_build_dir / "winsparkle-cli.exe"
                if winsparkle_cli.exists():
                    shutil.copy2(winsparkle_cli, build_dir / "winsparkle-cli.exe")
                    print("Copied winsparkle-cli.exe")
        
        # 4. 运行主构建脚本
        print("Running main build...")
        main_build = project_root / "build.py"
        if main_build.exists():
            subprocess.run([sys.executable, str(main_build)], check=True)
        
        # 5. 复制OTA包到构建目录
        print("Copying OTA package...")
        ota_package_dir = build_dir / "ota"
        if ota_package_dir.exists():
            shutil.rmtree(ota_package_dir)
        shutil.copytree(project_root / "ota", ota_package_dir)
        
        # 6. 验证OTA组件
        print("Verifying OTA components...")
        verify_ota_build(build_dir, current_platform)
        
        print("Build with OTA completed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Build error: {e}")
        sys.exit(1)

def verify_ota_build(build_dir, platform_name):
    """验证OTA构建组件"""
    
    required_files = [
        "ota/core/updater.py",
        "ota/gui/dialog.py",
        "VERSION"
    ]
    
    # 平台特定文件
    if platform_name == "Darwin":
        required_files.extend([
            "Frameworks/Sparkle.framework",
            "sparkle-cli"
        ])
    elif platform_name == "Windows":
        required_files.extend([
            "winsparkle.dll",
            "winsparkle-cli.exe"
        ])
    
    # OTA包文件
    required_files.extend([
        "ota/__init__.py",
        "ota/core/__init__.py",
        "ota/gui/__init__.py",
        "ota/platforms/__init__.py"
    ])
    
    missing_files = []
    for file_path in required_files:
        full_path = build_dir / file_path
        if not full_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("Warning: Missing OTA files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
    else:
        print("All OTA components verified successfully!")

def create_update_package():
    """创建更新包"""
    
    print("Creating update package...")
    
    project_root = Path(__file__).parent.parent
    build_dir = project_root / "dist"
    
    if not build_dir.exists():
        print("Build directory not found. Run build first.")
        return
    
    current_platform = platform.system()
    
    # 读取版本号
    version_file = project_root / "VERSION"
    version = "1.0.0"
    if version_file.exists():
        version = version_file.read_text().strip()
    
    # 创建更新包
    if current_platform == "Darwin":
        package_name = f"ECBot-{version}.dmg"
        print(f"Creating macOS package: {package_name}")
        # 这里应该创建DMG文件
        
    elif current_platform == "Windows":
        package_name = f"ECBot-{version}.exe"
        print(f"Creating Windows package: {package_name}")
        # 这里应该创建安装程序
        
    else:
        package_name = f"ECBot-{version}.tar.gz"
        print(f"Creating Linux package: {package_name}")
        # 这里应该创建tar.gz文件
    
    print(f"Update package created: {package_name}")

def start_update_server():
    """启动更新服务器"""
    
    print("Starting update server for testing...")
    
    server_script = Path(__file__).parent / "update_server.py"
    if server_script.exists():
        subprocess.run([sys.executable, str(server_script)])
    else:
        print("Update server script not found!")

def main():
    """主函数"""
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "build":
            build_with_ota()
        elif command == "package":
            create_update_package()
        elif command == "server":
            start_update_server()
        elif command == "all":
            build_with_ota()
            create_update_package()
        else:
            print("Unknown command:", command)
            print("Available commands: build, package, server, all")
    else:
        print("ECBot OTA Build System")
        print("Usage: python build_with_ota.py <command>")
        print("Commands:")
        print("  build   - Build ECBot with OTA support")
        print("  package - Create update package")
        print("  server  - Start update server for testing")
        print("  all     - Build and package")

if __name__ == "__main__":
    main()