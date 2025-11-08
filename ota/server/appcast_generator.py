#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Appcast XML 动态生成器
根据签名文件和配置动态生成 appcast.xml
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from jinja2 import Template

class AppcastGenerator:
    """Appcast XML 生成器"""
    
    def __init__(self, server_dir: Path = None):
        self.server_dir = server_dir or Path(__file__).parent
        self.template_file = self.server_dir / "appcast_template.xml"
        
    def load_template(self) -> Template:
        """加载 appcast 模板"""
        if not self.template_file.exists():
            raise FileNotFoundError(f"模板文件不存在: {self.template_file}")
        
        with open(self.template_file, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        return Template(template_content)
    
    def load_signatures(self, version: str) -> Optional[Dict[str, Any]]:
        """加载指定版本的签名文件"""
        signatures_file = self.server_dir / f"signatures_{version}.json"
        
        if not signatures_file.exists():
            return None
        
        with open(signatures_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_os_from_filename(self, filename: str) -> str:
        """从文件名推断操作系统"""
        filename_lower = filename.lower()
        
        if 'windows' in filename_lower or filename_lower.endswith('.exe'):
            return 'windows'
        elif 'darwin' in filename_lower or 'macos' in filename_lower or filename_lower.endswith('.dmg'):
            return 'macos'
        elif 'linux' in filename_lower or filename_lower.endswith('.appimage'):
            return 'linux'
        else:
            return 'unknown'
    
    def get_release_notes(self, version: str) -> str:
        """获取版本发布说明"""
        # 可以从文件、数据库或API获取发布说明
        # 这里提供一个默认模板
        return f"""
        <h2>What's New in eCan {version}</h2>
        <ul>
            <li>Performance improvements and bug fixes</li>
            <li>Enhanced user interface</li>
            <li>Security updates</li>
        </ul>
        """
    
    def generate_appcast_items(self, version: str, base_url: str = "http://127.0.0.1:8080") -> List[Dict[str, Any]]:
        """生成 appcast 项目列表"""
        signatures = self.load_signatures(version)
        if not signatures:
            return []
        
        items = []
        
        for filename, sig_info in signatures.items():
            # 跳过明显的测试文件（但允许测试版本）
            if filename.startswith('test_') and not version.endswith('-test'):
                continue
            
            os_type = self.get_os_from_filename(filename)
            
            item = {
                'title': f'eCan {version}',
                'description': self.get_release_notes(version),
                'pub_date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                'download_url': f'{base_url}/downloads/{filename}',
                'version': version,
                'os': os_type,
                'file_size': sig_info.get('file_size', 0),
                'signature': sig_info.get('signature', '')
            }
            
            items.append(item)
        
        return items
    
    def generate_appcast(self, version: str, base_url: str = "http://127.0.0.1:8080", 
                        output_file: str = "appcast.xml") -> bool:
        """生成 appcast.xml 文件"""
        try:
            # 加载模板
            template = self.load_template()
            
            # 生成项目数据
            items = self.generate_appcast_items(version, base_url)
            
            if not items:
                print(f"[APPCAST] ⚠️ 没有找到版本 {version} 的签名文件")
                return False
            
            # 准备模板数据
            template_data = {
                'base_url': base_url,
                'build_date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                'items': items
            }
            
            # 渲染模板
            appcast_content = template.render(**template_data)
            
            # 保存文件
            output_path = self.server_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(appcast_content)
            
            print(f"[APPCAST] ✅ 已生成: {output_path}")
            print(f"[APPCAST] 📦 包含 {len(items)} 个更新项目")
            
            return True
            
        except Exception as e:
            print(f"[APPCAST] ❌ 生成失败: {e}")
            return False
    
    def generate_from_latest_signatures(self, base_url: str = "http://127.0.0.1:8080") -> bool:
        """从最新的签名文件生成 appcast"""
        # 查找最新的签名文件
        signature_files = list(self.server_dir.glob("signatures_*.json"))
        
        if not signature_files:
            print("[APPCAST] ❌ 没有找到签名文件")
            return False
        
        # 按修改时间排序，获取最新的
        latest_file = max(signature_files, key=lambda f: f.stat().st_mtime)
        
        # 从文件名提取版本号
        version = latest_file.stem.replace('signatures_', '')
        
        print(f"[APPCAST] 🔍 使用最新签名文件: {latest_file.name}")
        print(f"[APPCAST] 📋 版本: {version}")
        
        return self.generate_appcast(version, base_url)

def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='生成 Appcast XML')
    parser.add_argument('--version', help='指定版本号')
    parser.add_argument('--base-url', default='http://127.0.0.1:8080', help='基础URL')
    parser.add_argument('--output', default='appcast.xml', help='输出文件名')
    parser.add_argument('--latest', action='store_true', help='使用最新的签名文件')
    
    args = parser.parse_args()
    
    generator = AppcastGenerator()
    
    if args.latest:
        success = generator.generate_from_latest_signatures(args.base_url)
    elif args.version:
        success = generator.generate_appcast(args.version, args.base_url, args.output)
    else:
        print("请指定 --version 或使用 --latest")
        return False
    
    return success

if __name__ == '__main__':
    main()
