#!/bin/bash
# macOS代码签名证书处理脚本

# 将P12证书转换为Base64编码
convert_p12_to_base64() {
    local p12_file="$1"
    
    if [ ! -f "$p12_file" ]; then
        echo "错误: 证书文件不存在: $p12_file"
        return 1
    fi
    
    echo "转换证书为Base64编码..."
    local base64_file="${p12_file%.p12}.base64.txt"
    base64 -i "$p12_file" -o "$base64_file"
    
    echo "Base64编码已保存到: $base64_file"
    echo "Base64内容:"
    cat "$base64_file"
}

# 查看可用的代码签名身份
list_codesign_identities() {
    echo "可用的代码签名身份:"
    security find-identity -v -p codesigning
}

# 验证证书
verify_p12_certificate() {
    local p12_file="$1"
    local password="$2"
    
    if [ ! -f "$p12_file" ]; then
        echo "错误: 证书文件不存在: $p12_file"
        return 1
    fi
    
    echo "验证P12证书..."
    if [ -n "$password" ]; then
        security import "$p12_file" -k ~/Library/Keychains/login.keychain -P "$password" -T /usr/bin/codesign
    else
        security import "$p12_file" -k ~/Library/Keychains/login.keychain -T /usr/bin/codesign
    fi
}

# 使用示例:
# convert_p12_to_base64 "path/to/your/certificate.p12"
# list_codesign_identities
# verify_p12_certificate "path/to/your/certificate.p12" "your_password"

echo "macOS代码签名证书处理脚本"
echo "使用方法:"
echo "  convert_p12_to_base64 <p12文件路径>"
echo "  list_codesign_identities"
echo "  verify_p12_certificate <p12文件路径> [密码]"
