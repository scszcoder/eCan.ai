#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 使用示例
展示如何使用重新整理后的 Playwright 系统进行各种操作
"""

from pathlib import Path

from .manager import get_playwright_manager, initialize_playwright_lazy
from .browser import PlaywrightBrowser, create_browser, with_browser
from .first_time_setup import run_first_time_setup, check_first_time_setup_needed
from .diagnostics import run_diagnostics, print_diagnostics
from .core.installer import install_playwright_with_progress

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


def example_first_time_setup():
    """首次安装示例"""
    print("\n=== 首次安装示例 ===")

    # 检查是否需要首次安装
    if check_first_time_setup_needed():
        print("检测到需要首次安装")

        # 运行安装向导
        def progress_callback(state):
            print(f"安装进度: 步骤 {state.current_step}/{state.total_steps} - {state.step_name}")
            if state.has_error:
                print(f"错误: {state.error_message}")

        success = run_first_time_setup(progress_callback=progress_callback)
        print(f"安装结果: {'成功' if success else '失败'}")
    else:
        print("Playwright 已经安装完成")


def example_diagnostics():
    """诊断工具示例"""
    print("\n=== 诊断工具示例 ===")

    # 运行诊断
    print("运行诊断检查...")
    report = run_diagnostics()

    print(f"诊断结果: {report['overall_status']}")
    print(f"检查项目: {report['summary']['total_checks']}")
    print(f"正常: {report['summary']['ok']}, 警告: {report['summary']['warnings']}, 错误: {report['summary']['errors']}")

    # 打印详细报告
    print("\n详细诊断报告:")
    print_diagnostics()


def example_installation_with_progress():
    """带进度的安装示例"""
    print("\n=== 带进度的安装示例 ===")

    from .core.utils import core_utils
    target_path = core_utils.get_app_data_path() / "ms-playwright-example"

    def progress_callback(progress):
        print(f"安装进度: {progress.current_step} ({progress.progress_percent}%)")
        if progress.error:
            print(f"安装错误: {progress.error.message}")

    print(f"开始安装到: {target_path}")
    success = install_playwright_with_progress(target_path, progress_callback)
    print(f"安装结果: {'成功' if success else '失败'}")


def main():
    """主函数：运行所有示例"""
    print("Playwright 重新整理后的使用示例")
    print("=" * 60)

    try:
        # 首先检查和安装
        example_first_time_setup()

        # 运行诊断
        example_diagnostics()

        # 原有示例
        example_basic_usage()
        example_browser_operations()
        example_decorator_usage()
        example_error_handling()
        example_status_monitoring()

        # 新增示例
        example_installation_with_progress()

        print("\n✅ 所有示例运行完成！")

    except Exception as e:
        logger.error(f"示例运行出错: {e}")
        print(f"❌ 示例运行出错: {e}")


if __name__ == "__main__":
    main()
