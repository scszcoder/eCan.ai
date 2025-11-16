#!/usr/bin/env python3
"""
自动下载并安装 Inno Setup 简体中文语言包

这个脚本会：
1. 下载 ChineseSimplified.isl 语言包
2. 自动复制到 Inno Setup 的 Languages 目录
3. 验证安装是否成功

Usage:
    python setup_inno_chinese.py
"""

import os
import sys
import shutil
from pathlib import Path
import urllib.request
import urllib.error


def print_step(message: str):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}")


def print_success(message: str):
    """打印成功信息"""
    print(f"✓ {message}")


def print_error(message: str):
    """打印错误信息"""
    print(f"✗ {message}", file=sys.stderr)


def print_warning(message: str):
    """打印警告信息"""
    print(f"⚠ {message}")


def find_inno_setup_dir() -> Path:
    """查找 Inno Setup 安装目录"""
    possible_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6"),
        Path(r"C:\Program Files\Inno Setup 6"),
        Path(r"C:\Program Files (x86)\Inno Setup 5"),
        Path(r"C:\Program Files\Inno Setup 5"),
    ]
    
    for path in possible_paths:
        if path.exists() and (path / "ISCC.exe").exists():
            return path
    
    return None


def download_language_pack(script_dir: Path) -> Path:
    """下载语言包"""
    print_step("步骤 1: 下载简体中文语言包")

    # 目标目录和文件
    target_dir = script_dir / "inno_setup_languages"
    target_dir.mkdir(parents=True, exist_ok=True)

    url = (
        "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/"
        "Languages/Unofficial/ChineseSimplified.isl"
    )
    lang_file = target_dir / "ChineseSimplified.isl"

    print(f"下载地址: {url}")
    print(f"保存路径: {lang_file}")

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()

        if not data:
            print_error("下载内容为空")
            sys.exit(1)

        lang_file.write_bytes(data)
        size_kb = len(data) / 1024.0
        print_success(f"语言包已下载到: {lang_file} ({size_kb:.1f} KB)")
        return lang_file

    except urllib.error.URLError as e:
        print_error(f"下载失败（网络错误）: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"下载过程出错: {e}")
        sys.exit(1)


def copy_to_inno_setup(source_file: Path, inno_dir: Path) -> bool:
    """复制语言包到 Inno Setup 目录"""
    print_step("步骤 2: 安装语言包到 Inno Setup")
    
    languages_dir = inno_dir / "Languages"
    if not languages_dir.exists():
        print_error(f"Inno Setup Languages 目录不存在: {languages_dir}")
        return False
    
    # 目标文件（注意扩展名改为 .isl）
    target_file = languages_dir / "ChineseSimplified.isl"
    
    print(f"源文件: {source_file}")
    print(f"目标位置: {target_file}")
    
    try:
        # 尝试直接复制
        shutil.copy2(source_file, target_file)
        print_success(f"语言包已安装到: {target_file}")
        return True
        
    except PermissionError:
        print_warning("需要管理员权限才能复制文件到 Program Files")
        print("\n请选择以下方式之一：")
        print("1. 以管理员身份重新运行此脚本")
        print("2. 手动复制文件（需要管理员权限）：")
        print(f"   源文件: {source_file}")
        print(f"   目标位置: {target_file}")
        print("\n手动复制命令（在管理员 PowerShell 中执行）：")
        print(f'   Copy-Item "{source_file}" "{target_file}" -Force')
        return False
        
    except Exception as e:
        print_error(f"复制文件时出错: {e}")
        return False


def verify_installation(inno_dir: Path) -> bool:
    """验证语言包是否安装成功"""
    print_step("步骤 3: 验证安装")
    
    target_file = inno_dir / "Languages" / "ChineseSimplified.isl"
    
    if not target_file.exists():
        print_error(f"语言包文件不存在: {target_file}")
        return False
    
    # 检查文件大小
    file_size = target_file.stat().st_size
    if file_size < 1000:
        print_warning(f"语言包文件似乎太小: {file_size} bytes")
        return False
    
    # 检查文件内容
    try:
        with open(target_file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            
        # 验证必要的部分
        required_sections = ['[LangOptions]', '[Messages]', 'LanguageID=']
        missing = [s for s in required_sections if s not in content]
        
        if missing:
            print_error(f"语言包文件缺少必要内容: {missing}")
            return False
        
        print_success(f"语言包已成功安装 ({file_size} bytes)")
        print(f"  文件位置: {target_file}")
        
        # 尝试提取语言信息
        import re
        if match := re.search(r'LanguageName=(.+)', content):
            lang_name = match.group(1).strip()
            print(f"  语言名称: {lang_name}")
        
        return True
        
    except Exception as e:
        print_error(f"验证文件时出错: {e}")
        return False


def main():
    """主函数"""
    print_step("Inno Setup 简体中文语言包自动安装工具")
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    print(f"工作目录: {script_dir}")
    
    # 查找 Inno Setup 安装目录
    print("\n正在查找 Inno Setup 安装目录...")
    inno_dir = find_inno_setup_dir()
    
    if not inno_dir:
        print_error("未找到 Inno Setup 安装目录")
        print("\n请确认 Inno Setup 已安装在以下位置之一：")
        print("  - C:\\Program Files (x86)\\Inno Setup 6")
        print("  - C:\\Program Files\\Inno Setup 6")
        sys.exit(1)
    
    print_success(f"找到 Inno Setup: {inno_dir}")
    
    # 下载语言包
    lang_file = download_language_pack(script_dir)
    
    # 复制到 Inno Setup 目录
    if not copy_to_inno_setup(lang_file, inno_dir):
        print_error("\n安装失败")
        sys.exit(1)
    
    # 验证安装
    if not verify_installation(inno_dir):
        print_error("\n验证失败")
        sys.exit(1)
    
    # 成功
    print_step("安装完成")
    print_success("简体中文语言包已成功安装到 Inno Setup")
    print("\n现在可以重新运行构建命令，安装器将支持中英文双语言界面。")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(1)
    except Exception as e:
        print_error(f"\n未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
