#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Appcast Generator for GitHub Release
为 GitHub Release 生成 Sparkle appcast XML 文件
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import hashlib

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def calculate_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """计算文件哈希值"""
    hash_obj = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def sign_update(file_path: str) -> Optional[str]:
    """使用 Ed25519 私钥签名更新文件"""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64
        
        # 从环境变量获取私钥
        private_key_pem = os.environ.get('ED25519_PRIVATE_KEY')
        if not private_key_pem:
            print("Warning: ED25519_PRIVATE_KEY not set, skipping signature")
            return None
        
        # 加载私钥
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None
        )
        
        # 读取文件内容并签名
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        signature = private_key.sign(file_data)
        return base64.b64encode(signature).decode('utf-8')
        
    except ImportError:
        print("Warning: cryptography module not available, skipping signature")
        return None
    except Exception as e:
        print(f"Warning: Failed to sign file: {e}")
        return None


def filter_assets(assets: List[Dict], platform_filter: Optional[str] = None, 
                  arch_filter: Optional[str] = None) -> List[Dict]:
    """过滤资产列表"""
    filtered = []
    
    for asset in assets:
        name = asset['name'].lower()
        
        # 平台过滤
        if platform_filter:
            if platform_filter == 'macos':
                if not ('macos' in name or 'darwin' in name or name.endswith('.pkg') or name.endswith('.dmg')):
                    continue
            elif platform_filter == 'windows':
                if not ('windows' in name or name.endswith('.exe') or name.endswith('.msi')):
                    continue
            elif platform_filter == 'linux':
                if not ('linux' in name or name.endswith('.appimage')):
                    continue
        
        # 架构过滤
        if arch_filter:
            if arch_filter == 'amd64':
                if not any(x in name for x in ['amd64', 'x86_64', 'x64']):
                    continue
            elif arch_filter == 'aarch64':
                if not any(x in name for x in ['aarch64', 'arm64']):
                    continue
        
        filtered.append(asset)
    
    return filtered


def detect_os_and_arch(filename: str) -> tuple:
    """从文件名检测操作系统和架构"""
    name_lower = filename.lower()
    
    # 检测操作系统
    if 'windows' in name_lower or name_lower.endswith('.exe') or name_lower.endswith('.msi'):
        os_type = 'windows'
    elif 'macos' in name_lower or 'darwin' in name_lower or name_lower.endswith('.pkg') or name_lower.endswith('.dmg'):
        os_type = 'macos'
    elif 'linux' in name_lower or name_lower.endswith('.appimage'):
        os_type = 'linux'
    else:
        os_type = 'unknown'
    
    # 检测架构
    if any(x in name_lower for x in ['amd64', 'x86_64', 'x64']):
        arch = 'x86_64'
    elif any(x in name_lower for x in ['aarch64', 'arm64']):
        arch = 'arm64'
    else:
        arch = 'universal'
    
    return os_type, arch


def generate_appcast_xml(release: Dict, assets: List[Dict], output_path: str):
    """生成 Sparkle appcast XML"""
    from xml.etree import ElementTree as ET
    
    # 创建 RSS 根元素
    rss = ET.Element('rss', {
        'version': '2.0',
        'xmlns:sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle',
        'xmlns:dc': 'http://purl.org/dc/elements/1.1/'
    })
    
    channel = ET.SubElement(rss, 'channel')
    
    # 频道信息
    ET.SubElement(channel, 'title').text = 'eCan AI Assistant'
    ET.SubElement(channel, 'link').text = 'https://github.com/scszcoder/ecbot'
    ET.SubElement(channel, 'description').text = 'eCan AI Assistant Updates'
    ET.SubElement(channel, 'language').text = 'en'
    
    # 为每个资产创建一个 item
    for asset in assets:
        item = ET.SubElement(channel, 'item')
        
        version = release['tag_name'].lstrip('v')
        os_type, arch = detect_os_and_arch(asset['name'])
        
        ET.SubElement(item, 'title').text = f"eCan {version}"
        ET.SubElement(item, 'sparkle:version').text = version
        ET.SubElement(item, 'sparkle:shortVersionString').text = version
        ET.SubElement(item, 'description').text = f"eCan AI Assistant {version} for {os_type} ({arch})"
        ET.SubElement(item, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        ET.SubElement(item, 'link').text = asset['browser_download_url']
        
        # 创建 enclosure 元素
        enclosure_attrs = {
            'url': asset['browser_download_url'],
            'length': str(asset['size']),
            'type': 'application/octet-stream',
            'sparkle:version': version,
            'sparkle:os': os_type,
        }
        
        # 添加架构信息
        if arch != 'universal':
            enclosure_attrs['sparkle:arch'] = arch
        
        # 尝试添加签名
        # 注意：这里我们假设 asset 是本地文件路径
        # 在 GitHub Actions 中，文件应该已经下载到本地
        if os.path.exists(asset['name']):
            signature = sign_update(asset['name'])
            if signature:
                enclosure_attrs['sparkle:edSignature'] = signature
        
        ET.SubElement(item, 'enclosure', enclosure_attrs)
    
    # 格式化并保存 XML
    tree = ET.ElementTree(rss)
    ET.indent(tree, space='  ')
    
    # 确保输出目录存在
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"Generated appcast: {output_path}")


def main(release: Dict, platform_filter: Optional[str] = None, 
         arch_filter: Optional[str] = None, output_path: str = 'appcast.xml'):
    """
    主函数：生成 appcast XML
    
    Args:
        release: GitHub release 信息字典，包含 tag_name 和 assets
        platform_filter: 平台过滤器 ('macos', 'windows', 'linux')
        arch_filter: 架构过滤器 ('amd64', 'aarch64')
        output_path: 输出文件路径
    """
    print(f"Generating appcast for release: {release.get('tag_name', 'unknown')}")
    print(f"Platform filter: {platform_filter or 'all'}")
    print(f"Arch filter: {arch_filter or 'all'}")
    
    # 获取资产列表
    assets = release.get('assets', [])
    if not assets:
        print("Warning: No assets found in release")
        return
    
    print(f"Total assets: {len(assets)}")
    
    # 过滤资产
    filtered_assets = filter_assets(assets, platform_filter, arch_filter)
    print(f"Filtered assets: {len(filtered_assets)}")
    
    if not filtered_assets:
        print("Warning: No assets match the filters")
        return
    
    # 生成 appcast XML
    generate_appcast_xml(release, filtered_assets, output_path)
    print(f"Appcast generated successfully: {output_path}")


if __name__ == '__main__':
    # 测试代码
    test_release = {
        'tag_name': 'v0.0.1',
        'assets': [
            {
                'name': 'eCan-0.0.1-macos-amd64.pkg',
                'browser_download_url': 'https://github.com/scszcoder/ecbot/releases/download/v0.0.1/eCan-0.0.1-macos-amd64.pkg',
                'size': 100000000
            }
        ]
    }
    
    main(test_release, platform_filter='macos', arch_filter='amd64', output_path='test_appcast.xml')
