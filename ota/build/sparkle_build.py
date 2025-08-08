#!/usr/bin/env python3
"""
Sparkle和winSparkle构建脚本
用于构建OTA更新组件
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

class SparkleBuilder:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.build_dir = self.project_root / "build" / "sparkle"
        self.build_dir.mkdir(parents=True, exist_ok=True)
        
    def build_macos_sparkle(self):
        """构建macOS Sparkle组件"""
        print("Building macOS Sparkle components...")
        
        # 创建Xcode项目
        self._create_sparkle_xcode_project()
        
        # 构建Sparkle框架
        self._build_sparkle_framework()
        
        # 构建命令行工具
        self._build_sparkle_cli()
        
        print("macOS Sparkle build completed")
    
    def _create_sparkle_xcode_project(self):
        """创建Sparkle Xcode项目"""
        project_dir = self.build_dir / "sparkle_project"
        project_dir.mkdir(exist_ok=True)
        
        # 创建项目文件
        project_file = project_dir / "SparkleIntegration.xcodeproj"
        if not project_file.exists():
            # 使用xcodebuild创建项目
            subprocess.run([
                "xcodebuild", "-project", str(project_file),
                "-target", "SparkleIntegration",
                "-configuration", "Release"
            ], cwd=project_dir)
    
    def _build_sparkle_framework(self):
        """构建Sparkle框架"""
        framework_dir = self.build_dir / "Sparkle.framework"
        
        # 下载Sparkle框架（如果不存在）
        if not framework_dir.exists():
            print("Downloading Sparkle framework...")
            # 这里应该从官方源下载Sparkle框架
            # 或者使用CocoaPods/Swift Package Manager
    
    def _build_sparkle_cli(self):
        """构建Sparkle命令行工具"""
        cli_source = self.project_root / "ota" / "platforms" / "sparkle_integration.swift"
        cli_output = self.build_dir / "sparkle-cli"
        
        # 编译Swift文件
        subprocess.run([
            "swiftc", str(cli_source),
            "-o", str(cli_output),
            "-framework", "Sparkle"
        ])
    
    def build_windows_winsparkle(self):
        """构建Windows winSparkle组件"""
        print("Building Windows winSparkle components...")
        
        # 创建Visual Studio项目
        self._create_winsparkle_vs_project()
        
        # 构建winSparkle DLL
        self._build_winsparkle_dll()
        
        # 构建命令行工具
        self._build_winsparkle_cli()
        
        print("Windows winSparkle build completed")
    
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
    
    def _build_winsparkle_dll(self):
        """构建winSparkle DLL"""
        dll_source = self.project_root / "ota" / "platforms" / "winsparkle_integration.cpp"
        dll_output = self.build_dir / "winsparkle.dll"
        
        # 使用MSVC编译器
        subprocess.run([
            "cl", "/LD", str(dll_source),
            "/Fe:" + str(dll_output),
            "/I", "winsparkle/include",
            "winsparkle/lib/winsparkle.lib"
        ])
    
    def _build_winsparkle_cli(self):
        """构建winSparkle命令行工具"""
        cli_source = self.project_root / "ota" / "platforms" / "winsparkle_integration.cpp"
        cli_output = self.build_dir / "winsparkle-cli.exe"
        
        # 编译为可执行文件
        subprocess.run([
            "cl", str(cli_source),
            "/Fe:" + str(cli_output),
            "/I", "winsparkle/include",
            "winsparkle/lib/winsparkle.lib"
        ])
    
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
        # 下载winSparkle
        winsparkle_dir = self.build_dir / "winsparkle"
        if not winsparkle_dir.exists():
            print("Downloading winSparkle...")
            # 从GitHub下载winSparkle
            subprocess.run([
                "git", "clone", "https://github.com/winsparkle/winsparkle.git",
                str(winsparkle_dir)
            ])
    
    def build_all(self):
        """构建所有平台"""
        print("Building OTA update components...")
        
        self.install_dependencies()
        
        if platform.system() == "Darwin":
            self.build_macos_sparkle()
        elif platform.system() == "Windows":
            self.build_windows_winsparkle()
        else:
            print("Unsupported platform for OTA updates")
    
    def clean(self):
        """清理构建文件"""
        import shutil
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        print("Build directory cleaned")


def main():
    builder = SparkleBuilder()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "build":
            builder.build_all()
        elif command == "macos":
            builder.build_macos_sparkle()
        elif command == "windows":
            builder.build_windows_winsparkle()
        elif command == "clean":
            builder.clean()
        elif command == "deps":
            builder.install_dependencies()
        else:
            print("Unknown command:", command)
            print("Available commands: build, macos, windows, clean, deps")
    else:
        builder.build_all()


if __name__ == "__main__":
    main() 