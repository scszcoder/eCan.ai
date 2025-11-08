#!/usr/bin/env python3
"""
Sparkle和winSparkle依赖管理脚本
- 用于下载和管理Sparkle/winSparkle框架依赖
- 注意：Sparkle和winSparkle不提供CLI工具，只提供框架/DLL
- 本脚本主要用于依赖管理，而非构建CLI工具
- 默认处于禁用状态：需设置环境变量 ECBOT_ALLOW_BUILD_SCRIPTS=1 才会执行
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

class SparkleManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.build_dir = self.project_root / "build" / "sparkle"
        self.build_dir.mkdir(parents=True, exist_ok=True)
        
    def setup_macos_sparkle(self):
        """设置macOS Sparkle依赖"""
        print("Setting up macOS Sparkle dependencies...")
        
        # 下载Sparkle框架
        self._download_sparkle_framework()
        
        # 创建集成代码
        self._create_sparkle_integration()
        
        print("macOS Sparkle setup completed")
    
    def _download_sparkle_framework(self):
        """下载Sparkle框架"""
        framework_dir = self.build_dir / "Sparkle.framework"
        
        if not framework_dir.exists():
            print("Downloading Sparkle framework...")
            # 从GitHub Releases下载最新版本
            try:
                subprocess.run([
                    "curl", "-L", "-o", "sparkle.tar.xz",
                    "https://github.com/sparkle-project/Sparkle/releases/latest/download/Sparkle-for-Swift-Package-Manager.zip"
                ], cwd=self.build_dir, check=True)
                
                # 解压
                subprocess.run(["unzip", "sparkle.tar.xz"], cwd=self.build_dir, check=True)
                print("Sparkle framework downloaded successfully")
            except subprocess.CalledProcessError:
                print("Failed to download Sparkle framework")
    
    def _create_sparkle_integration(self):
        """创建Sparkle集成代码"""
        integration_file = self.build_dir / "sparkle_integration.swift"
        
        # 创建基本的Sparkle集成代码
        swift_code = '''import Cocoa
import Sparkle

// ECBot Sparkle集成
class ECBotSparkleUpdater {
    private var updater: SPUUpdater?
    
    init() {
        // 初始化Sparkle更新器
        updater = SPUUpdater(hostBundle: Bundle.main,
                           applicationBundle: Bundle.main,
                           userDriver: SPUStandardUserDriver(hostBundle: Bundle.main, delegate: nil),
                           delegate: nil)
    }
    
    func checkForUpdates() {
        updater?.checkForUpdates()
    }
    
    func checkForUpdatesInBackground() {
        updater?.checkForUpdatesInBackground()
    }
}
'''
        
        with open(integration_file, 'w') as f:
            f.write(swift_code)
        
        print(f"Created Sparkle integration code: {integration_file}")
    
    def _install_sparkle_to_app(self):
        """将Sparkle框架安装到应用包中"""
        app_frameworks_dir = self.project_root / "dist" / "ECBot.app" / "Contents" / "Frameworks"
        sparkle_framework = self.build_dir / "Sparkle.framework"
        
        if sparkle_framework.exists() and app_frameworks_dir.exists():
            import shutil
            target_framework = app_frameworks_dir / "Sparkle.framework"
            if target_framework.exists():
                shutil.rmtree(target_framework)
            shutil.copytree(sparkle_framework, target_framework)
            print(f"Installed Sparkle framework to: {target_framework}")
        else:
            print("Warning: Sparkle framework or app bundle not found")
    
    def setup_windows_winsparkle(self):
        """设置Windows winSparkle依赖"""
        print("Setting up Windows winSparkle dependencies...")
        
        # 下载winSparkle
        self._download_winsparkle()
        
        # 创建集成代码
        self._create_winsparkle_integration()
        
        print("Windows winSparkle setup completed")
    
    def _create_winsparkle_vs_project(self):
        """创建winSparkle Visual Studio项目"""
        project_dir = self.build_dir / "winsparkle_project"
        project_dir.mkdir(exist_ok=True)
        
        # 创建项目文件
        project_file = project_dir / "WinSparkleIntegration.vcxproj"
        if not project_file.exists():
            # 创建基本的项目文件
            self._create_vs_project_file(project_file)
    
    def _create_vs_project_file(self, project_file):
        """创建Visual Studio项目文件"""
        content = '''<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup Label="ProjectConfigurations">
    <ProjectConfiguration Include="Release|x64">
      <Configuration>Release</Configuration>
      <Platform>x64</Platform>
    </ProjectConfiguration>
  </ItemGroup>
  <PropertyGroup Label="Globals">
    <VCProjectVersion>16.0</VCProjectVersion>
    <ProjectGuid>{12345678-1234-1234-1234-123456789ABC}</ProjectGuid>
    <RootNamespace>WinSparkleIntegration</RootNamespace>
    <WindowsTargetPlatformVersion>10.0</WindowsTargetPlatformVersion>
  </PropertyGroup>
  <Import Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props" />
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'" Label="Configuration">
    <ConfigurationType>Application</ConfigurationType>
    <UseDebugLibraries>false</UseDebugLibraries>
    <PlatformToolset>v143</PlatformToolset>
    <WholeProgramOptimization>true</WholeProgramOptimization>
    <CharacterSet>Unicode</CharacterSet>
  </PropertyGroup>
  <Import Project="$(VCTargetsPath)\\Microsoft.Cpp.props" />
  <ImportGroup Label="ExtensionSettings">
  </ImportGroup>
  <ImportGroup Label="Shared">
  </ImportGroup>
  <ImportGroup Label="PropertySheets" Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <Import Project="$(UserRootDir)\\Microsoft.Cpp.$(Platform).user.props" Condition="exists('$(UserRootDir)\\Microsoft.Cpp.$(Platform).user.props')" Label="LocalAppDataPlatform" />
  </ImportGroup>
  <PropertyGroup Label="UserMacros" />
  <PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <LinkIncremental>false</LinkIncremental>
  </PropertyGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <ClCompile>
      <WarningLevel>Level3</WarningLevel>
      <FunctionLevelLinking>true</FunctionLevelLinking>
      <IntrinsicFunctions>true</IntrinsicFunctions>
      <SDLCheck>true</SDLCheck>
      <PreprocessorDefinitions>NDEBUG;_CONSOLE;%(PreprocessorDefinitions)</PreprocessorDefinitions>
      <ConformanceMode>true</ConformanceMode>
      <PrecompiledHeader>NotUsing</PrecompiledHeader>
      <PrecompiledHeaderFile>
      </PrecompiledHeaderFile>
    </ClCompile>
    <Link>
      <SubSystem>Console</SubSystem>
      <EnableCOMDATFolding>true</EnableCOMDATFolding>
      <OptimizeReferences>true</OptimizeReferences>
      <GenerateDebugInformation>true</GenerateDebugInformation>
    </Link>
  </ItemDefinitionGroup>
  <ItemGroup>
    <ClCompile Include="winsparkle_integration.cpp" />
  </ItemGroup>
  <Import Project="$(VCTargetsPath)\\Microsoft.Cpp.targets" />
  <ImportGroup Label="ExtensionTargets">
  </ImportGroup>
</Project>'''
        
        with open(project_file, 'w') as f:
            f.write(content)
    
    def _download_winsparkle(self):
        """下载winSparkle DLL"""
        winsparkle_dir = self.build_dir / "winsparkle"
        
        if not winsparkle_dir.exists():
            print("Downloading winSparkle...")
            try:
                # 从GitHub Releases下载
                subprocess.run([
                    "curl", "-L", "-o", "winsparkle.zip",
                    "https://github.com/winsparkle/winsparkle/releases/latest/download/winsparkle.zip"
                ], cwd=self.build_dir, check=True)
                
                # 解压
                subprocess.run(["powershell", "Expand-Archive", "winsparkle.zip", "winsparkle"], 
                             cwd=self.build_dir, check=True)
                print("winSparkle downloaded successfully")
            except subprocess.CalledProcessError:
                print("Failed to download winSparkle")
    
    def _create_winsparkle_integration(self):
        """创建winSparkle集成代码"""
        integration_file = self.build_dir / "winsparkle_integration.cpp"
        
        # 创建基本的winSparkle集成代码
        cpp_code = '''#include <windows.h>
#include "winsparkle.h"

// ECBot winSparkle集成
class ECBotWinSparkleUpdater {
public:
    ECBotWinSparkleUpdater() {
        // 初始化winSparkle
        win_sparkle_set_appcast_url(L"https://your-server.com/appcast.xml");
        win_sparkle_set_app_details(L"ECBot", L"ECBot", L"1.0.0");
        win_sparkle_init();
    }
    
    ~ECBotWinSparkleUpdater() {
        win_sparkle_cleanup();
    }
    
    void checkForUpdates() {
        win_sparkle_check_update_with_ui();
    }
    
    void checkForUpdatesInBackground() {
        win_sparkle_check_update_without_ui();
    }
};
'''
        
        with open(integration_file, 'w') as f:
            f.write(cpp_code)
        
        print(f"Created winSparkle integration code: {integration_file}")
    
    def install_dependencies(self):
        """安装依赖"""
        print("Installing dependencies...")
        
        if platform.system() == "Darwin":
            self._install_macos_dependencies()
        elif platform.system() == "Windows":
            self._install_windows_dependencies()
    
    def _install_macos_dependencies(self):
        """安装macOS依赖"""
        # 安装Sparkle框架
        subprocess.run(["brew", "install", "sparkle"])
        
        # 或者使用CocoaPods
        # subprocess.run(["pod", "install"])
    
    def _install_windows_dependencies(self):
        """安装Windows依赖"""
        # 下载winSparkle预编译版本
        self._download_winsparkle()
        
        # 复制DLL到应用目录
        self._install_winsparkle_to_app()
    
    def _install_winsparkle_to_app(self):
        """将winSparkle DLL安装到应用目录"""
        app_dir = self.project_root / "dist"
        winsparkle_dll = self.build_dir / "winsparkle" / "winsparkle.dll"
        
        if winsparkle_dll.exists() and app_dir.exists():
            import shutil
            target_dll = app_dir / "winsparkle.dll"
            shutil.copy2(winsparkle_dll, target_dll)
            print(f"Installed winSparkle DLL to: {target_dll}")
        else:
            print("Warning: winSparkle DLL or app directory not found")
    
    def setup_all(self):
        """设置所有平台的OTA依赖"""
        print("Setting up OTA update dependencies...")
        
        self.install_dependencies()
        
        if platform.system() == "Darwin":
            self.setup_macos_sparkle()
        elif platform.system() == "Windows":
            self.setup_windows_winsparkle()
        else:
            print("Unsupported platform for OTA updates")
    
    def clean(self):
        """清理构建文件"""
        import shutil
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        print("Build directory cleaned")


def main():
    # 默认禁用：仅在明确允许时执行
    if os.environ.get("ECBOT_ALLOW_BUILD_SCRIPTS", "").lower() not in ("1", "true", "yes", "on"):
        print("[sparkle_build] This is an example/placeholder build script and is disabled by default.\n"
              "Set ECBOT_ALLOW_BUILD_SCRIPTS=1 to enable execution.")
        return

    manager = SparkleManager()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "setup":
            manager.setup_all()
        elif command == "macos":
            manager.setup_macos_sparkle()
        elif command == "windows":
            manager.setup_windows_winsparkle()
        elif command == "clean":
            manager.clean()
        elif command == "deps":
            manager.install_dependencies()
        else:
            print("Unknown command:", command)
            print("Available commands: setup, macos, windows, clean, deps")
    else:
        manager.setup_all()


if __name__ == "__main__":
    main()