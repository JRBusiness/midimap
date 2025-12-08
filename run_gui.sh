#!/bin/bash

# MidiMap GUI Launcher for Linux/macOS

cd "$(dirname "$0")"

# Find Python executable
if [ -d ".venv" ]; then
    PYTHON=".venv/bin/python"
    echo "Using .venv Python"
elif [ -d "../.venv" ]; then
    PYTHON="../.venv/bin/python"
    echo "Using parent .venv Python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
    echo "Using system Python 3"
else
    PYTHON="python"
    echo "Using system Python"
fi

echo "Python: $PYTHON"

# Check if mido is installed
if ! $PYTHON -c "import mido" 2>/dev/null; then
    echo "Installing dependencies..."
    $PYTHON -m pip install -r requirements.txt
fi

# Run the GUI via main.py
$PYTHON main.py --gui

if [ $? -ne 0 ]; then
    echo ""
    echo "Error: Failed to run GUI."
    echo ""
    echo "Make sure dependencies are installed:"
    echo "  $PYTHON -m pip install -r requirements.txt"
    echo ""
    echo "On Linux, you may also need:"
    echo "  sudo apt install xdotool"
fi
