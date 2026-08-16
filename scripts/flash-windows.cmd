@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0flash-windows.ps1" %*
exit /b %ERRORLEVEL%
