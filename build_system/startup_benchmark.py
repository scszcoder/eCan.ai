#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan Startup Benchmark Tool
测量不同构建模式的启动时间
"""

import os
import sys
import time
import subprocess
import statistics
from pathlib import Path
from typing import List, Dict, Any


class StartupBenchmark:
    """启动时间基准测试"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.dist_dir = project_root / "dist"
        
    def find_executables(self) -> Dict[str, Path]:
        """查找可执行文件"""
        executables = {}
        
        # 查找 onedir 模式
        if sys.platform == "win32":
            onedir_exe = self.dist_dir / "eCan" / "eCan.exe"
            onefile_exe = self.dist_dir / "eCan.exe"
        elif sys.platform == "darwin":
            onedir_exe = self.dist_dir / "eCan.app" / "Contents" / "MacOS" / "eCan"
            onefile_exe = self.dist_dir / "eCan"
        else:  # Linux
            onedir_exe = self.dist_dir / "eCan" / "eCan"
            onefile_exe = self.dist_dir / "eCan"
        
        if onedir_exe.exists():
            executables["onedir"] = onedir_exe
            
        if onefile_exe.exists():
            executables["onefile"] = onefile_exe
            
        return executables
    
    def measure_startup_time(self, exe_path: Path, runs: int = 5) -> Dict[str, float]:
        """测量启动时间"""
        times = []
        
        print(f"📊 测量 {exe_path.name} 启动时间 ({runs} 次运行)...")
        
        for i in range(runs):
            print(f"  运行 {i+1}/{runs}...", end=" ")
            
            start_time = time.time()
            
            try:
                # 启动程序并立即退出
                process = subprocess.Popen(
                    [str(exe_path), "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                # 等待程序启动完成
                stdout, stderr = process.communicate(timeout=30)
                end_time = time.time()
                
                startup_time = end_time - start_time
                times.append(startup_time)
                
                print(f"{startup_time:.2f}s")
                
            except subprocess.TimeoutExpired:
                print("超时")
                process.kill()
                continue
            except Exception as e:
                print(f"错误: {e}")
                continue
                
        if not times:
            return {"error": "所有测试都失败了"}
            
        return {
            "times": times,
            "average": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "std_dev": statistics.stdev(times) if len(times) > 1 else 0
        }
    
    def compare_modes(self) -> Dict[str, Any]:
        """比较不同模式的启动时间"""
        executables = self.find_executables()
        
        if not executables:
            return {"error": "没有找到可执行文件"}
            
        results = {}
        
        for mode, exe_path in executables.items():
            print(f"\n🔍 测试 {mode.upper()} 模式:")
            print(f"   可执行文件: {exe_path}")
            print(f"   文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
            
            results[mode] = self.measure_startup_time(exe_path)
            
        return results
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """生成报告"""
        report = []
        report.append("=" * 60)
        report.append("eCan 启动时间基准测试报告")
        report.append("=" * 60)
        
        if "error" in results:
            report.append(f"❌ 错误: {results['error']}")
            return "\n".join(report)
            
        # 按平均启动时间排序
        sorted_results = sorted(
            [(mode, data) for mode, data in results.items() if "error" not in data],
            key=lambda x: x[1]["average"]
        )
        
        report.append("\n📊 启动时间统计:")
        report.append("-" * 40)
        
        for mode, data in sorted_results:
            report.append(f"\n{mode.upper()} 模式:")
            report.append(f"  平均时间: {data['average']:.2f}s")
            report.append(f"  中位数:   {data['median']:.2f}s")
            report.append(f"  最快:     {data['min']:.2f}s")
            report.append(f"  最慢:     {data['max']:.2f}s")
            report.append(f"  标准差:   {data['std_dev']:.2f}s")
            
        # 性能比较
        if len(sorted_results) > 1:
            fastest = sorted_results[0]
            slowest = sorted_results[-1]
            
            improvement = (slowest[1]["average"] - fastest[1]["average"]) / slowest[1]["average"] * 100
            
            report.append(f"\n🚀 性能比较:")
            report.append(f"  最快模式: {fastest[0].upper()} ({fastest[1]['average']:.2f}s)")
            report.append(f"  最慢模式: {slowest[0].upper()} ({slowest[1]['average']:.2f}s)")
            report.append(f"  性能提升: {improvement:.1f}%")
            
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)


def main():
    """主函数"""
    project_root = Path.cwd()
    benchmark = StartupBenchmark(project_root)
    
    print("🚀 eCan 启动时间基准测试")
    print("=" * 40)
    
    results = benchmark.compare_modes()
    report = benchmark.generate_report(results)
    
    print(report)
    
    # 保存报告
    report_file = project_root / "startup_benchmark_report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 报告已保存到: {report_file}")


if __name__ == "__main__":
    main()
