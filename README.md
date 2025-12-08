# MidiMap

A cross-platform desktop application that bridges MIDI input with computer keyboard output. Originally designed for rhythm game integration, MidiMap converts MIDI notes to keystrokes and includes AI-powered audio-to-MIDI transcription.

## Features

### MIDI to Keyboard Mapping
- Map any MIDI note (0-127) to keyboard keys or key combinations
- DirectInput support for game compatibility (Windows)
- Real-time MIDI note detection and visualization
- Multiple mapping profiles with easy switching

### MIDI File Playback
- Load and play MIDI files with automatic keystroke output
- Adjustable playback speed (0.25x - 2x)
- Note range adjustment to fit instrument constraints (e.g., 36-note range)
- Optional humanization with configurable misclick simulation

### Audio to MIDI Conversion
- AI-powered piano converter using ONNX runtime
- Supports MP3, WAV, FLAC, OGG, M4A, and WMA formats
- GPU acceleration via DirectML (Windows) with CPU fallback
- Batch conversion support

### YouTube Integration
- Download YouTube videos as MP3
- One-click download and convert to MIDI workflow
- Automatic video title sanitization

## Installation

### Prerequisites
- Python 3.8 or higher
- FFmpeg (required for audio conversion)

### Quick Start

1. Clone the repository:
```bash
git clone https://github.com/yourusername/midimap.git
cd midimap
```

2. Create a virtual environment (recommended):
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Download the AI model:
   - Place `model.onnx` in the `models/` directory
   - The model file is required for audio-to-MIDI conversion

5. Run the application:
```bash
python main.py --gui
```

Or on Windows, double-click `run_gui.bat`.

### FFmpeg Installation

FFmpeg is required for audio format conversion.

**Windows:**
```bash
winget install ffmpeg
```
Or download from [ffmpeg.org](https://ffmpeg.org/download.html) and place `ffmpeg.exe` in the project directory.

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg  # Debian/Ubuntu
sudo dnf install ffmpeg  # Fedora
```

## Usage

### GUI Mode

Launch the GUI with:
```bash
python main.py --gui
```

#### Mapping MIDI Notes

1. Connect your MIDI device and select it from the dropdown
2. Click **Connect** to start listening
3. Play a note on your MIDI device or enter the note number manually
4. Click **Capture Key/Combo** and press the desired keyboard key
5. Click **Assign** to save the mapping
6. Enable **MIDI to Keyboard Mapping** checkbox to activate

#### Playing MIDI Files

1. Click **Browse...** in the MIDI File Player section
2. Select a MIDI file (.mid)
3. Adjust playback speed if needed
4. Click **Play** to start automatic keystroke output

#### Converting Audio to MIDI

1. Click **Browse Audio...** and select an audio file
2. Choose an output folder for MIDI files
3. Click **Convert & Load** to convert and immediately load for playback

#### YouTube to MIDI

1. Paste a YouTube URL in the text field
2. Click **Download & Convert** for a one-click workflow
3. The MP3 will be saved to `downloads/` and converted to MIDI

### Command Line Mode

```bash
# List available MIDI ports
python main.py --list-ports

# Run with default profile
python main.py

# Run with a specific profile
python main.py --profile "MyProfile"

# Use custom config file
python main.py --config "custom_config.json"

# Launch GUI
python main.py --gui
```

## Configuration

Configuration is stored in `config.json`:

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

### Key Mapping Format

| Type | Examples |
|------|----------|
| Single key | `a`, `z`, `space`, `enter`, `f1` |
| With modifier | `ctrl+c`, `shift+f1`, `alt+tab` |
| Multiple modifiers | `ctrl+shift+a`, `ctrl+alt+delete` |

### MIDI Note Reference

| Note | MIDI Number |
|------|-------------|
| C3 | 48 |
| C4 (Middle C) | 60 |
| C5 | 72 |

## Project Structure

```
midimap/
├── main.py                  # Entry point
├── src/                     # Source code
│   ├── __init__.py
│   ├── mapper.py            # Core MIDI to keyboard mapper
│   ├── keyboard.py          # Cross-platform keyboard backend
│   ├── gui.py               # Tkinter GUI application
│   └── converters/          # Conversion modules
│       ├── __init__.py
│       ├── audio.py         # Audio to MIDI conversion
│       ├── inference.py     # AI transcription engine
│       └── youtube.py       # YouTube downloader
├── utils/                   # Utility modules
│   ├── __init__.py
│   ├── audio.py             # Audio processing utilities
│   ├── config.py            # Configuration constants
│   └── vad.py               # Voice activity detection
├── models/                  # AI models
│   └── model.onnx           # Piano converter model
├── config.json              # User configuration
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Package configuration
├── run_gui.bat              # Windows launcher
├── run_gui.sh               # Linux/Mac launcher
├── LICENSE                  # MIT license
├── downloads/               # YouTube downloads (auto-created)
└── midi_output/             # Converted MIDI files (auto-created)
```

## Platform Support

| Platform | Keyboard Backend | Status |
|----------|-----------------|--------|
| Windows | DirectInput (SendInput API) | Full support |
| macOS | pynput / AppleScript | Supported |
| Linux | xdotool / pynput | Supported |

### Platform Notes

**Windows:**
- Uses DirectInput scan codes for game compatibility
- May require administrator privileges for some games
- GPU acceleration available via DirectML

**macOS:**
- Requires accessibility permissions in System Preferences
- Some applications may block simulated input

**Linux:**
- Install xdotool for best compatibility: `sudo apt install xdotool`
- Requires X11 (limited Wayland support via XWayland)

## Troubleshooting

### Keys Not Working in Games

1. Run as administrator (Windows)
2. Verify keys work in a text editor first
3. Some games require specific DirectInput settings

### MIDI Device Not Detected

1. Click **Refresh** in the GUI
2. Ensure device is connected and powered on
3. Install manufacturer drivers if needed

### Audio Conversion Fails

1. Verify FFmpeg is installed: `ffmpeg -version`
2. Check that the AI model exists in `models/model.onnx`
3. Try converting to WAV format first for problematic files

### YouTube Download Fails

1. Update yt-dlp: `pip install --upgrade yt-dlp`
2. Check video is not private or region-locked
3. Verify FFmpeg is available for audio extraction

## Dependencies

| Package | Purpose |
|---------|---------|
| mido | MIDI input/output handling |
| pynput | Keyboard input capture |
| librosa | Audio loading and processing |
| onnxruntime | AI model inference |
| yt-dlp | YouTube video downloading |
| numpy | Numerical operations |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request.