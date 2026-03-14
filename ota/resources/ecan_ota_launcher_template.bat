@echo off
setlocal
timeout /t __DELAY_SECONDS__ /nobreak >nul
echo [OTA] Launching installer: __INSTALLER_COMMAND__
start "" __INSTALLER_COMMAND__
(del "%~f0" >nul 2>&1)
