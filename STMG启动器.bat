@echo off
cd /d "%~dp0"
rem Launcher UI needs CustomTkinter; install it on first run if missing.
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% -c "import customtkinter" 2>nul
if errorlevel 1 (
    echo Launcher needs CustomTkinter, installing now...
    %PY% -m pip install customtkinter -i https://mirrors.aliyun.com/pypi/simple/
    echo.
)

rem Use python.exe in debug phase so errors are visible in console.
%PY% launcher.py
if errorlevel 1 pause
