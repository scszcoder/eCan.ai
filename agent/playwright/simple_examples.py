#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 简化版使用示例
展示如何使用简化后的 Playwright 系统
"""

def example_basic_usage():
    """基本使用示例"""
    print("\n=== 基本使用示例 ===")
    
    # 导入简化的函数
    from agent.playwright.core.helpers import (
        is_first_time_use,
        auto_install_playwright,
        quick_diagnostics
    )
    
    # 检查是否首次使用
    if is_first_time_use():
        print("🎯 检测到首次使用")
        
        # 自动安装
        print("🚀 开始自动安装...")
        success = auto_install_playwright()
        if success:
            print("✅ 安装成功！")
        else:
            print("❌ 安装失败，运行诊断...")
            quick_diagnostics()
    else:
        print("✅ Playwright 已安装")


def example_with_decorator():
    """装饰器使用示例"""
    print("\n=== 装饰器使用示例 ===")
    
    from agent.playwright.decorators import ensure_playwright_initialized
    
    @ensure_playwright_initialized
    def my_browser_function():
        """使用 Playwright 的函数"""
        print("🌐 执行浏览器操作...")
        # 这里会自动确保 Playwright 已初始化
        return "浏览器操作完成"
    
    try:
        result = my_browser_function()
        print(f"结果: {result}")
    except Exception as e:
        print(f"执行失败: {e}")


def example_error_handling():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    from agent.playwright.core.helpers import friendly_error_message
    
    # 模拟各种错误
    test_errors = [
        FileNotFoundError("playwright browser not found"),
        PermissionError("access denied"),
        ConnectionError("network timeout"),
        OSError("disk space insufficient")
    ]
    
    for error in test_errors:
        friendly_msg = friendly_error_message(error, "test")
        print(f"\n原始错误: {error}")
        print(f"友好提示: {friendly_msg}")


def example_diagnostics():
    """诊断示例"""
    print("\n=== 诊断示例 ===")
    
    from agent.playwright.core.helpers import quick_diagnostics
    
    # 运行快速诊断
    quick_diagnostics()


def example_manual_install():
    """手动安装示例"""
    print("\n=== 手动安装示例 ===")
    
    from agent.playwright.core.helpers import auto_install_playwright
    from pathlib import Path
    
    # 指定安装路径
    custom_path = Path.home() / "my_playwright_browsers"
    
    print(f"安装到自定义路径: {custom_path}")
    success = auto_install_playwright(custom_path)
    
    if success:
        print("✅ 自定义路径安装成功")
    else:
        print("❌ 自定义路径安装失败")


def main():
    """主函数：运行所有简化示例"""
    print("Playwright 简化版使用示例")
    print("=" * 50)
    
    try:
        example_basic_usage()
        example_with_decorator()
        example_error_handling()
        example_diagnostics()
        example_manual_install()
        
        print("\n✅ 所有示例运行完成！")
        
    except Exception as e:
        print(f"❌ 示例运行出错: {e}")


if __name__ == "__main__":
    main()
