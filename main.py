#!/usr/bin/env python3
"""
MidiMap - MIDI Keyboard to Computer Keyboard Mapper

Maps MIDI note events to computer keyboard key presses.
Cross-platform support for Windows, macOS, and Linux.
"""

import argparse
import sys

from src.mapper import MIDIToKeyboardMapper


def is_bundled() -> bool:
    """Check if running as a bundled executable."""
    return getattr(sys, 'frozen', False)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Map MIDI keyboard notes to computer keyboard keys"
    )
    parser.add_argument(
        '-c', '--config',
        default=None,
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--profile',
        help='Profile name to use (default: current profile or "default")'
    )
    parser.add_argument(
        '-p', '--port',
        help='MIDI input port name (default: first available)'
    )
    parser.add_argument(
        '-l', '--list-ports',
        action='store_true',
        help='List available MIDI input ports and exit'
    )
    parser.add_argument(
        '-g', '--gui',
        action='store_true',
        help='Launch GUI application for interactive key mapping'
    )
    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Run in CLI mode (only for bundled exe)'
    )
    
    args = parser.parse_args()
    
    # Auto-launch GUI when running as bundled exe (unless --no-gui is specified)
    if is_bundled() and not args.no_gui and not args.list_ports:
        args.gui = True
    
    if args.gui:
        try:
            from src.gui import main as gui_main
            gui_main()
            return
        except ImportError as e:
            print(f"Error: GUI module not available: {e}")
            sys.exit(1)
    
    mapper = MIDIToKeyboardMapper(config_file=args.config)
    mapper.load_config(profile_name=args.profile)
    
    if args.list_ports:
        mapper.list_midi_ports()
        return
    
    mapper.run(port_name=args.port)


if __name__ == "__main__":
    main()
