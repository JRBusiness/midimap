@echo off
cd /d "%~dp0"

REM MidiMap GUI Launcher for Windows

REM Try to find Python in various locations
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
    echo Using .venv Python
) else if exist "..\.venv\Scripts\python.exe" (
    set PYTHON_EXE=..\.venv\Scripts\python.exe
    echo Using parent .venv Python
) else if exist "Scripts\python.exe" (
    set PYTHON_EXE=Scripts\python.exe
    echo Using Scripts Python
) else (
    set PYTHON_EXE=python
    echo Using system Python
)

echo Python: %PYTHON_EXE%

REM Check if dependencies are installed
%PYTHON_EXE% -c "import mido" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    %PYTHON_EXE% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Warning: Some dependencies failed to install. Trying to continue anyway...
    )
)

REM Run the GUI via main.py
%PYTHON_EXE% main.py --gui

if errorlevel 1 (
    echo.
    echo Error: Failed to run GUI.
    echo.
    echo Make sure dependencies are installed:
    echo   %PYTHON_EXE% -m pip install -r requirements.txt
    pause
)
