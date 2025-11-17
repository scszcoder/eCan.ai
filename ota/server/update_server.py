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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 初始化 appcast 生成器
server_dir = Path(__file__).parent
appcast_gen = AppcastGenerator(server_dir, server_dir)

# 服务器配置
SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False
}

# 更新信息配置
UPDATE_CONFIG = {
    "latest_version": "1.1.0",
    "min_version": "1.0.0",
    "updates": {
        "1.1.0": {
            "version": "1.1.0",
            "description": "Added OTA update functionality and bug fixes",
            "release_date": "2024-01-01",
            "download_urls": {
                "windows": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-1.1.0-windows-amd64-Setup.exe",
                "darwin": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-1.1.0-darwin-amd64.dmg",
                "linux": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-1.1.0-linux-amd64.tar.gz"
            },
            "file_sizes": {
                "windows": 0,  # Will be calculated dynamically
                "darwin": 0,
                "linux": 0
            },
            "signatures": {
                "windows": "SHA256:...",
                "darwin": "SHA256:...",
                "linux": "SHA256:..."
            }
        }
    }
}

@app.route('/api/check', methods=['GET'])
@app.route('/api/check-update', methods=['GET'])
def check_update():
    """检查更新API"""
    try:
        # 获取客户端信息
        app_name = request.args.get('app', 'ecbot')
        current_version = request.args.get('version', '1.0.0')
        platform = request.args.get('platform', 'windows')
        arch = request.args.get('arch', 'x64')
        
        logger.info(f"Update check: {app_name} v{current_version} on {platform}-{arch}")
        
        # 检查是否有更新
        latest_version = UPDATE_CONFIG['latest_version']
        # 语义化版本比较（无第三方依赖的简化实现）
        def _to_version_tuple(v: str):
            import re
            parts = re.split(r'[.+-]', v)
            nums = []
            for p in parts:
                if p.isdigit():
                    nums.append(int(p))
                else:
                    # 非数字段停止，以避免把预发布标签纳入比较
                    break
            # 统一长度，避免 1.2 与 1.2.0 比较不一致
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
            response.update({
                "description": update_info.get('description', ''),
                "release_date": update_info.get('release_date', ''),
                "download_url": update_info.get('download_urls', {}).get(platform, ''),
                "file_size": update_info.get('file_sizes', {}).get(platform, 0),
                "signature": update_info.get('signatures', {}).get(platform, '')
            })
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['GET'])
@app.route('/api/download-latest', methods=['GET'])
def download_latest():
    """下载最新版本API"""
    try:
        platform = request.args.get('platform', 'windows')
        arch = request.args.get('arch', 'x64')
        
        # 这里应该返回实际的更新文件
        # 为了演示，我们返回一个示例响应
        return jsonify({
            "error": "Download not implemented in demo server",
            "message": "In production, this would return the actual update file"
        }), 501
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/appcast.xml', methods=['GET'])
def appcast():
    """动态生成 Sparkle/winSparkle appcast文件"""
    try:
        # 获取请求参数
        version = request.args.get('version')  # 指定版本
        base_url = request.args.get('base_url', f"http://{request.host}")
        
        # 如果指定了版本，使用指定版本；否则使用最新版本
        if version:
            success = appcast_gen.generate_appcast(version, base_url, "appcast_temp.xml")
            appcast_file = "appcast_temp.xml"
        else:
            success = appcast_gen.generate_from_latest_signatures(base_url)
            appcast_file = "appcast.xml"
        
        if not success:
            # 如果动态生成失败，尝试返回静态文件
            static_appcast = server_dir / "appcast.xml"
            if static_appcast.exists():
                logger.warning("动态生成失败，使用静态 appcast.xml")
                return send_file(str(static_appcast), mimetype='application/rss+xml')
            else:
                return "Appcast generation failed and no static file found", 404
        
        # 返回生成的文件
        appcast_path = server_dir / appcast_file
        if appcast_path.exists():
            logger.info(f"提供动态生成的 appcast: {appcast_file}")
            return send_file(str(appcast_path), mimetype='application/rss+xml')
        else:
            return "Generated appcast not found", 404
            
    except Exception as e:
        logger.error(f"Appcast 生成错误: {e}")
        return f"Error serving appcast: {str(e)}", 500

@app.route('/admin/generate-appcast', methods=['POST'])
def generate_appcast_admin():
    """管理接口：手动生成 appcast"""
    try:
        data = request.get_json() or {}
        version = data.get('version')
        base_url = data.get('base_url', 'http://127.0.0.1:8080')
        
        if version:
            success = appcast_gen.generate_appcast(version, base_url)
            message = f"为版本 {version} 生成 appcast"
        else:
            success = appcast_gen.generate_from_latest_signatures(base_url)
            message = "从最新签名文件生成 appcast"
        
        if success:
            return jsonify({
                "success": True,
                "message": f"{message} 成功",
                "appcast_url": f"{base_url}/appcast.xml"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"{message} 失败"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/admin/signatures', methods=['GET'])
def list_signatures():
    """管理接口：列出所有签名文件"""
    try:
        signature_files = list(server_dir.glob("signatures_*.json"))
        signatures_info = []
        
        for sig_file in signature_files:
            version = sig_file.stem.replace('signatures_', '')
            stat = sig_file.stat()
            
            signatures_info.append({
                "version": version,
                "filename": sig_file.name,
                "size": stat.st_size,
                "modified": stat.st_mtime
            })
        
        # 按修改时间排序
        signatures_info.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            "signatures": signatures_info,
            "count": len(signatures_info)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/downloads/<filename>', methods=['GET'])
def download_file(filename):
    """提供真实的安装包下载"""
    try:
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # 查找匹配的安装包文件
        actual_file = None
        
        # 定义文件映射规则
        file_mapping = {
            "eCan-1.1.0-windows-amd64-Setup.exe": [
                "eCan-1.0.0-windows-amd64-Setup.exe",
                "eCan-1.0.0-windows-amd64.exe"
            ],
            "eCan-1.1.0-darwin-amd64.dmg": [
                "eCan-1.0.0-darwin-amd64.dmg"
            ],
            "eCan-1.1.0-linux-amd64.tar.gz": [
                "eCan-1.0.0-linux-amd64.tar.gz"
            ]
        }
        
        # 查找实际文件
        if filename in file_mapping:
            for candidate in file_mapping[filename]:
                candidate_path = dist_dir / candidate
                if candidate_path.exists():
                    actual_file = candidate_path
                    break
        
        # 直接查找文件名
        if not actual_file:
            direct_path = dist_dir / filename
            if direct_path.exists():
                actual_file = direct_path
        
        # 如果找到真实文件，提供下载
        if actual_file and actual_file.exists():
            file_size = actual_file.stat().st_size
            logger.info(f"Serving real file: {actual_file} ({file_size} bytes)")
            
            # 更新配置中的文件大小
            if filename.endswith('.exe'):
                UPDATE_CONFIG['updates']['1.1.0']['file_sizes']['windows'] = file_size
            elif filename.endswith('.dmg'):
                UPDATE_CONFIG['updates']['1.1.0']['file_sizes']['darwin'] = file_size
            elif filename.endswith('.tar.gz'):
                UPDATE_CONFIG['updates']['1.1.0']['file_sizes']['linux'] = file_size
            
            return send_file(str(actual_file), as_attachment=True, download_name=filename)
        
        # 如果没有找到真实文件，创建模拟文件
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / "ecbot_ota_test"
        temp_dir.mkdir(exist_ok=True)
        
        file_path = temp_dir / filename
        
        if not file_path.exists():
            with open(file_path, 'wb') as f:
                if filename.endswith('.exe'):
                    # 创建一个小的模拟exe文件
                    f.write(b'MZ' + b'\x00' * (1024 * 1024 - 2))  # 1MB模拟文件
                elif filename.endswith('.dmg'):
                    f.write(b'\x00' * (2 * 1024 * 1024))  # 2MB模拟文件
                else:
                    f.write(b'ECBot Update Package\n' * 1000)
        
        file_size = file_path.stat().st_size
        logger.info(f"Serving simulated file: {filename} ({file_size} bytes)")
        
        # 更新配置中的文件大小
        if filename.endswith('.exe'):
            UPDATE_CONFIG['updates']['1.1.0']['file_sizes']['windows'] = file_size
        elif filename.endswith('.dmg'):
            UPDATE_CONFIG['updates']['1.1.0']['file_sizes']['darwin'] = file_size
        elif filename.endswith('.tar.gz'):
            UPDATE_CONFIG['updates']['1.1.0']['file_sizes']['linux'] = file_size
        
        return send_file(str(file_path), as_attachment=True, download_name=filename)
        
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