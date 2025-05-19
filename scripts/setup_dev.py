#!/usr/bin/env python3
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

def get_python_cmd():
    """获取 Python 命令"""
    if sys.platform == 'win32':
        return 'python'
    return 'python3'

def run_command(cmd, cwd=None):
    """运行命令并打印输出"""
    print(f"执行命令: {cmd}")
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        cwd=cwd
    )
    
    for line in process.stdout:
        print(line, end='')
    
    process.wait()
    return process.returncode

def get_requirements_file():
    """根据操作系统返回对应的 requirements 文件路径"""
    system = platform.system()
    if system == "Darwin":  # macOS
        return "requirements-macos.txt"
    elif system == "Windows":
        return "requirements-windows.txt"
    else:
        print(f"Unsupported operating system: {system}")
        sys.exit(1)

def activate_venv():
    """激活虚拟环境"""
    venv_dir = Path(__file__).parent.parent / "venv"
    
    if platform.system() == "Windows":
        activate_script = venv_dir / "Scripts" / "activate.bat"
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        activate_script = venv_dir / "bin" / "activate"
        python_path = venv_dir / "bin" / "python"
    
    if not activate_script.exists() or not python_path.exists():
        print("错误：找不到虚拟环境")
        return False
    
    # 使用 subprocess 运行激活命令
    if platform.system() == "Windows":
        activate_cmd = f"call {activate_script}"
    else:
        activate_cmd = f"source {activate_script}"
    
    # 运行激活命令
    try:
        subprocess.run(activate_cmd, shell=True, check=True)
        return True
    except subprocess.CalledProcessError:
        print("错误：虚拟环境激活失败")
        return False

def setup_python_env():
    """设置 Python 环境，包括安装依赖"""
    # 获取项目根目录
    root_dir = Path(__file__).parent.parent.absolute()
    venv_dir = root_dir / "venv"
    
    # 获取虚拟环境中的 pip 路径
    if platform.system() == "Windows":
        pip_path = venv_dir / "Scripts" / "pip"
    else:
        pip_path = venv_dir / "bin" / "pip"
    
    # 升级 pip
    print("Upgrading pip...")
    subprocess.run([str(pip_path), "install", "--upgrade", "pip"], check=True)
    
    # 安装依赖
    requirements_file = get_requirements_file()
    print(f"Installing dependencies from {requirements_file}...")
    subprocess.run([
        str(pip_path), "install", "-r", requirements_file,
        "--index-url", "https://mirrors.aliyun.com/pypi/simple/"
    ], check=True)
    
    return str(venv_dir / "bin" / "python") if platform.system() != "Windows" else str(venv_dir / "Scripts" / "python")

def setup_frontend():
    """设置前端环境"""
    gui_dir = Path('gui_v2')
    if not gui_dir.exists():
        print("错误：找不到 gui_v2 目录")
        return False
    
    # 安装前端依赖
    print("安装前端依赖...")
    if run_command('npm install', cwd=gui_dir) != 0:
        return False
    
    # 构建前端
    print("构建前端...")
    if run_command('npm run build', cwd=gui_dir) != 0:
        return False
    
    return True

def cleanup_venv(venv_dir):
    """清理旧的虚拟环境"""
    if venv_dir.exists():
        print("清理旧的虚拟环境...")
        try:
            if platform.system() == "Windows":
                subprocess.run(f"rmdir /s /q {venv_dir}", shell=True, check=True)
            else:
                subprocess.run(f"rm -rf {venv_dir}", shell=True, check=True)
            print("旧的虚拟环境已清理")
        except subprocess.CalledProcessError as e:
            print(f"清理虚拟环境时出错: {e}")
            return False
    return True

def main():
    """主函数"""
    print("开始设置开发环境...")
    
    try:
        # 获取项目根目录
        root_dir = Path(__file__).parent.parent.absolute()
        venv_dir = root_dir / "venv"
        
        # 清理旧的虚拟环境
        if not cleanup_venv(venv_dir):
            print("清理虚拟环境失败")
            return 1
        
        # 创建新的虚拟环境
        print("创建新的虚拟环境...")
        venv.create(venv_dir, with_pip=True)
        
        # 获取激活脚本路径
        if platform.system() == "Windows":
            activate_script = venv_dir / "Scripts" / "activate.bat"
            python_path = venv_dir / "Scripts" / "python.exe"
        else:
            activate_script = venv_dir / "bin" / "activate"
            python_path = venv_dir / "bin" / "python"
        
        # 设置 Python 环境（安装依赖）
        python_path = setup_python_env()
        
        # 设置前端环境
        if not setup_frontend():
            print("前端环境设置失败")
            return 1
        
        print("\n" + "="*50)
        print("开发环境设置完成！")
        print("="*50)
        print("\n请按顺序执行以下命令：")
        print("\n1. 进入项目目录：")
        print(f"   cd {root_dir}")
        
        print("\n2. 激活虚拟环境：")
        if platform.system() == "Windows":
            print(f"   {activate_script}")
        else:
            print(f"   source {activate_script}")
        
        print("\n3. 运行应用：")
        print(f"   {python_path} main.py")
        
        print("\n" + "="*50)
        print("提示：")
        print("1. 每次打开新的终端窗口都需要重新激活虚拟环境")
        print("2. 可以通过命令提示符前的 (venv) 来确认虚拟环境是否已激活")
        print("="*50 + "\n")
        
        return 0
        
    except Exception as e:
        print(f"Error during setup: {str(e)}")
        return 1

if __name__ == '__main__':
    sys.exit(main()) 