#!/usr/bin/env python3
"""
本地OTA测试服务器启动脚本
用于开发和测试OTA更新功能
"""

import os
import sys
import subprocess
import platform
import webbrowser
from pathlib import Path

def check_dependencies():
    """检查依赖"""
    try:
        import flask
        print("✓ Flask已安装")
        return True
    except ImportError:
        print("✗ Flask未安装，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
            print("✓ Flask安装成功")
            return True
        except subprocess.CalledProcessError:
            print("✗ Flask安装失败")
            return False

def start_server():
    """启动本地OTA服务器"""
    print("=" * 50)
    print("ECBot 本地OTA测试服务器")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        print("依赖检查失败，无法启动服务器")
        return False
    
    # 获取服务器脚本路径
    server_dir = Path(__file__).parent / "server"
    server_script = server_dir / "update_server.py"
    
    if not server_script.exists():
        print(f"✗ 服务器脚本不存在: {server_script}")
        return False
    
    print(f"✓ 服务器脚本路径: {server_script}")
    print(f"✓ 工作目录: {server_dir}")
    
    # 显示服务器信息
    print("\n服务器信息:")
    print("  - 地址: http://127.0.0.1:8080")
    print("  - 端点:")
    print("    * GET /api/check-update - 检查更新")
    print("    * GET /appcast.xml - Sparkle appcast文件")
    print("    * GET /health - 健康检查")
    print("    * GET / - 服务器信息")
    
    print("\n正在启动服务器...")
    
    try:
        # 切换到服务器目录并启动
        os.chdir(server_dir)
        
        # 设置环境变量
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).parent.parent)  # 添加项目根目录到Python路径
        
        # 启动服务器
        print("按 Ctrl+C 停止服务器")
        print("-" * 50)
        
        # 在新窗口中打开浏览器（可选）
        try:
            webbrowser.open("http://127.0.0.1:8080")
        except:
            pass
        
        # 启动Flask服务器
        subprocess.run([sys.executable, "update_server.py"], env=env, check=True)
        
    except KeyboardInterrupt:
        print("\n服务器已停止")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 服务器启动失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 未知错误: {e}")
        return False

def show_help():
    """显示帮助信息"""
    print("ECBot 本地OTA测试服务器")
    print("\n用法:")
    print("  python start_local_server.py [选项]")
    print("\n选项:")
    print("  -h, --help     显示此帮助信息")
    print("  start          启动服务器（默认）")
    print("  check          检查服务器状态")
    print("\n示例:")
    print("  python start_local_server.py")
    print("  python start_local_server.py start")
    print("  python start_local_server.py check")

def check_server():
    """检查服务器状态"""
    try:
        import requests
        response = requests.get("http://127.0.0.1:8080/health", timeout=5)
        if response.status_code == 200:
            print("✓ 本地OTA服务器正在运行")
            print(f"  状态: {response.json()}")
            return True
        else:
            print(f"✗ 服务器响应异常: {response.status_code}")
            return False
    except ImportError:
        print("需要安装requests库来检查服务器状态")
        print("运行: pip install requests")
        return False
    except Exception as e:
        print(f"✗ 无法连接到本地OTA服务器: {e}")
        print("服务器可能未启动")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command in ["-h", "--help", "help"]:
            show_help()
        elif command == "check":
            check_server()
        elif command == "start":
            start_server()
        else:
            print(f"未知命令: {command}")
            show_help()
    else:
        start_server()
