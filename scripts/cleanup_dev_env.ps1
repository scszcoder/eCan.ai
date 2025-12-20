# ECBot 开发环境清理脚本
# 用于关闭诊断模式和清理运行中的进程

Write-Host "================================" -ForegroundColor Cyan
Write-Host "ECBot Development Environment Cleanup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 1. 清除诊断模式环境变量
Write-Host "1. Clearing diagnostic environment variables..." -ForegroundColor Yellow
Remove-Item Env:\EC_DIAG -ErrorAction SilentlyContinue
Remove-Item Env:\EC_DIAG_LOG -ErrorAction SilentlyContinue

if ($env:EC_DIAG) {
    Write-Host "   ✗ EC_DIAG still set: $env:EC_DIAG" -ForegroundColor Red
} else {
    Write-Host "   ✓ EC_DIAG cleared" -ForegroundColor Green
}

if ($env:EC_DIAG_LOG) {
    Write-Host "   ✗ EC_DIAG_LOG still set: $env:EC_DIAG_LOG" -ForegroundColor Red
} else {
    Write-Host "   ✓ EC_DIAG_LOG cleared" -ForegroundColor Green
}

Write-Host ""

# 2. 查找并关闭 ECBot 相关的 Python 进程
Write-Host "2. Finding ECBot Python processes..." -ForegroundColor Yellow

$ecbotProcesses = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*ecbot*" -or $_.Path -like "*WorkSpace\ecbot*"
}

if ($ecbotProcesses) {
    Write-Host "   Found $($ecbotProcesses.Count) process(es):" -ForegroundColor Yellow
    $ecbotProcesses | ForEach-Object {
        Write-Host "   - PID: $($_.Id), Name: $($_.ProcessName), Path: $($_.Path)" -ForegroundColor Gray
    }
    
    Write-Host ""
    $confirm = Read-Host "   Terminate these processes? (Y/N)"
    
    if ($confirm -eq 'Y' -or $confirm -eq 'y') {
        $ecbotProcesses | ForEach-Object {
            try {
                Stop-Process -Id $_.Id -Force -ErrorAction Stop
                Write-Host "   ✓ Terminated PID: $($_.Id)" -ForegroundColor Green
            } catch {
                Write-Host "   ✗ Failed to terminate PID: $($_.Id) - $($_.Exception.Message)" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "   Skipped process termination" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ✓ No ECBot processes found" -ForegroundColor Green
}

Write-Host ""

# 3. 清理诊断日志文件（可选）
Write-Host "3. Diagnostic log file..." -ForegroundColor Yellow
$diagLog = Join-Path $env:TEMP "ecan_diag.log"

if (Test-Path $diagLog) {
    $logSize = (Get-Item $diagLog).Length
    Write-Host "   Found: $diagLog ($logSize bytes)" -ForegroundColor Gray
    
    $clearLog = Read-Host "   Clear diagnostic log? (Y/N)"
    if ($clearLog -eq 'Y' -or $clearLog -eq 'y') {
        try {
            Remove-Item $diagLog -Force -ErrorAction Stop
            Write-Host "   ✓ Diagnostic log cleared" -ForegroundColor Green
        } catch {
            Write-Host "   ✗ Failed to clear log: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "   Kept diagnostic log" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ✓ No diagnostic log found" -ForegroundColor Green
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Cleanup completed!" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now run the application normally:" -ForegroundColor White
Write-Host "  python main.py" -ForegroundColor Gray
Write-Host ""
