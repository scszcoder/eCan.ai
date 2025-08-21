# Windows代码签名证书转换脚本

# 将PFX证书转换为Base64编码
function Convert-PfxToBase64 {
    param(
        [Parameter(Mandatory=$true)]
        [string]$PfxPath
    )
    
    if (-not (Test-Path $PfxPath)) {
        Write-Error "证书文件不存在: $PfxPath"
        return
    }
    
    try {
        $bytes = [IO.File]::ReadAllBytes($PfxPath)
        $base64 = [Convert]::ToBase64String($bytes)
        
        Write-Host "证书Base64编码:"
        Write-Host $base64
        
        # 保存到文件
        $outputFile = [IO.Path]::ChangeExtension($PfxPath, ".base64.txt")
        $base64 | Out-File -FilePath $outputFile -Encoding ASCII
        Write-Host "Base64编码已保存到: $outputFile"
        
        return $base64
    }
    catch {
        Write-Error "转换失败: $_"
    }
}

# 验证PFX证书
function Test-PfxCertificate {
    param(
        [Parameter(Mandatory=$true)]
        [string]$PfxPath,
        [string]$Password
    )
    
    try {
        if ($Password) {
            $securePassword = ConvertTo-SecureString $Password -AsPlainText -Force
            $cert = Get-PfxCertificate -FilePath $PfxPath -Password $securePassword
        } else {
            $cert = Get-PfxCertificate -FilePath $PfxPath
        }
        
        Write-Host "证书信息:"
        Write-Host "  主题: $($cert.Subject)"
        Write-Host "  颁发者: $($cert.Issuer)"
        Write-Host "  有效期: $($cert.NotBefore) 到 $($cert.NotAfter)"
        Write-Host "  指纹: $($cert.Thumbprint)"
        
        return $cert
    }
    catch {
        Write-Error "验证证书失败: $_"
    }
}

# 使用示例:
# Convert-PfxToBase64 -PfxPath "path\to\your\certificate.pfx"
# Test-PfxCertificate -PfxPath "path\to\your\certificate.pfx" -Password "your_password"
