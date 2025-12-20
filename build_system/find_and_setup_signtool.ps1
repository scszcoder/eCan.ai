# 查找并设置 signtool 环境
# 解决本地构建时 signtool 不可用的问题

Write-Host "🔍 查找并设置 signtool 环境" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# 1. 检查当前 PATH 中是否有 signtool
Write-Host "`n1️⃣ 检查当前环境" -ForegroundColor Yellow
$currentSigntool = Get-Command signtool -ErrorAction SilentlyContinue
if ($currentSigntool) {
    Write-Host "✅ signtool 已在 PATH 中: $($currentSigntool.Source)" -ForegroundColor Green
    signtool /?
    exit 0
}

Write-Host "❌ signtool 不在当前 PATH 中" -ForegroundColor Red

# 2. 搜索系统中的 signtool
Write-Host "`n2️⃣ 搜索系统中的 signtool" -ForegroundColor Yellow

$searchPaths = @(
    "${env:ProgramFiles(x86)}\Windows Kits",
    "${env:ProgramFiles}\Windows Kits",
    "${env:ProgramFiles(x86)}\Microsoft SDKs",
    "${env:ProgramFiles}\Microsoft SDKs",
    "${env:ProgramFiles(x86)}\Microsoft Visual Studio",
    "${env:ProgramFiles}\Microsoft Visual Studio"
)

$foundSigntools = @()

foreach ($basePath in $searchPaths) {
    if (Test-Path $basePath) {
        Write-Host "🔍 搜索: $basePath" -ForegroundColor Gray
        
        try {
            $signtoolFiles = Get-ChildItem -Path $basePath -Recurse -Name "signtool.exe" -ErrorAction SilentlyContinue
            foreach ($file in $signtoolFiles) {
                $fullPath = Join-Path $basePath $file
                $foundSigntools += @{
                    Path = $fullPath
                    Directory = Split-Path $fullPath
                    Size = (Get-Item $fullPath).Length
                    Version = "Unknown"
                }
                Write-Host "  ✅ 找到: $fullPath" -ForegroundColor Green
            }
        } catch {
            Write-Host "  ⚠️ 搜索失败: $_" -ForegroundColor Yellow
        }
    }
}

if ($foundSigntools.Count -eq 0) {
    Write-Host "❌ 未找到 signtool.exe" -ForegroundColor Red
    Write-Host "请安装 Windows SDK 或 Visual Studio" -ForegroundColor Yellow
    Write-Host "下载地址: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/" -ForegroundColor Cyan
    exit 1
}

# 3. 选择最佳的 signtool
Write-Host "`n3️⃣ 选择最佳的 signtool" -ForegroundColor Yellow

# 优先级：Windows Kits > Visual Studio > 其他
$bestSigntool = $null
$bestScore = -1

foreach ($signtool in $foundSigntools) {
    $score = 0
    $path = $signtool.Path
    
    # Windows Kits 优先级最高
    if ($path -like "*Windows Kits*") {
        $score += 100
        
        # 版本号越高越好
        if ($path -match "10\.0\.(\d+)\.") {
            $buildNumber = [int]$matches[1]
            $score += $buildNumber / 1000  # 转换为小数避免溢出
        }
        
        # x64 版本优先
        if ($path -like "*x64*") {
            $score += 10
        }
    }
    # Visual Studio 次优先级
    elseif ($path -like "*Visual Studio*") {
        $score += 50
    }
    
    Write-Host "  📋 $path (评分: $score)" -ForegroundColor Gray
    
    if ($score > $bestScore) {
        $bestScore = $score
        $bestSigntool = $signtool
    }
}

if ($bestSigntool) {
    $chosenPath = $bestSigntool.Path
    $chosenDir = $bestSigntool.Directory
    
    Write-Host "✅ 选择: $chosenPath" -ForegroundColor Green
    
    # 4. 测试选择的 signtool
    Write-Host "`n4️⃣ 测试选择的 signtool" -ForegroundColor Yellow
    
    try {
        $testResult = & $chosenPath /? 2>&1
        if ($LASTEXITCODE -eq 0 -or $testResult -like "*Microsoft*") {
            Write-Host "✅ signtool 工作正常" -ForegroundColor Green
        } else {
            Write-Host "⚠️ signtool 可能有问题" -ForegroundColor Yellow
            Write-Host "输出: $testResult" -ForegroundColor Gray
        }
    } catch {
        Write-Host "❌ signtool 测试失败: $_" -ForegroundColor Red
        exit 1
    }
    
    # 5. 添加到当前会话的 PATH
    Write-Host "`n5️⃣ 配置环境变量" -ForegroundColor Yellow
    
    $currentPath = $env:PATH
    if ($currentPath -notlike "*$chosenDir*") {
        $env:PATH = "$chosenDir;$currentPath"
        Write-Host "✅ 已添加到当前会话 PATH: $chosenDir" -ForegroundColor Green
        
        # 验证添加成功
        $newSigntool = Get-Command signtool -ErrorAction SilentlyContinue
        if ($newSigntool) {
            Write-Host "✅ signtool 现在可用: $($newSigntool.Source)" -ForegroundColor Green
        } else {
            Write-Host "❌ PATH 添加失败" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ 目录已在 PATH 中" -ForegroundColor Green
    }
    
    # 6. 提供永久配置建议
    Write-Host "`n6️⃣ 永久配置建议" -ForegroundColor Yellow
    Write-Host "要永久添加到系统 PATH，请运行以下命令 (需要管理员权限):" -ForegroundColor Gray
    Write-Host "[Environment]::SetEnvironmentVariable('PATH', `"$chosenDir;`" + [Environment]::GetEnvironmentVariable('PATH', 'Machine'), 'Machine')" -ForegroundColor Cyan
    
    Write-Host "`n或者手动添加到系统环境变量:" -ForegroundColor Gray
    Write-Host "1. 右键 '此电脑' -> '属性'" -ForegroundColor Gray
    Write-Host "2. '高级系统设置' -> '环境变量'" -ForegroundColor Gray
    Write-Host "3. 在 '系统变量' 中找到 'PATH'" -ForegroundColor Gray
    Write-Host "4. 添加路径: $chosenDir" -ForegroundColor Cyan
    
    # 7. 测试构建系统
    Write-Host "`n7️⃣ 测试构建系统签名检测" -ForegroundColor Yellow
    
    try {
        $testScript = @"
import sys
sys.path.append('build_system')
from signing_manager import create_signing_manager
from unified_build import UnifiedBuildSystem

build_system = UnifiedBuildSystem()
signing_manager = create_signing_manager(build_system.project_root, build_system.config.config)

print('Windows签名配置:')
print('  启用:', signing_manager.should_sign('prod'))
print('  平台:', signing_manager.platform)

# 测试工具检测
tool_available = signing_manager._check_tool_available('signtool')
print('  signtool可用:', tool_available)
"@
        
        $testScript | Out-File -FilePath "temp_test_signing.py" -Encoding UTF8
        $pythonResult = python temp_test_signing.py 2>&1
        
        Write-Host "构建系统测试结果:" -ForegroundColor Gray
        Write-Host $pythonResult -ForegroundColor Gray
        
        Remove-Item "temp_test_signing.py" -ErrorAction SilentlyContinue
        
    } catch {
        Write-Host "⚠️ 构建系统测试失败: $_" -ForegroundColor Yellow
    }
    
    Write-Host "`n🎉 signtool 配置完成！" -ForegroundColor Green
    Write-Host "现在可以运行构建命令进行签名了" -ForegroundColor Green
    
} else {
    Write-Host "❌ 未找到可用的 signtool" -ForegroundColor Red
    exit 1
}
