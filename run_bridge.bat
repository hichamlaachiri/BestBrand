@echo off
cd /d "%~dp0"
if exist ".\venv\Scripts\activate.bat" (
    call .\venv\Scripts\activate.bat 2>nul
)
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py main.py
) else (
    python main.py
)
pause


