#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 使用示例
展示如何使用 Playwright 管理器进行各种操作
"""

from pathlib import Path

from .manager import get_playwright_manager, initialize_playwright_lazy
from .browser import PlaywrightBrowser, create_browser, with_browser

from utils.logger_helper import logger_helper as logger


def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 1. 获取管理器实例
    manager = get_playwright_manager()
    print(f"管理器状态: {manager.get_status()}")
    
    # 2. 延迟初始化
    success = initialize_playwright_lazy()
    print(f"初始化结果: {success}")
    
    # 3. 获取状态
    status = manager.get_status()
    print(f"当前状态: {status}")


def example_browser_operations():
    """浏览器操作示例"""
    print("\n=== 浏览器操作示例 ===")
    
    # 使用上下文管理器自动管理资源
    with PlaywrightBrowser() as browser:
        # 启动浏览器
        if browser.launch_browser(headless=True):
            print("浏览器启动成功")
            
            # 创建上下文
            if browser.create_context():
                print("上下文创建成功")
                
                # 创建页面
                page = browser.create_page()
                if page:
                    print("页面创建成功")
                    
                    # 导航到网页
                    if browser.navigate_to("https://www.example.com", page):
                        print("导航成功")
                        
                        # 截图
                        screenshot_path = "example_screenshot.png"
                        if browser.take_screenshot(page, screenshot_path):
                            print(f"截图保存到: {screenshot_path}")
                        
                        # 获取页面内容
                        content = browser.get_page_content(page)
                        if content:
                            print(f"页面内容长度: {len(content)} 字符")
                    else:
                        print("导航失败")
                else:
                    print("页面创建失败")
            else:
                print("上下文创建失败")
        else:
            print("浏览器启动失败")


def example_decorator_usage():
    """装饰器使用示例"""
    print("\n=== 装饰器使用示例 ===")
    
    @with_browser
    def scrape_website(browser):
        """使用装饰器自动管理浏览器的函数"""
        page = browser.create_page()
        if page:
            browser.navigate_to("https://httpbin.org/json", page)
            content = browser.get_page_content(page)
            return content
        return None
    
    # 调用函数，浏览器会自动管理
    result = scrape_website()
    if result:
        print(f"抓取结果: {result[:100]}...")
    else:
        print("抓取失败")


def example_error_handling():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    manager = get_playwright_manager()
    
    # 检查状态
    status = manager.get_status()
    if not status["initialized"]:
        print("Playwright 未初始化，尝试初始化...")
        
        success = manager.lazy_init()
        if success:
            print("初始化成功")
        else:
            print("初始化失败，尝试强制重新初始化...")
            
            # 强制重新初始化
            success = manager.force_reinitialize()
            if success:
                print("强制重新初始化成功")
            else:
                print("强制重新初始化失败")
    
    # 获取环境信息
    env_info = manager.get_environment_info()
    print(f"环境信息: {env_info}")


def example_status_monitoring():
    """状态监控示例"""
    print("\n=== 状态监控示例 ===")
    
    manager = get_playwright_manager()
    
    # 获取详细状态
    status = manager.get_status()
    print("状态详情:")
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    # 验证安装
    is_valid = manager.validate_installation()
    print(f"安装验证: {'✅ 有效' if is_valid else '❌ 无效'}")


def main():
    """主函数：运行所有示例"""
    print("Playwright 管理器使用示例")
    print("=" * 50)
    
    try:
        example_basic_usage()
        example_browser_operations()
        example_decorator_usage()
        example_error_handling()
        example_status_monitoring()
        
        print("\n所有示例运行完成！")
        
    except Exception as e:
        logger.error(f"示例运行出错: {e}")
        print(f"示例运行出错: {e}")


if __name__ == "__main__":
    main()
