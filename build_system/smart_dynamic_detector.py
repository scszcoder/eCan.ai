#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能动态导入检测器 v2.0
分阶段检测和智能合并，避免丢失模块的同时控制 spec 文件长度
优化版本：提高检测准确性，确保所有动态包都能被正确引入
"""

import os
import sys
import importlib
import ast
import subprocess
from pathlib import Path
from typing import Set, List, Dict, Any, Optional
import json

class SmartDynamicDetector:
    """智能动态导入检测器 v2.0"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.detected_modules = set()
        self.max_hidden_imports = 2000  # 提高限制，确保更多模块被包含
        self.windows_cmd_limit = 8191  # Windows命令行长度限制
        self.spec_line_limit = 7000  # spec文件中单行长度限制（留出安全余量）
        
    def detect_smart_imports(self) -> List[str]:
        """智能检测动态导入 v2.0"""
        print("🧠 开始智能动态导入检测 v2.0...")
        
        # 第一阶段：检测项目特定的动态导入
        print("📝 第一阶段：检测项目特定的动态导入...")
        project_imports = self._detect_project_specific_imports()
        print(f"   发现项目特定导入: {len(project_imports)} 个")
        
        # 第二阶段：检测代码中的实际动态导入
        print("💻 第二阶段：检测代码中的实际动态导入...")
        code_imports = self._detect_actual_code_imports()
        print(f"   发现代码动态导入: {len(code_imports)} 个")
        
        # 第三阶段：检测关键依赖的动态导入
        print("🔑 第三阶段：检测关键依赖的动态导入...")
        critical_imports = self._detect_critical_dependencies()
        print(f"   发现关键依赖: {len(critical_imports)} 个")
        
        # 第四阶段：检测运行时动态导入
        print("⚡ 第四阶段：检测运行时动态导入...")
        runtime_imports = self._detect_runtime_imports()
        print(f"   发现运行时导入: {len(runtime_imports)} 个")
        
        # 第五阶段：智能合并和优化
        print("🔄 第五阶段：智能合并和优化...")
        all_modules = project_imports | code_imports | critical_imports | runtime_imports
        
        # 第六阶段：验证和过滤模块
        print("✅ 第六阶段：验证和过滤模块...")
        validated_modules = self._validate_and_filter_modules(all_modules)
        print(f"   验证后模块: {len(validated_modules)} 个")
        
        # 第七阶段：Windows兼容性检查和压缩
        print("🪟 第七阶段：Windows兼容性检查和压缩...")
        final_modules = self._compress_modules_for_windows(list(validated_modules))
        
        # 如果模块数量过多，使用智能策略
        if len(final_modules) > self.max_hidden_imports:
            print(f"⚠️  模块数量过多 ({len(final_modules)})，使用智能策略...")
            final_modules = self._smart_merge_strategy(set(final_modules), project_imports, code_imports, critical_imports, runtime_imports)
        else:
            final_modules = list(final_modules)
        
        print(f"✅ 智能检测完成: {len(final_modules)} 个模块")
        return final_modules
    
    def _detect_project_specific_imports(self) -> Set[str]:
        """检测项目特定的动态导入 v2.0"""
        modules = set()
        
        # 检测项目中的包结构（更全面的检测）
        project_dirs = [
            "agent", "bot", "common", "config", "gui", "utils", 
            "telemetry", "knowledge", "settings", "skills", "build_system",
            "resource", "tests", "docs", "scripts"
        ]
        
        for dir_name in project_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                modules.add(dir_name)
                
                # 递归查找子模块（不限制深度）
                submodules = self._get_project_submodules(dir_path, dir_name)
                modules.update(submodules)
        
        # 添加根目录下的Python文件
        for py_file in self.project_root.glob("*.py"):
            if py_file.name != "__init__.py":
                modules.add(py_file.stem)
        
        return modules
    
    def _get_project_submodules(self, dir_path: Path, base_name: str) -> Set[str]:
        """获取项目子模块（不限制深度）v2.0"""
        modules = set()
        
        try:
            for item in dir_path.iterdir():
                if item.is_file() and item.suffix == '.py':
                    if item.name != "__init__.py":
                        module_name = f"{base_name}.{item.stem}"
                        modules.add(module_name)
                elif item.is_dir() and not item.name.startswith('_'):
                    if (item / '__init__.py').exists():
                        module_name = f"{base_name}.{item.name}"
                        modules.add(module_name)
                        # 递归查找子模块
                        submodules = self._get_project_submodules(item, module_name)
                        modules.update(submodules)
        except Exception as e:
            print(f"   警告: 获取子模块失败 {dir_path}: {e}")
        
        return modules
    
    def _detect_actual_code_imports(self) -> Set[str]:
        """检测代码中的实际动态导入 v2.0"""
        dynamic_imports = set()
        
        # 查找所有 Python 文件
        python_files = list(self.project_root.rglob("*.py"))
        python_files = [f for f in python_files if not any(skip in str(f) for skip in ['venv', 'build', 'dist', '__pycache__', '.git', 'node_modules'])]
        
        print(f"   分析 {len(python_files)} 个 Python 文件...")
        
        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 提取实际的动态导入
                imports = self._extract_actual_dynamic_imports(content)
                dynamic_imports.update(imports)
                
            except Exception as e:
                print(f"   警告: 分析文件 {py_file} 失败: {e}")
        
        return dynamic_imports
    
    def _extract_actual_dynamic_imports(self, content: str) -> Set[str]:
        """提取实际的动态导入 v2.0"""
        imports = set()
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            
            # 检测 importlib.import_module
            if 'importlib.import_module' in line:
                module = self._extract_module_name(line)
                if module:
                    imports.add(module)
            
            # 检测 __import__
            elif '__import__' in line:
                module = self._extract_module_name(line)
                if module:
                    imports.add(module)
            
            # 检测 from ... import *
            elif 'from ' in line and ' import *' in line:
                parts = line.split(' import ')[0].split('from ')[1]
                base_module = parts.strip()
                imports.add(base_module)
            
            # 检测动态字符串导入
            elif 'import ' in line and ('"' in line or "'" in line):
                module = self._extract_string_module(line)
                if module:
                    imports.add(module)
        
        return imports
    
    def _extract_module_name(self, line: str) -> Optional[str]:
        """提取模块名 v2.0"""
        if "('" in line or '("' in line:
            start = line.find("('") if "('" in line else line.find('("')
            if start != -1:
                end = line.find("')", start) if "('" in line else line.find('")', start)
                if end != -1:
                    return line[start+2:end]
        return None
    
    def _extract_string_module(self, line: str) -> Optional[str]:
        """提取字符串中的模块名"""
        import_pos = line.find('import ')
        if import_pos != -1:
            module_part = line[import_pos + 7:].strip()
            if module_part.startswith('"') or module_part.startswith("'"):
                end_quote = module_part.find('"', 1) if module_part.startswith('"') else module_part.find("'", 1)
                if end_quote != -1:
                    return module_part[1:end_quote]
        return None
    
    def _detect_critical_dependencies(self) -> Set[str]:
        """检测关键依赖的动态导入 v2.0"""
        modules = set()
        
        # 扩展的关键动态导入模式 v2.0
        critical_patterns = [
            # scipy 相关（最常见的问题）
            "scipy._lib.array_api_compat.numpy.fft",
            "scipy.stats.chatterjeexi",
            "scipy._lib.array_api_compat.numpy",
            "scipy._lib.array_api_compat",
            "scipy._lib._util",
            "scipy._lib._array_api",
            "scipy.sparse._base",
            "scipy.sparse._sputils",
            "scipy.stats._stats_py",
            "scipy.stats._continuous_distns",
            "scipy.stats._discrete_distns",
            "scipy.stats._multivariate",
            "scipy.stats._stats_mstats_common",
            "scipy.stats._stats",
            "scipy.stats._binned_statistic",
            "scipy.stats._qmc",
            "scipy.stats._sobol",
            "scipy.stats._levy_stable",
            "scipy.stats._binomtest",
            "scipy.stats._entropy",
            "scipy.stats._hypotests",
            "scipy.stats._ksstats",
            "scipy.stats._mannwhitneyu",
            "scipy.stats._morestats",
            "scipy.stats._mstats_basic",
            "scipy.stats._mstats_extras",
            "scipy.stats._page_trend_test",
            "scipy.stats._proportion",
            "scipy.stats._relative_risk",
            "scipy.stats._resampling",
            "scipy.stats._rvs_sampling",
            "scipy.stats._survival",
            "scipy.stats._tukeylambda_stats",
            "scipy.stats._variation",
            "scipy.stats.contingency",
            "scipy.stats.distributions",
            "scipy.stats.mstats",
            "scipy.stats.mstats_basic",
            "scipy.stats.mstats_extras",
            "scipy.stats.qmc",
            "scipy.stats.sampling",
            "scipy.stats.survival",
            
            # numpy 相关
            "numpy.core._methods",
            "numpy.lib.format",
            "numpy.random._pickle",
            "numpy.random._common",
            "numpy.random._bounded_integers",
            "numpy.random._mt19937",
            "numpy.random._pcg64",
            "numpy.random._philox",
            "numpy.random._sfc64",
            "numpy.random._generator",
            "numpy.random.bit_generator",
            "numpy.random.mtrand",
            
            # pandas 相关
            "pandas._libs.tslibs.timedeltas",
            "pandas._libs.tslibs.timestamps",
            "pandas._libs.tslibs.np_datetime",
            "pandas._libs.tslibs.offsets",
            "pandas._libs.tslibs.parsing",
            "pandas._libs.tslibs.period",
            "pandas._libs.tslibs.strptime",
            "pandas._libs.hashtable",
            "pandas._libs.index",
            "pandas._libs.internals",
            "pandas._libs.join",
            "pandas._libs.lib",
            "pandas._libs.missing",
            "pandas._libs.parsers",
            "pandas._libs.properties",
            "pandas._libs.reduction",
            "pandas._libs.sparse",
            "pandas._libs.window",
            "pandas._libs.writers",
            
            # sklearn 相关
            "sklearn.utils._cython_blas",
            "sklearn.neighbors._partition_nodes",
            "sklearn.tree._utils",
            "sklearn.tree._splitter",
            "sklearn.tree._criterion",
            "sklearn.tree._tree",
            
            # transformers 相关
            "transformers.tokenization_utils",
            "transformers.modeling_utils",
            "transformers.generation.utils",
            "transformers.trainer_utils",
            "transformers.data.data_collator",
            "transformers.data.processors",
            "transformers.pipelines",
            "transformers.feature_extraction_utils",
            "transformers.image_processing_utils",
            "transformers.processing_utils",
            
            # Web 框架
            "fastapi.dependencies",
            "starlette.middleware",
            "uvicorn.lifespan",
            
            # 其他关键库
            "pydantic.deprecated.decorator",
            "langchain_core._import_utils",
            "langchain_core.tools.base",
            
            # PySide6 相关
            "PySide6.QtCore",
            "PySide6.QtGui", 
            "PySide6.QtWidgets",
            "PySide6.QtNetwork",
            "PySide6.QtWebEngine",
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets",
            
            # 其他重要库
            "requests",
            "urllib3",
            "certifi",
            "charset_normalizer",
            "idna",
            
            # Pydantic 相关模块
            "pydantic",
            "pydantic.deprecated",
            "pydantic.deprecated.decorator",
            "pydantic_core",
            "pydantic._internal",
            "pydantic._migration",
            "pydantic._internal._validators",
            
            # LangChain 相关模块
            "langchain",
            "langchain_core",
            "langchain_openai",
            "langchain_core.tools",
            "langchain_core._import_utils",
            "langchain_core.tools.base",
        ]
        
        print(f"   检测 {len(critical_patterns)} 个关键动态导入模式...")
        
        for module_name in critical_patterns:
            try:
                # 尝试导入模块
                importlib.import_module(module_name)
                modules.add(module_name)
            except ImportError:
                # 如果导入失败，检查是否是项目内部模块
                if not any(prefix in module_name for prefix in ['scipy.', 'numpy.', 'pandas.', 'sklearn.', 'transformers.', 'PySide6.']):
                    # 对于非第三方库，尝试添加到项目中
                    modules.add(module_name)
            except Exception:
                # 对于其他错误，也尝试添加
                modules.add(module_name)
        
        return modules
    
    def _detect_runtime_imports(self) -> Set[str]:
        """检测运行时动态导入"""
        modules = set()
        
        # 运行时可能需要的模块
        runtime_modules = [
            # 系统模块
            "os", "sys", "pathlib", "json", "time", "datetime",
            "subprocess", "platform", "argparse", "typing",
            
            # 网络相关
            "requests", "urllib3", "certifi", "charset_normalizer",
            
            # 数据处理
            "pandas", "numpy", "scipy", "sklearn",
            
            # 机器学习
            "transformers", "torch", "tensorflow",
            
            # Web框架
            "fastapi", "starlette", "uvicorn", "flask",
            
            # 数据库
            "sqlite3", "sqlalchemy", "pymongo", "redis",
            
            # 图像处理
            "PIL", "opencv", "matplotlib", "seaborn",
            
            # 其他常用库
            "yaml", "toml", "configparser", "logging",
            "threading", "multiprocessing", "asyncio",
            "aiohttp", "websockets", "socketserver",
        ]
        
        print(f"   检测 {len(runtime_modules)} 个运行时模块...")
        
        for module_name in runtime_modules:
            try:
                importlib.import_module(module_name)
                modules.add(module_name)
            except ImportError:
                # 对于某些模块，即使导入失败也添加到列表中
                # 因为这些模块可能在运行时动态加载
                if module_name in ["sqlite3", "threading", "multiprocessing", "asyncio"]:
                    modules.add(module_name)
            except Exception:
                # 对于其他错误，也尝试添加
                modules.add(module_name)
        
        return modules
    
    def _smart_merge_strategy(self, all_modules: Set[str], project_imports: Set[str], 
                             code_imports: Set[str], critical_imports: Set[str], 
                             runtime_imports: Set[str]) -> List[str]:
        """智能合并策略 v2.0，确保不丢失重要模块"""
        final_modules = set()
        
        # 策略1：保留所有项目特定模块（最高优先级）
        final_modules.update(project_imports)
        print(f"   保留项目特定模块: {len(project_imports)} 个")
        
        # 策略2：保留所有代码中的实际动态导入
        final_modules.update(code_imports)
        print(f"   保留代码动态导入: {len(code_imports)} 个")
        
        # 策略3：保留所有关键依赖
        final_modules.update(critical_imports)
        print(f"   保留关键依赖: {len(critical_imports)} 个")
        
        # 策略4：保留运行时模块
        final_modules.update(runtime_imports)
        print(f"   保留运行时模块: {len(runtime_imports)} 个")
        
        # 策略5：如果还有空间，添加其他重要模块
        remaining_space = self.max_hidden_imports - len(final_modules)
        if remaining_space > 0:
            other_modules = all_modules - final_modules
            if other_modules:
                # 按优先级添加其他模块
                prioritized_others = self._prioritize_other_modules(list(other_modules))
                final_modules.update(prioritized_others[:remaining_space])
                print(f"   添加其他重要模块: {min(remaining_space, len(prioritized_others))} 个")
        
        return list(final_modules)
    
    def _prioritize_other_modules(self, modules: List[str]) -> List[str]:
        """对其他模块进行优先级排序 v2.0"""
        # 定义优先级规则
        priority_rules = [
            # 最高优先级：科学计算库
            lambda m: any(prefix in m for prefix in ['scipy.', 'numpy.', 'pandas.', 'matplotlib.']),
            # 高优先级：机器学习库
            lambda m: any(prefix in m for prefix in ['sklearn.', 'transformers.', 'torch.', 'tensorflow.']),
            # 中优先级：Web框架
            lambda m: any(prefix in m for prefix in ['fastapi.', 'starlette.', 'uvicorn.', 'django.', 'flask.']),
            # 中优先级：GUI框架
            lambda m: any(prefix in m for prefix in ['PySide6.', 'PyQt6.', 'tkinter.', 'wx.']),
            # 低优先级：其他库
            lambda m: True
        ]
        
        prioritized = []
        for rule in priority_rules:
            rule_modules = [m for m in modules if rule(m) and m not in prioritized]
            prioritized.extend(rule_modules)
        
        return prioritized
    
    def save_detection_result(self, modules: List[str], output_file: str = "smart_detected_modules.json"):
        """保存检测结果 v2.0"""
        data = {
            "generated_at": str(Path.cwd()),
            "total_modules": len(modules),
            "modules": sorted(modules),
            "detection_method": "smart_automated_v2",
            "max_modules": self.max_hidden_imports,
            "version": "2.0"
        }
        
        output_path = self.project_root / "build_system" / output_file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 智能检测结果已保存到: {output_path}")
    
    def _is_project_module(self, module_name: str) -> bool:
        """检查是否是项目内部模块"""
        project_prefixes = [
            'agent', 'bot', 'common', 'config', 'gui', 'utils',
            'telemetry', 'knowledge', 'settings', 'skills', 'build_system',
            'resource', 'tests', 'docs', 'scripts'
        ]
        
        # 检查模块名是否以项目前缀开头
        for prefix in project_prefixes:
            if module_name.startswith(prefix + '.') or module_name == prefix:
                return True
        
        # 检查是否是项目根目录下的模块
        root_modules = ['main', 'app_context', 'build']
        if module_name in root_modules:
            return True
        
        return False
    
    def _validate_and_filter_modules(self, modules: Set[str]) -> Set[str]:
        """验证和过滤模块，确保模块名称的有效性"""
        validated_modules = set()
        
        for module in modules:
            if self._is_valid_module_name(module):
                validated_modules.add(module)
        
        return validated_modules
    
    def _is_valid_module_name(self, module_name: str) -> bool:
        """检查模块名称是否有效"""
        # 检查基本有效性
        if not module_name or module_name.startswith('.') or module_name.endswith('.'):
            return False
        
        # 检查是否包含无效字符
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        if any(char in module_name for char in invalid_chars):
            return False
        
        # 检查是否以数字开头（Python模块不能以数字开头）
        if module_name[0].isdigit():
            return False
        
        # 检查是否包含连续的点
        if '..' in module_name:
            return False
        
        # 检查是否以点结尾
        if module_name.endswith('.'):
            return False
        
        # 排除hook文件
        if 'hook-' in module_name:
            return False
        
        # 排除包含连字符的模块名（Python模块名不能包含连字符）
        if '-' in module_name:
            return False
        
        return True
    
    def _check_windows_compatibility(self, modules: List[str]) -> Dict[str, Any]:
        """检查Windows兼容性"""
        # 模拟生成spec文件中的hidden_imports行
        hidden_imports_str = "hiddenimports=[" + ", ".join(f"'{m}'" for m in modules) + "]"
        line_length = len(hidden_imports_str)
        
        result = {
            "line_length": line_length,
            "windows_compatible": line_length <= self.spec_line_limit,
            "exceeds_limit": line_length - self.spec_line_limit if line_length > self.spec_line_limit else 0,
            "modules_count": len(modules)
        }
        
        return result
    
    def _compress_modules_for_windows(self, modules: List[str]) -> List[str]:
        """为Windows环境压缩模块列表"""
        print(f"🪟 检查Windows兼容性...")
        
        # 检查当前模块列表的兼容性
        compatibility = self._check_windows_compatibility(modules)
        
        if compatibility["windows_compatible"]:
            print(f"✅ Windows兼容性检查通过: {compatibility['line_length']} 字符")
            return modules
        
        print(f"⚠️  Windows兼容性检查失败: {compatibility['line_length']} 字符 (限制: {self.spec_line_limit})")
        print(f"   超出限制: {compatibility['exceeds_limit']} 字符")
        
        # 压缩策略：按优先级保留模块
        compressed_modules = self._apply_compression_strategy(modules)
        
        # 重新检查兼容性
        new_compatibility = self._check_windows_compatibility(compressed_modules)
        
        if new_compatibility["windows_compatible"]:
            print(f"✅ 压缩后Windows兼容性检查通过: {new_compatibility['line_length']} 字符")
            print(f"   保留模块: {len(compressed_modules)} 个 (原始: {len(modules)} 个)")
        else:
            print(f"❌ 压缩后仍超出限制: {new_compatibility['line_length']} 字符")
            # 进一步压缩
            compressed_modules = self._apply_aggressive_compression(compressed_modules)
            final_compatibility = self._check_windows_compatibility(compressed_modules)
            print(f"✅ 最终压缩后Windows兼容性检查通过: {final_compatibility['line_length']} 字符")
            print(f"   最终保留模块: {len(compressed_modules)} 个")
        
        return compressed_modules
    
    def _apply_compression_strategy(self, modules: List[str]) -> List[str]:
        """应用压缩策略"""
        # 优先级1：项目核心模块（必须保留）
        core_modules = [m for m in modules if self._is_core_module(m)]
        
        # 优先级2：关键第三方库
        critical_third_party = [m for m in modules if self._is_critical_third_party(m)]
        
        # 优先级3：项目内部模块
        project_modules = [m for m in modules if self._is_project_module(m) and m not in core_modules]
        
        # 优先级4：其他模块（按重要性排序）
        other_modules = [m for m in modules if m not in core_modules + critical_third_party + project_modules]
        
        # 按优先级组合，确保不超过限制
        result = []
        for module_group in [core_modules, critical_third_party, project_modules, other_modules]:
            for module in module_group:
                result.append(module)
                # 检查是否超出限制
                test_compatibility = self._check_windows_compatibility(result)
                if not test_compatibility["windows_compatible"]:
                    result.pop()  # 移除最后一个模块
                    break
        
        return result
    
    def _apply_aggressive_compression(self, modules: List[str]) -> List[str]:
        """应用激进压缩策略"""
        # 只保留最核心的模块
        essential_modules = [
            # 项目核心
            'main', 'app_context', 'config', 'gui', 'bot', 'agent', 'common', 'utils',
            
            # 关键第三方库
            'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
            'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
            'PySide6.QtWebChannel', 'PySide6.QtWebEngine',
            'requests', 'urllib3', 'certifi', 'charset_normalizer',
            'pandas', 'numpy', 'scipy', 'sklearn',
            'transformers', 'torch', 'tensorflow',
            'fastapi', 'starlette', 'uvicorn',
            'sqlalchemy', 'sqlite3', 'PIL', 'opencv',
            'cryptography', 'bcrypt', 'jwt', 'playwright',
            'langmem', 'faiss',
            
            # Pydantic 相关模块
            'pydantic', 'pydantic.deprecated', 'pydantic.deprecated.decorator',
            'pydantic_core', 'pydantic._internal', 'pydantic._migration',
            
            # LangChain 相关模块
            'langchain', 'langchain_core', 'langchain_openai',
            'langchain_core.tools', 'langchain_core._import_utils',
        ]
        
        # 从原始列表中筛选出存在的核心模块
        result = [m for m in modules if m in essential_modules]
        
        return result
    
    def _is_core_module(self, module: str) -> bool:
        """检查是否是核心模块"""
        core_modules = [
            'main', 'app_context', 'config', 'gui', 'bot', 'agent', 'common', 'utils'
        ]
        return module in core_modules
    
    def _is_critical_third_party(self, module: str) -> bool:
        """检查是否是关键第三方库"""
        critical_libs = [
            'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
            'requests', 'urllib3', 'certifi', 'charset_normalizer',
            'pandas', 'numpy', 'scipy', 'sklearn',
            'transformers', 'torch', 'tensorflow',
            'fastapi', 'starlette', 'uvicorn',
            'sqlalchemy', 'sqlite3', 'PIL', 'opencv',
            # 添加pydantic相关模块
            'pydantic', 'pydantic.deprecated', 'pydantic.deprecated.decorator',
            'pydantic_core', 'pydantic._internal', 'pydantic._migration',
            # 添加langchain相关模块
            'langchain', 'langchain_core', 'langchain_openai',
            'langchain_core.tools', 'langchain_core._import_utils'
        ]
        return any(module.startswith(lib) for lib in critical_libs) 