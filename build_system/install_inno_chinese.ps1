# Install Inno Setup Chinese Simplified Language Pack
# This script downloads and installs the Chinese language file for Inno Setup

Write-Host "=== Installing Inno Setup Chinese Language Pack ===" -ForegroundColor Cyan

# Check if Inno Setup is installed
$innoPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $innoPath)) {
    Write-Host "ERROR: Inno Setup 6 not found at: $innoPath" -ForegroundColor Red
    Write-Host "Please install Inno Setup 6 first from: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    exit 1
}

Write-Host "Inno Setup found at: $innoPath" -ForegroundColor Green

# Define language file URL and destination
$LangUrl = "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/Unofficial/ChineseSimplified.isl"
$LangDir = "${env:ProgramFiles(x86)}\Inno Setup 6\Languages"
$LangPath = "$LangDir\ChineseSimplified.isl"

# Check if language file already exists
if (Test-Path $LangPath) {
    Write-Host "Chinese language pack already installed at: $LangPath" -ForegroundColor Yellow
    $fileSize = (Get-Item $LangPath).Length
    Write-Host "File size: $fileSize bytes" -ForegroundColor Gray
    
    $response = Read-Host "Do you want to reinstall? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "Installation cancelled" -ForegroundColor Yellow
        exit 0
    }
}

# Download language file
Write-Host "Downloading Chinese Simplified language file..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $LangUrl -OutFile $LangPath -UseBasicParsing
    Write-Host "Download completed" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to download language file" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Verify installation
if (Test-Path $LangPath) {
    $fileSize = (Get-Item $LangPath).Length
    Write-Host "SUCCESS: Chinese language pack installed at: $LangPath" -ForegroundColor Green
    Write-Host "File size: $fileSize bytes" -ForegroundColor Gray
    
    # Verify file content (basic check)
    $content = Get-Content $LangPath -Raw -Encoding UTF8
    if ($content -match "ChineseSimplified" -or $content -match "中文") {
        Write-Host "Language file content verified" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Language file content may be invalid" -ForegroundColor Yellow
    }
} else {
    Write-Host "ERROR: Language pack installation failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Cyan
Write-Host "You can now build installers with Chinese language support" -ForegroundColor Green
Write-Host "Run: python build.py prod" -ForegroundColor Gray
