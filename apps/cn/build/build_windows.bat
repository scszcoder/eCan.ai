@echo off
REM =============================================================================
REM Build Script for eCan.cn (CN Version) - Windows
REM =============================================================================
REM Usage: build_windows.bat [options]
REM
REM Options:
REM   --clean         Clean build artifacts before building
REM   --test          Build for testing (no code signing)
REM   --release       Build for release (with code signing)
REM
REM Environment Variables:
REM   ECAN_APP_ID     Set to 'cn' automatically
REM   BUILD_NUMBER    CI build number (optional)
REM =============================================================================

setlocal enabledelayedexpansion

REM Configuration
set "ECAN_APP_ID=cn"
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "BUILD_DIR=%PROJECT_ROOT%\build"
set "DIST_DIR=%PROJECT_ROOT%\dist"
set "VERSION=1.0.0"
set "BUILD_NUMBER=%BUILD_NUMBER:=1%"

REM Parse arguments
set "BUILD_MODE=test"
set "CLEAN_BUILD="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--clean" set "CLEAN_BUILD=1" & shift & goto parse_args
if /i "%~1"=="--test" set "BUILD_MODE=test" & shift & goto parse_args
if /i "%~1"=="--release" set "BUILD_MODE=release" & shift & goto parse_args
if /i "%~1"=="--help" goto usage
shift
goto parse_args

:usage
echo Usage: %~n0 [OPTIONS]
echo.
echo Options:
echo   --clean    Clean build artifacts
echo   --test     Build for testing (no signing)
echo   --release  Build for release (with signing)
echo   --help     Show this help
exit /b 1

:args_done

echo ================================================================================
echo Building eCan.cn (CN Version)...
echo Build mode: %BUILD_MODE%
echo Version: %VERSION%
echo Build number: %BUILD_NUMBER%
echo ================================================================================

cd /d "%PROJECT_ROOT%"

REM Check prerequisites
echo [INFO] Checking prerequisites...
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is required but not found.
    exit /b 1
)

REM Install dependencies
echo [INFO] Installing dependencies...
pip install -r requirements-cn.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

REM Clean if requested
if defined CLEAN_BUILD (
    echo [INFO] Cleaning build artifacts...
    if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
    if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
    if exist "%PROJECT_ROOT%\build" rmdir /s /q "%PROJECT_ROOT%\build"
    if exist "%PROJECT_ROOT%\dist" rmdir /s /q "%PROJECT_ROOT%\dist"
    if exist "%PROJECT_ROOT%\*.spec" del /q "%PROJECT_ROOT%\*.spec"
    echo [INFO] Clean complete
)

REM Build
echo [INFO] Building eCan.cn...

set "SPEC_FILE=%PROJECT_ROOT%\eCan_cn.spec"
if not exist "%SPEC_FILE%" (
    echo [WARN] CN-specific spec file not found, using default...
    set "SPEC_FILE=%PROJECT_ROOT%\eCan.spec"
)

REM Run PyInstaller
python -m PyInstaller "%SPEC_FILE%" --noconfirm --log-level=WARN
if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

if /i "%BUILD_MODE%"=="release" (
    echo [INFO] Signing executable...
    REM Windows code signing would go here
    REM signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com "%DIST_DIR%\eCan.cn.exe"
)

echo [INFO] Build complete: %DIST_DIR%
echo ================================================================================
echo Build finished successfully!
exit /b 0
