@echo off
cd /d "%~dp0"
rem 调试阶段先用 python.exe（有控制台，报错看得见）。
rem 以后嫌控制台碍眼，把下面的 python.exe 换成 pythonw.exe 就行。
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" launcher.py
) else (
    python launcher.py
)
if errorlevel 1 pause
