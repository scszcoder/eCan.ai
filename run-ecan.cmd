@echo off
rem Launcher for run-ecan.ps1 that bypasses the PowerShell execution policy
rem for this single invocation only (no system/user setting is changed).
rem Usage:  run-ecan            run-ecan -KeepVite            run-ecan -Prod -Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-ecan.ps1" %*
