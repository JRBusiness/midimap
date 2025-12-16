@echo off
setlocal enabledelayedexpansion

echo ============================================
echo MidiMap - Building Standalone Executable
echo ============================================
echo.

REM Find Python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
    echo Using .venv Python
) else if exist "Scripts\python.exe" (
    set PYTHON_EXE=Scripts\python.exe
    echo Using Scripts Python
) else (
    set PYTHON_EXE=python
    echo Using system Python
)

echo Python: %PYTHON_EXE%
echo.

REM Check if PyInstaller is installed
%PYTHON_EXE% -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    %PYTHON_EXE% -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Build the executable
echo.
echo Building MidiMap.exe...
echo This may take several minutes...
echo.

%PYTHON_EXE% -m PyInstaller midimap.spec --noconfirm

if errorlevel 1 (
    echo.
    echo ============================================
    echo Build FAILED!
    echo ============================================
    pause
    exit /b 1
)

echo.
echo ============================================
echo Build SUCCESSFUL!
echo ============================================
echo.

REM Copy config.json to dist folder for user editing
echo Copying config.json to dist folder...
copy /Y config.json dist\config.json >nul

echo.
echo Executable location: dist\MidiMap.exe
echo Config file: dist\config.json
echo.

REM Check file size
for %%A in (dist\MidiMap.exe) do set size=%%~zA
set /a size_mb=%size%/1048576
echo File size: approximately %size_mb% MB
echo.
echo IMPORTANT: To distribute the application, share the entire 'dist' folder
echo The config.json in dist folder can be edited by users.
echo.

pause

