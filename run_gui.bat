@echo off
cd /d "%~dp0"

REM Try to use virtual environment Python if it exists
if exist "Scripts\python.exe" (
    set PYTHON_EXE=Scripts\python.exe
) else (
    set PYTHON_EXE=python
)

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

REM Run the GUI
%PYTHON_EXE% gui.py

if errorlevel 1 (
    echo.
    echo Error: Failed to run GUI.
    echo.
    echo Make sure dependencies are installed:
    echo   %PYTHON_EXE% -m pip install mido pynput
    echo.
    echo Note: python-rtmidi is optional but recommended for better MIDI support.
    echo On Python 3.13, you may need to use Python 3.12 or install python-rtmidi manually.
    pause
)
