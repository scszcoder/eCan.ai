#!/usr/bin/env python3
import os
import subprocess
import sys
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

def setup_python_env():
    """设置 Python 环境"""
    python_cmd = get_python_cmd()
    
    # 创建虚拟环境
    if not os.path.exists('venv'):
        print("创建虚拟环境...")
        run_command(f'{python_cmd} -m venv venv')
    
    # 获取虚拟环境的 Python 解释器路径
    if sys.platform == 'win32':
        python_path = 'venv\\Scripts\\python'
        pip_path = 'venv\\Scripts\\pip'
    else:
        python_path = 'venv/bin/python3'
        pip_path = 'venv/bin/pip3'
    
    # 升级 pip
    print("升级 pip...")
    run_command(f'{python_path} -m pip install --upgrade pip')
    
    # 安装依赖
    print("安装 Python 依赖...")
    run_command(f'{pip_path} install -r requirements.txt --index-url https://mirrors.aliyun.com/pypi/simple/')
    
    return python_path

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

def main():
    """主函数"""
    print("开始设置开发环境...")
    
    # 设置 Python 环境
    python_path = setup_python_env()
    
    # 设置前端环境
    if not setup_frontend():
        print("前端环境设置失败")
        return 1
    
    print("\n开发环境设置完成！")
    print("\n使用方法：")
    print("1. 激活虚拟环境：")
    if sys.platform == 'win32':
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print("2. 运行应用：")
    print(f"   {python_path} main.py")
    
    return 0

if __name__ == '__main__':
    sys.exit(main()) 