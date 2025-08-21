@echo off
REM ECBot Environment Variables Configuration Generator - Windows Version
REM Automatically find ECan installation path and generate .env file

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   ECBot Environment Config Generator (Windows)
echo ========================================
echo.

REM Find ECan installation path and bundle directory
set "ECAN_PATH="
set "BUNDLE_DIR="
set "ENV_PATH="

echo 🔍 Searching for ECan installation path...

REM 1. Check for running ECan processes and get their paths
for /f "tokens=2" %%A in ('tasklist /fo csv /v ^| findstr /i "ECan.exe\|eCan.exe" ^| findstr /v "Image Name"') do (
    for /f "tokens=*" %%B in ('wmic process where "name='%%~nxA'" get ExecutablePath /value 2^>nul ^| findstr "="') do (
        for /f "tokens=2 delims==" %%C in ("%%B") do (
            if exist "%%C" (
                set "ECAN_PATH=%%~dpC"
                set "ECAN_PATH=!ECAN_PATH:~0,-1!"
                goto :found_path
            )
        )
    )
)

REM 2. Check common installation paths (prioritize Program Files)
set "COMMON_PATHS=%PROGRAMFILES%\eCan;%PROGRAMFILES(X86)%\eCan;%PROGRAMFILES%\ECan;%LOCALAPPDATA%\ECan;%APPDATA%\ECan"

for %%P in (%COMMON_PATHS%) do (
    if exist "%%P\ECan.exe" (
        set "ECAN_PATH=%%P"
        goto :found_path
    )
    if exist "%%P\eCan.exe" (
        set "ECAN_PATH=%%P"
        goto :found_path
    )
)

REM 3. Check registry
for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "ECan" 2^>nul ^| findstr "InstallLocation"') do (
    if exist "%%B\ECan.exe" (
        set "ECAN_PATH=%%B"
        goto :found_path
    )
    if exist "%%B\eCan.exe" (
        set "ECAN_PATH=%%B"
        goto :found_path
    )
)

REM 4. Check current directory and parent directory
set "CURRENT_DIR=%~dp0"
if exist "%CURRENT_DIR%..\ECan.exe" (
    set "ECAN_PATH=%CURRENT_DIR%.."
    goto :found_path
)
if exist "%CURRENT_DIR%..\eCan.exe" (
    set "ECAN_PATH=%CURRENT_DIR%.."
    goto :found_path
)

REM 5. Check temporary directory (PyInstaller runtime)
if defined TEMP (
    for /d %%D in ("%TEMP%\_MEI*") do (
        if exist "%%D\ECan.exe" (
            set "BUNDLE_DIR=%%D"
            set "ECAN_PATH=%%D"
            echo ✅ Detected PyInstaller runtime environment
            goto :found_path
        )
        if exist "%%D\eCan.exe" (
            set "BUNDLE_DIR=%%D"
            set "ECAN_PATH=%%D"
            echo ✅ Detected PyInstaller runtime environment
            goto :found_path
        )
    )
)

REM 6. Manual path input
echo ❌ Could not automatically find ECan installation path
echo.
echo 💡 Tips:
echo    - If ECan is running, please close ECan before running this script
echo    - For PyInstaller packaged applications, run this script while ECan is running
echo.
echo Please choose:
echo 1. Manually enter ECan installation directory path
echo 2. Manually enter bundle directory path (PyInstaller temporary directory)
set /p "CHOICE=Please choose (1/2): "

if "!CHOICE!"=="2" (
    echo.
    echo Please enter bundle directory path (usually starts with _MEI):
    set /p "BUNDLE_DIR=Bundle path: "
    if exist "!BUNDLE_DIR!" (
        set "ECAN_PATH=!BUNDLE_DIR!"
        goto :found_path
    ) else (
        echo ❌ Error: Specified bundle directory does not exist
        pause
        exit /b 1
    )
) else (
    echo.
    echo Please enter ECan installation directory path:
    set /p "ECAN_PATH=ECan path: "

    if not exist "%ECAN_PATH%\ECan.exe" (
        if not exist "%ECAN_PATH%\eCan.exe" (
            echo ❌ Error: ECan.exe or eCan.exe not found in specified path
            pause
            exit /b 1
        )
    )
)

:found_path
echo ✅ Found ECan path: %ECAN_PATH%

REM Determine .env file path
if defined BUNDLE_DIR (
    set "ENV_PATH=%BUNDLE_DIR%\.env"
    echo 📄 .env file will be saved to bundle directory: %ENV_PATH%
    echo ⚠️  Note: PyInstaller temporary directory will be deleted after application closes
    echo    Consider placing configuration file in a persistent directory
) else (
    set "ENV_PATH=%ECAN_PATH%\.env"
    echo 📄 .env file will be saved to: %ENV_PATH%
)
echo.

REM Check existing configuration
if exist "%ENV_PATH%" (
    echo 📁 Found existing configuration file: %ENV_PATH%
    set /p "UPDATE_CONFIG=Do you want to update existing configuration? (Y/n): "
    if /i "!UPDATE_CONFIG!"=="n" (
        echo Operation cancelled
        pause
        exit /b 0
    )
)

REM Collect configuration information
echo 📋 Please enter API key configuration:
echo ========================================
echo.

REM API key configuration
echo 🔑 API Key Configuration:
echo ----------------------------------------

echo OpenAI API Key (input will be hidden, optional):
powershell -Command "$key = Read-Host -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))" > temp_openai.txt
set /p OPENAI_API_KEY=<temp_openai.txt
del temp_openai.txt

echo DashScope API Key (input will be hidden, optional):
powershell -Command "$key = Read-Host -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))" > temp_dash.txt
set /p DASHSCOPE_API_KEY=<temp_dash.txt
del temp_dash.txt

echo Claude API Key (input will be hidden, optional):
powershell -Command "$key = Read-Host -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))" > temp_claude.txt
set /p CLAUDE_API_KEY=<temp_claude.txt
del temp_claude.txt

echo Gemini API Key (input will be hidden, optional):
powershell -Command "$key = Read-Host -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))" > temp_gemini.txt
set /p GEMINI_API_KEY=<temp_gemini.txt
del temp_gemini.txt

echo.

REM Basic configuration
echo ⚙️ Basic Configuration:
echo ----------------------------------------
set /p "DEBUG_MODE=Debug mode (true/false) [false]: "
if "!DEBUG_MODE!"=="" set "DEBUG_MODE=false"

set /p "LOG_LEVEL=Log level (DEBUG/INFO/WARNING/ERROR) [INFO]: "
if "!LOG_LEVEL!"=="" set "LOG_LEVEL=INFO"

echo.

REM Display configuration summary
echo ========================================
echo 📋 Configuration Summary:
echo ========================================
if not "!OPENAI_API_KEY!"=="" echo OpenAI API: Configured
if not "!DASHSCOPE_API_KEY!"=="" echo DashScope API: Configured
if not "!CLAUDE_API_KEY!"=="" echo Claude API: Configured
if not "!GEMINI_API_KEY!"=="" echo Gemini API: Configured
echo Log level: !LOG_LEVEL!
echo Debug mode: !DEBUG_MODE!
echo.
echo 📂 Target file: %ENV_PATH%
echo.

set /p "CONFIRM=Confirm generating .env file? (Y/n): "
if /i "!CONFIRM!"=="n" (
    echo Operation cancelled
    pause
    exit /b 0
)

REM Generate .env file
echo.
echo 📝 Generating .env file...

(
echo # ECBot Environment Variables Configuration File
echo # Generated: %date% %time%
echo # Platform: Windows
echo # ECan Path: %ECAN_PATH%
if defined BUNDLE_DIR (
    echo # Bundle Directory: %BUNDLE_DIR%
    echo # Runtime Mode: PyInstaller Package
) else (
    echo # Runtime Mode: Standard Installation
)
echo.
echo # API Key Configuration
if not "!OPENAI_API_KEY!"=="" (
    echo # OpenAI API Key
    echo OPENAI_API_KEY=!OPENAI_API_KEY!
)
if not "!DASHSCOPE_API_KEY!"=="" (
    echo # DashScope API Key
    echo DASHSCOPE_API_KEY=!DASHSCOPE_API_KEY!
)
if not "!CLAUDE_API_KEY!"=="" (
    echo # Claude API Key
    echo CLAUDE_API_KEY=!CLAUDE_API_KEY!
)
if not "!GEMINI_API_KEY!"=="" (
    echo # Gemini API Key
    echo GEMINI_API_KEY=!GEMINI_API_KEY!
)
echo.
echo # Basic Configuration
echo # Log Level
echo LOG_LEVEL=!LOG_LEVEL!
echo # Debug Mode
echo DEBUG_MODE=!DEBUG_MODE!
) > "%ENV_PATH%"

if exist "%ENV_PATH%" (
    echo ✅ .env file generated successfully!
    echo 📄 File location: %ENV_PATH%
    echo.
    echo 💡 Tips:
    echo    - Restart ECan application to apply new configuration
    echo    - Please keep this configuration file secure, it contains sensitive information
    echo    - Do not share this file with others
) else (
    echo ❌ .env file generation failed!
    echo Please check if you have write permissions
)

echo.
echo Press any key to exit...
pause >nul
exit /b 0
