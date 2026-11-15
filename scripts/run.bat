@echo off
cd /d "%~dp0.."
python -m pawtation %*
if errorlevel 1 pause
