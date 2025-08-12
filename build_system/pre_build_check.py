#!/usr/bin/env python3
"""
构建前简单检查
检查是否有进程冲突，如果有就报错并结束构建
"""

import subprocess
import platform
import sys
from pathlib import Path

def check_running_processes():
    """检查是否有 eCan 进程正在运行"""
    print("[CHECK] 检查是否有 eCan 进程正在运行...")
    
    try:
        if platform.system() == "Windows":
            # Windows: 使用 tasklist
            result = subprocess.run([
                'tasklist', '/FI', 'IMAGENAME eq eCan.exe', '/FO', 'CSV'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # 检查是否有实际的进程（不只是标题行）
                process_lines = [line for line in lines[1:] if line and 'eCan.exe' in line]
                
                if process_lines:
                    print(f"[ERROR] 发现 {len(process_lines)} 个 eCan.exe 进程正在运行:")
                    for line in process_lines:
                        parts = line.split('","')
                        if len(parts) >= 2:
                            pid = parts[1].strip('"')
                            print(f"  - PID: {pid}")
                    return False
                else:
                    print("[SUCCESS] 没有发现 eCan 进程")
                    return True
            else:
                print("[WARNING] 无法检查进程状态")
                return True
                
        else:
            # macOS/Linux: 使用 ps
            result = subprocess.run([
                'ps', 'aux'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                ecan_processes = []
                for line in result.stdout.split('\n'):
                    if 'eCan' in line and 'ps aux' not in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            ecan_processes.append(parts[1])  # PID
                
                if ecan_processes:
                    print(f"[ERROR] 发现 {len(ecan_processes)} 个 eCan 进程正在运行:")
                    for pid in ecan_processes:
                        print(f"  - PID: {pid}")
                    return False
                else:
                    print("[SUCCESS] 没有发现 eCan 进程")
                    return True
            else:
                print("[WARNING] 无法检查进程状态")
                return True
                
    except Exception as e:
        print(f"[WARNING] 检查进程时出错: {e}")
        return True  # 检查失败时允许继续构建

def check_build_directories():
    """检查构建目录状态"""
    print("[CHECK] 检查构建目录状态...")
    
    directories = ['dist', 'build']
    issues = []
    
    for dir_name in directories:
        dir_path = Path(dir_name)
        if dir_path.exists():
            try:
                # 尝试在目录中创建测试文件
                test_file = dir_path / f"test_write_{dir_name}.tmp"
                test_file.write_text("test")
                test_file.unlink()
                print(f"[SUCCESS] {dir_name} 目录可写")
            except Exception as e:
                issues.append(f"{dir_name} 目录可能被占用: {e}")
        else:
            print(f"[INFO] {dir_name} 目录不存在（正常）")
    
    if issues:
        print("[WARNING] 发现目录访问问题:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    return True

def provide_solutions():
    """提供解决方案"""
    print("\n" + "="*60)
    print("[SOLUTIONS] 请按以下步骤解决问题:")
    print("="*60)
    
    if platform.system() == "Windows":
        print("1. 打开任务管理器 (Ctrl+Shift+Esc)")
        print("2. 在'进程'标签页中找到所有 'eCan.exe' 进程")
        print("3. 右键点击每个 eCan.exe 进程，选择'结束任务'")
        print("4. 或者在命令行运行: taskkill /F /IM eCan.exe")
    elif platform.system() == "Darwin":  # macOS
        print("1. 打开活动监视器 (Applications/Utilities/Activity Monitor)")
        print("2. 搜索 'eCan' 并强制退出所有相关进程")
        print("3. 或者在终端运行: pkill -f eCan")
    else:  # Linux
        print("1. 使用系统监视器或 htop 查看进程")
        print("2. 终止所有 eCan 相关进程")
        print("3. 或者在终端运行: pkill -f eCan")
    
    print("\n5. 如果目录被占用，手动删除以下目录:")
    print("   - dist/")
    print("   - build/")
    
    print("\n6. 然后重新运行构建: python build.py")
    print("="*60)

def run_pre_build_check():
    """运行构建前检查"""
    print("[PRECHECK] 开始构建前检查...")
    
    # 检查进程
    process_ok = check_running_processes()
    
    # 检查目录
    directory_ok = check_build_directories()
    
    if process_ok and directory_ok:
        print("[SUCCESS] 构建前检查通过")
        return True
    else:
        print("[ERROR] 构建前检查失败")
        provide_solutions()
        return False

def main():
    """主函数"""
    if run_pre_build_check():
        print("[INFO] 可以继续构建")
        return 0
    else:
        print("[ERROR] 请解决上述问题后重新运行构建")
        return 1

if __name__ == "__main__":
    sys.exit(main())
