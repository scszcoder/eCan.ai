# Windows signtool 安装和配置指南

## 🎯 本地安装 signtool

### 方法1: 安装 Windows SDK (推荐)

#### 下载安装
1. 访问 [Windows SDK 下载页面](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/)
2. 下载最新版本 (Windows 11 SDK 或 Windows 10 SDK)
3. 运行安装程序，选择以下组件：
   - ✅ **Windows SDK Signing Tools for Desktop Apps**
   - ✅ **Windows SDK for UWP Managed Apps** (可选)

#### 验证安装
```powershell
# 查找 signtool 位置
where signtool

# 测试 signtool
signtool /?

# 常见安装路径
# C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe
# C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe
```

### 方法2: 使用 Visual Studio Installer
1. 打开 Visual Studio Installer
2. 修改现有安装或安装新的 Visual Studio
3. 在 "Individual components" 中选择：
   - ✅ **Windows 10/11 SDK (latest version)**
   - ✅ **MSVC v143 - VS 2022 C++ x64/x86 build tools**

### 方法3: 使用 Chocolatey (命令行)
```powershell
# 安装 Chocolatey (管理员权限)
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 安装 Windows SDK
choco install windows-sdk-10-version-2004-all

# 或者只安装构建工具
choco install visualstudio2022buildtools --package-parameters "--add Microsoft.VisualStudio.Workload.VCTools"
```

## 🚀 GitHub Actions CI 配置

### 完整的 CI 配置文件

创建 `.github/workflows/build-and-sign.yml`：

```yaml
name: Build and Sign eCan.ai

on:
  push:
    branches: [ main, develop ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]

jobs:
  build-windows:
    runs-on: windows-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
      
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        
    - name: Install Windows SDK (signtool)
      shell: powershell
      run: |
        # 方法1: 使用 Chocolatey 安装 Windows SDK
        choco install windows-sdk-10-version-2004-all -y
        
        # 方法2: 或者安装 Visual Studio Build Tools
        # choco install visualstudio2022buildtools --package-parameters "--add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.Windows10SDK.19041" -y
        
        # 验证安装
        $signtool = Get-ChildItem -Path "C:\Program Files (x86)\Windows Kits" -Recurse -Name "signtool.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($signtool) {
          $signtoolPath = "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe"
          $resolved = Resolve-Path $signtoolPath | Select-Object -First 1
          Write-Host "Found signtool at: $($resolved.Path)"
          & $resolved.Path /?
        } else {
          Write-Error "signtool not found after installation"
          exit 1
        }
        
    - name: Add signtool to PATH
      shell: powershell
      run: |
        # 查找 signtool 并添加到 PATH
        $signtoolDir = Get-ChildItem -Path "C:\Program Files (x86)\Windows Kits\10\bin" -Directory | 
                       Sort-Object Name -Descending | 
                       Select-Object -First 1 | 
                       ForEach-Object { Join-Path $_.FullName "x64" }
        
        if (Test-Path (Join-Path $signtoolDir "signtool.exe")) {
          Write-Host "Adding to PATH: $signtoolDir"
          echo "$signtoolDir" | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
        } else {
          Write-Error "signtool.exe not found in expected location"
          exit 1
        }
        
    - name: Verify signtool availability
      run: |
        signtool /?
        echo "signtool is available!"
        
    - name: Install Python dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements-windows.txt
        
    - name: Set up certificate environment
      env:
        CERT_PASSWORD: ${{ secrets.CERT_PASSWORD }}
        CERT_BASE64: ${{ secrets.CERT_BASE64 }}
      shell: powershell
      run: |
        # 如果有 base64 编码的证书，解码并保存
        if ($env:CERT_BASE64) {
          $certBytes = [System.Convert]::FromBase64String($env:CERT_BASE64)
          $certPath = "build_system\certificates\production_certificate.pfx"
          [System.IO.File]::WriteAllBytes($certPath, $certBytes)
          Write-Host "Certificate saved to: $certPath"
        } else {
          # 使用测试证书
          python build_system/create_test_certificate.py
        }
        
    - name: Build and sign eCan.ai
      env:
        CERT_PASSWORD: ${{ secrets.CERT_PASSWORD }}
      run: |
        # 提取版本号
        if ($env:GITHUB_REF -match 'refs/tags/v(.+)') {
          $version = $matches[1]
        } else {
          $version = "1.0.0-$($env:GITHUB_SHA.Substring(0,7))"
        }
        
        Write-Host "Building version: $version"
        python build_system/unified_build.py prod --version $version
        
    - name: Test signing functionality
      run: |
        python build_system/test_signing_flow.py
        
    - name: Upload build artifacts
      uses: actions/upload-artifact@v3
      with:
        name: ecan-windows-signed
        path: |
          dist/*.exe
          dist/*.msi
          ota/server/signatures_*.json
          
    - name: Create Release (on tag)
      if: startsWith(github.ref, 'refs/tags/v')
      uses: softprops/action-gh-release@v1
      with:
        files: |
          dist/*.exe
          dist/*.msi
        draft: false
        prerelease: false
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 简化版本 (仅安装 signtool)

如果只需要安装 signtool，可以使用这个简化配置：

```yaml
- name: Install signtool
  shell: powershell
  run: |
    # 使用预安装的 Visual Studio 组件
    $vsPath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Enterprise"
    if (-not (Test-Path $vsPath)) {
      $vsPath = "${env:ProgramFiles}\Microsoft Visual Studio\2022\Enterprise"
    }
    
    # 查找 Windows SDK
    $sdkPath = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Directory | 
               Sort-Object Name -Descending | 
               Select-Object -First 1
    
    if ($sdkPath) {
      $signtoolPath = Join-Path $sdkPath.FullName "x64\signtool.exe"
      if (Test-Path $signtoolPath) {
        $signtoolDir = Split-Path $signtoolPath
        echo "$signtoolDir" | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
        Write-Host "Found signtool at: $signtoolPath"
      }
    }
    
    # 如果没找到，安装 Windows SDK
    if (-not (Get-Command signtool -ErrorAction SilentlyContinue)) {
      Write-Host "Installing Windows SDK..."
      choco install windows-sdk-10-version-2004-all -y
      
      # 重新查找并添加到 PATH
      $newSdkPath = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Directory | 
                    Sort-Object Name -Descending | 
                    Select-Object -First 1 | 
                    ForEach-Object { Join-Path $_.FullName "x64" }
      echo "$newSdkPath" | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
    }
```

## 🔐 GitHub Secrets 配置

在 GitHub 仓库设置中添加以下 Secrets：

### 必需的 Secrets
```
CERT_PASSWORD          # 证书密码
CERT_BASE64           # base64 编码的证书文件 (可选)
```

### 生成 base64 证书
```powershell
# 将 .pfx 证书转换为 base64
$certBytes = [System.IO.File]::ReadAllBytes("path\to\certificate.pfx")
$certBase64 = [System.Convert]::ToBase64String($certBytes)
Write-Host $certBase64
```

## ✅ 验证配置

### 本地测试
```powershell
# 测试 signtool
signtool sign /? 

# 测试证书
signtool sign /f "build_system\certificates\test_certificate.pfx" /p "test123" /t "http://timestamp.digicert.com" "path\to\test.exe"
```

### CI 测试
推送代码到 GitHub，检查 Actions 日志确认：
1. ✅ signtool 安装成功
2. ✅ 证书配置正确  
3. ✅ 签名流程正常
4. ✅ 构建产物包含签名

---

**注意**: 生产环境建议使用商业代码签名证书，测试证书仅用于开发。
