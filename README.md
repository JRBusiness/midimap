# MIDI to Keyboard Mapper
<img width="951" height="882" alt="image" src="https://github.com/user-attachments/assets/56f1a5ee-62ab-44d2-91e2-21096fd7305f" />

A cross-platform application that maps MIDI keyboard input to computer keyboard keys, allowing you to use your MIDI controller as a keyboard input device. Perfect for gaming, music production, and other applications where you want MIDI control.

**Supports:** Windows, macOS, and Linux

## Features

- **Interactive GUI** - Easy-to-use graphical interface for mapping MIDI notes to keyboard keys
- **Hotkey Support** - Assign single keys or key combinations (e.g., `ctrl+c`, `shift+f1`)
- **Multiple Profiles** - Create and switch between different mapping profiles
- **Real-time MIDI Detection** - See MIDI notes as you play them
- **Game Compatible** - Uses Windows API SendInput for compatibility with games and applications
- **Profile Management** - Create, rename, delete, and switch between profiles

## Installation

1. **Install Python** (3.7 or higher)
   - Download from [python.org](https://www.python.org/downloads/)

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   Required packages:
   - `mido` - MIDI input/output handling
   - `python-rtmidi` - MIDI backend for mido
   - `pynput` - Keyboard input capture (for GUI and macOS/Linux fallback)

3. **Platform-Specific Requirements**

   **Linux:**
   - Install `xdotool` for best results (recommended):
     ```bash
     sudo apt install xdotool    # Debian/Ubuntu
     sudo yum install xdotool    # RedHat/CentOS
     ```
   - Alternatively, `pynput` can be used but requires X11

   **macOS:**
   - No additional system packages required
   - Uses `pynput` by default, falls back to AppleScript if needed

   **Windows:**
   - No additional system packages required
   - Uses Windows API directly

## Usage

### GUI Mode (Recommended)

1. **Launch the GUI**
   ```bash
   python gui.py
   ```
   Or double-click `run_gui.bat` on Windows

2. **Connect Your MIDI Device**
   - Select your MIDI input port from the dropdown
   - Click "Connect"

3. **Assign Keys**
   - Play a MIDI note (or enter the note number manually)
   - Click "Capture Key/Combo" and press the keyboard key you want to assign
   - Click "Assign" to save the mapping

4. **Enable Mapping**
   - Check "Enable MIDI to Keyboard Mapping" to activate
   - Play your MIDI keyboard - keys will be sent to your computer

5. **Manage Profiles**
   - Use the Profile dropdown to switch between profiles
   - Click "New" to create a new profile
   - Click "Rename" or "Delete" to manage profiles

### Command Line Mode

1. **List Available MIDI Ports**
   ```bash
   python main.py --list-ports
   ```

2. **Run with Default Profile**
   ```bash
   python main.py
   ```

3. **Run with Specific Profile**
   ```bash
   python main.py --profile "ProfileName"
   ```

4. **Use Custom Config File**
   ```bash
   python main.py --config "custom_config.json"
   ```

## Configuration

Configuration is stored in `config.json` with the following structure:

```json
{
  "profiles": {
    "default": {
      "midi_map": {
        "60": "a",
        "62": "s",
        "64": "d"
      },
      "velocity_threshold": 0
    }
  },
  "current_profile": "default"
}
```

### MIDI Note Numbers

MIDI notes range from 0-127. Common reference:
- C4 (Middle C) = 60
- C3 = 48
- C5 = 72

### Keyboard Key Formats

- **Single keys**: `a`, `z`, `space`, `enter`, `f1`
- **Key combinations**: `ctrl+c`, `shift+f1`, `ctrl+alt+delete`
- **Supported modifiers**: `ctrl`, `shift`, `alt`

### Special Keys

Supported special keys:
- Arrow keys: `up`, `down`, `left`, `right`
- Function keys: `f1` through `f12`
- Navigation: `home`, `end`, `page_up`, `page_down`
- Editing: `backspace`, `delete`, `insert`, `tab`, `enter`, `esc`

## Troubleshooting

### Keys Not Working in Games

1. **Run as Administrator**
   - Right-click Command Prompt/Python and select "Run as administrator"
   - Many games require administrator privileges for simulated input

2. **Check Game Settings**
   - Some games block simulated input for security
   - Try in a different application first (like Notepad) to verify it works

### MIDI Device Not Detected

1. **Check MIDI Port**
   - Click "Refresh" in the GUI
   - Ensure your MIDI device is connected and powered on
   - Try disconnecting and reconnecting the device

2. **Install MIDI Drivers**
   - Some MIDI devices require specific drivers
   - Check your device manufacturer's website

### Mapping Not Working

1. **Check Mapping is Enabled**
   - Ensure "Enable MIDI to Keyboard Mapping" checkbox is checked

2. **Verify MIDI Connection**
   - Check the status shows "Connected" (green)
   - Play a note and verify it appears in "Last detected notes"

3. **Check Console Output**
   - Look for error messages or warnings
   - Verify keys are being assigned correctly


## Technical Details

- **Keyboard Input**:
  - **Windows**: Uses Windows API `SendInput` function for low-level keyboard simulation
  - **macOS**: Uses `pynput` library (fallback to AppleScript)
  - **Linux**: Uses `xdotool` (fallback to `pynput` via X11)
- **MIDI Input**: Uses `mido` library with `python-rtmidi` backend
- **Key Capture**: Uses `pynput` for capturing keyboard input in the GUI
- **Cross-Platform**: Automatic platform detection and backend selection

## Platform-Specific Notes

### Windows
- Uses Windows API `SendInput` for low-level keyboard simulation
- Works with most games and applications
- May require administrator privileges for some games

### macOS
- Uses `pynput` library (primary method)
- Falls back to AppleScript if `pynput` is not available
- May require accessibility permissions in System Preferences > Security & Privacy

### Linux
- Uses `xdotool` if available (recommended, no root required)
- Falls back to `pynput` if `xdotool` is not installed
- Requires X11 environment (does not work with Wayland without XWayland)
- Some applications may require root privileges

## Limitations

- Some applications may block simulated input for security reasons
- Linux: Requires X11 (Wayland support limited)
- macOS: May require accessibility permissions
- Windows: May require administrator privileges for some games

## License
                                                                                                                                                                                                                                                        
Free to use and modify.

## Contributing

Feel free to submit issues or pull requests if you find bugs or want to add features.

