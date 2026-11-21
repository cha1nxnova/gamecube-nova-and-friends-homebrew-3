@echo off
cd /d "%~dp0.."
if "%~1"=="" (
    python -m pawtation gui
) else (
    python -m pawtation %*
)
if errorlevel 1 pause
