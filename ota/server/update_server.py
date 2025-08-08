#!/usr/bin/env python3
"""
简单的OTA更新服务器
用于测试和开发
"""

from flask import Flask, jsonify, request, send_file
import os
import json
from pathlib import Path

app = Flask(__name__)

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
                "windows": "https://updates.ecbot.com/downloads/ECBot-1.1.0.exe",
                "darwin": "https://updates.ecbot.com/downloads/ECBot-1.1.0.dmg",
                "linux": "https://updates.ecbot.com/downloads/ECBot-1.1.0.tar.gz"
            },
            "file_sizes": {
                "windows": 41943040,
                "darwin": 52428800,
                "linux": 35651584
            },
            "signatures": {
                "windows": "DEF456...",
                "darwin": "ABC123...",
                "linux": "GHI789..."
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
        
        print(f"Update check: {app_name} v{current_version} on {platform}-{arch}")
        
        # 检查是否有更新
        latest_version = UPDATE_CONFIG['latest_version']
        has_update = current_version < latest_version
        
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
    """Sparkle/winSparkle appcast文件"""
    try:
        appcast_path = Path(__file__).parent / "appcast.xml"
        if appcast_path.exists():
            return send_file(str(appcast_path), mimetype='application/rss+xml')
        else:
            return "Appcast not found", 404
    except Exception as e:
        return f"Error serving appcast: {str(e)}", 500

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

if __name__ == '__main__':
    print("Starting ECBot Update Server...")
    print("Available endpoints:")
    print("  - GET /api/check-update")
    print("  - GET /api/download-latest")
    print("  - GET /appcast.xml")
    print("  - GET /health")
    
    # 在开发模式下运行
    app.run(host='0.0.0.0', port=8080, debug=True)