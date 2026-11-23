@echo off
setlocal
cd /d "%~dp0"
if not exist "chat\server.py" (
    echo Extract the entire ZIP first, then open this launcher from the extracted folder.
    pause
    exit /b 1
)
where python >nul 2>&1
if not errorlevel 1 (
    python "chat\server.py" --open
) else (
    py -3 "chat\server.py" --open
)
if errorlevel 1 (
    echo The chat server stopped. Read the error above and keep this window open while using chat.
    pause
)
