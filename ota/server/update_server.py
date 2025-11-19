#!/usr/bin/env python3
"""
简单的OTA更新服务器
用于测试和开发，支持动态生成 appcast.xml
"""

import logging
import os
import sys
from flask import Flask, jsonify, request, send_file, Response
from pathlib import Path

# Add project root to Python path to resolve imports when run as a script
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ota.server.appcast_generator import AppcastGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize appcast generator
server_dir = Path(__file__).parent
appcast_gen = AppcastGenerator(server_dir, server_dir)

# Server configuration
SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False
}

def _find_installation_package(requested_filename: str, dist_dir: Path) -> Path:
    """
    智能查找安装包文件
    
    策略：
    1. 直接匹配文件名
    2. 模糊匹配（忽略版本号）
    3. 匹配平台和架构
    
    Args:
        requested_filename: 请求的文件名
        dist_dir: dist 目录路径
    
    Returns:
        Path: 找到的文件路径，如果未找到返回 None
    """
    if not dist_dir.exists():
        logger.warning(f"Dist directory not found: {dist_dir}")
        return None
    
    # 1. 直接匹配
    direct_path = dist_dir / requested_filename
    if direct_path.exists():
        logger.info(f"Found exact match: {direct_path}")
        return direct_path
    
    # 2. 提取请求文件的关键信息
    import re
    
    # 提取平台和架构信息
    platform_patterns = {
        'macos': r'(macos|darwin)',
        'windows': r'windows',
        'linux': r'linux'
    }
    
    arch_patterns = {
        'aarch64': r'(aarch64|arm64)',
        'amd64': r'(amd64|x86_64|x64)',
        'x86': r'(x86|i386)'
    }
    
    # 提取扩展名
    ext = Path(requested_filename).suffix
    
    # 检测平台
    detected_platform = None
    for platform, pattern in platform_patterns.items():
        if re.search(pattern, requested_filename, re.IGNORECASE):
            detected_platform = platform
            break
    
    # 检测架构
    detected_arch = None
    for arch, pattern in arch_patterns.items():
        if re.search(pattern, requested_filename, re.IGNORECASE):
            detected_arch = arch
            break
    
    logger.info(f"Searching for: platform={detected_platform}, arch={detected_arch}, ext={ext}")
    
    # 3. 在 dist 目录中查找匹配的文件
    candidates = []
    
    for file_path in dist_dir.glob(f"*{ext}"):
        if not file_path.is_file():
            continue
        
        filename = file_path.name
        score = 0
        
        # 匹配平台
        if detected_platform:
            for pattern in platform_patterns[detected_platform].split('|'):
                if pattern.strip('()') in filename.lower():
                    score += 10
                    break
        
        # 匹配架构
        if detected_arch:
            for pattern in arch_patterns[detected_arch].split('|'):
                if pattern.strip('()') in filename.lower():
                    score += 5
                    break
        
        # 匹配扩展名（已经通过 glob 过滤）
        score += 1
        
        if score > 0:
            candidates.append((score, file_path))
    
    # 按分数排序，返回最佳匹配
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_match = candidates[0][1]
        logger.info(f"Found best match (score={candidates[0][0]}): {best_match}")
        return best_match
    
    logger.warning(f"No matching file found for: {requested_filename}")
    return None

# Update information configuration
UPDATE_CONFIG = {
    "latest_version": "1.1.0",
    "min_version": "1.0.0",
    "updates": {
        "1.1.0": {
            "version": "1.1.0",
            "description": "<h2>What's New in eCan 1.1.0</h2><ul><li>Added OTA update functionality</li><li>Bug fixes and performance improvements</li><li>Enhanced UI/UX</li></ul>",
            "release_date": "2024-01-01",
            "download_urls": {
                "windows": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-1.0.0-windows-amd64-Setup.exe",
                "darwin": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-1.0.0-macos-aarch64.pkg",
                "linux": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-1.0.0-linux-amd64.tar.gz"
            },
            "file_sizes": {
                "windows": 0,  # Will be calculated dynamically
                "darwin": 0,
                "linux": 0
            },
            "signatures": {
                "windows": "",
                "darwin": "",
                "linux": ""
            }
        }
    }
}

@app.route('/api/check', methods=['GET'])
@app.route('/api/check-update', methods=['GET'])
def check_update():
    """Check update API"""
    try:
        # Get client information
        app_name = request.args.get('app', 'ecbot')
        current_version = request.args.get('version', '1.0.0')
        platform = request.args.get('platform', 'windows')
        arch = request.args.get('arch', 'x64')
        
        logger.info(f"Update check: {app_name} v{current_version} on {platform}-{arch}")
        
        # Check if update is available
        latest_version = UPDATE_CONFIG['latest_version']
        # Semantic version comparison (simplified implementation without third-party dependencies)
        def _to_version_tuple(v: str):
            import re
            parts = re.split(r'[.+-]', v)
            nums = []
            for p in parts:
                if p.isdigit():
                    nums.append(int(p))
                else:
                    # Stop at non-numeric segment to avoid including pre-release tags in comparison
                    break
            # Normalize length to avoid inconsistent comparison between 1.2 and 1.2.0
            while len(nums) < 3:
                nums.append(0)
            return tuple(nums[:3])
        has_update = _to_version_tuple(current_version) < _to_version_tuple(latest_version)
        
        response = {
            "update_available": has_update,
            "current_version": current_version,
            "latest_version": latest_version
        }
        
        if has_update:
            update_info = UPDATE_CONFIG['updates'].get(latest_version, {})
            
            # ✅ 动态扫描 dist 目录获取文件信息
            signature = ""
            file_size = 0
            
            try:
                project_root = Path(__file__).parent.parent.parent
                dist_dir = project_root / "dist"
                
                # 根据平台查找对应的文件
                patterns = {
                    'darwin': ["eCan-*-macos-*.pkg", "eCan-*-macos-*.dmg"],
                    'windows': ["eCan-*-windows-*-Setup.exe", "eCan-*-windows-*.msi"],
                    'linux': ["eCan-*-linux-*.tar.gz", "eCan-*-linux-*.AppImage"]
                }
                
                if platform in patterns:
                    for pattern in patterns[platform]:
                        for pkg_file in dist_dir.glob(pattern):
                            # 计算文件大小
                            file_size = pkg_file.stat().st_size
                            
                            # 计算 SHA256
                            import hashlib
                            sha256_hash = hashlib.sha256()
                            with open(pkg_file, "rb") as f:
                                for byte_block in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(byte_block)
                            signature = sha256_hash.hexdigest()
                            
                            logger.info(f"[CHECK] Found package: {pkg_file.name}, size: {file_size}, sha256: {signature[:16]}...")
                            break
                        if file_size > 0:
                            break
            except Exception as e:
                logger.warning(f"Failed to scan dist directory: {e}")
            
            response.update({
                "description": update_info.get('description', ''),
                "release_date": update_info.get('release_date', ''),
                "download_url": update_info.get('download_urls', {}).get(platform, ''),
                "file_size": file_size or update_info.get('file_sizes', {}).get(platform, 0),
                "signature": signature
            })
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['GET'])
@app.route('/api/download-latest', methods=['GET'])
def download_latest():
    """Download latest version API"""
    try:
        platform = request.args.get('platform', 'windows')
        arch = request.args.get('arch', 'x64')
        
        # This should return the actual update file
        # For demonstration, we return a sample response
        return jsonify({
            "error": "Download not implemented in demo server",
            "message": "In production, this would return the actual update file"
        }), 501
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/appcast.xml', methods=['GET'])
def appcast():
    """Dynamically generate Sparkle/winSparkle appcast file by scanning dist directory"""
    try:
        # Get request parameters
        version = request.args.get('version')  # Specified version
        base_url = request.args.get('base_url', f"http://{request.host}")
        
        logger.info(f"[APPCAST] Request received: version={version}, base_url={base_url}")
        
        # Get dist directory
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # ✅ Use dynamic generation - scans dist directory and calculates signatures
        logger.info("[APPCAST] 🚀 Using dynamic generation (no signature files needed)")
        xml_content = appcast_gen.generate_dynamic(
            base_url=base_url,
            dist_dir=dist_dir,
            version=version
        )
        
        if not xml_content:
            logger.error("[APPCAST] ❌ Dynamic generation failed")
            return "Appcast generation failed - no packages found in dist directory", 404
        
        # Return generated file
        appcast_path = server_dir / "appcast.xml"
        if appcast_path.exists():
            logger.info(f"[APPCAST] ✅ Serving dynamically generated appcast")
            return send_file(str(appcast_path), mimetype='application/rss+xml')
        else:
            return "Generated appcast not found", 404
            
    except Exception as e:
        logger.error(f"[APPCAST] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error serving appcast: {str(e)}", 500

@app.route('/admin/generate-appcast', methods=['POST'])
def generate_appcast_admin():
    """Admin API: manually trigger dynamic appcast generation"""
    try:
        data = request.get_json() or {}
        version = data.get('version')
        base_url = data.get('base_url', 'http://127.0.0.1:8080')
        
        # Get dist directory
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # Use dynamic generation
        xml_content = appcast_gen.generate_dynamic(
            base_url=base_url,
            dist_dir=dist_dir,
            version=version
        )
        
        if xml_content:
            return jsonify({
                "success": True,
                "message": "Dynamic appcast generated successfully",
                "appcast_url": f"{base_url}/appcast.xml"
            })
        else:
            return jsonify({
                "success": False,
                "message": "Dynamic appcast generation failed - no packages found"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    # /admin/signatures route removed - no longer using signature files

@app.route('/downloads/<filename>', methods=['GET'])
def download_file(filename):
    """Provide real installation package download - dynamically finds files"""
    try:
        # Get project root directory
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # ✅ 智能查找文件
        actual_file = _find_installation_package(filename, dist_dir)
        
        if not actual_file:
            logger.warning(f"File not found: {filename}")
            return jsonify({"error": f"File not found: {filename}"}), 404
        
        # 提供文件下载
        file_size = actual_file.stat().st_size
        logger.info(f"✅ Serving file: {actual_file.name} ({file_size / 1024 / 1024:.2f} MB)")
        
        return send_file(str(actual_file), as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"status": "ok", "service": "ECBot Update Server"})

@app.route('/', methods=['GET'])
def index():
    """首页"""
    return jsonify({
        "service": "ECBot Update Server",
        "endpoints": [
            "/api/check-update",
            "/api/download-latest", 
            "/appcast.xml",
            "/health"
        ]
    })

def check_dependencies():
    """检查依赖"""
    try:
        import flask
        logger.info("✓ Flask已安装")
        return True
    except ImportError:
        logger.error("✗ Flask未安装，请运行: pip install flask")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("ECBot 本地OTA测试服务器")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        logger.error("依赖检查失败，无法启动服务器")
        return
    
    logger.info("Starting ECBot Update Server...")
    logger.info("Available endpoints:")
    for rule in app.url_map.iter_rules():
        logger.info(f"  - {rule.methods} {rule.rule}")
    
    print("\n服务器信息:")
    print(f"  - 地址: http://127.0.0.1:{SERVER_CONFIG['port']}")
    print("  - 端点:")
    print("    * GET /api/check-update - 检查更新")
    print("    * GET /appcast.xml - Sparkle appcast文件") 
    print("    * GET /health - 健康检查")
    print("    * GET / - 服务器信息")
    
    print("\n正在启动服务器...")
    print("按 Ctrl+C 停止服务器")
    print("-" * 50)
    
    try:
        app.run(
            host=SERVER_CONFIG["host"], 
            port=SERVER_CONFIG["port"], 
            debug=SERVER_CONFIG["debug"]
        )
    except KeyboardInterrupt:
        logger.info("服务器已停止")

if __name__ == "__main__":
    main()