@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%validate-v2-windows.ps1" %*
exit /b %ERRORLEVEL%
