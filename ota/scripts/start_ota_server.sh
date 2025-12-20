#!/bin/bash
# Quick start script for OTA server

echo "🚀 启动 OTA 更新服务器..."
echo ""
echo "服务器地址: http://127.0.0.1:8080"
echo "PKG 文件: dist/eCan-1.0.0-macos-aarch64.pkg (752MB)"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "================================"
echo ""

cd "$(dirname "$0")"
python3 ota/server/update_server.py
