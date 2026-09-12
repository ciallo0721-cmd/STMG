@echo off
cd /d "%~dp0"
rem 不带参数 -> 打开启动器；带参数 -> 直接当剧本启动器用
if "%~1"=="" (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" launcher.py
    ) else (
        python launcher.py
    )
) else (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" start.py %*
    ) else (
        python start.py %*
    )
)
if errorlevel 1 pause
