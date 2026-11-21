@echo off
cd /d "%~dp0.."
if not "%~1"=="" goto args
python -m pawtation gui
goto done
:args
python -m pawtation %*
:done
if errorlevel 1 pause
