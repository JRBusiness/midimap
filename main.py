#!/usr/bin/env python3
"""
MIDI Keyboard to Computer Keyboard Mapper
Maps MIDI note events to computer keyboard key presses
Cross-platform support for Windows, macOS, and Linux
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional

try:
    import mido
    from mido import Message
except ImportError:
    print("Error: mido library not found. Please install it with: pip install mido")
    sys.exit(1)

# Import cross-platform keyboard backend
from keyboard_backend import PlatformKeyboard


class MIDIToKeyboardMapper:
    """Maps MIDI note events to keyboard key presses"""
    
    def __init__(self, config_file: str = "config.json", profile_name: Optional[str] = None):
        self.config_path = Path(config_file)
        self.keyboard = PlatformKeyboard()
        self.midi_map: Dict[int, str] = {}
        self.active_notes: Dict[int, bool] = {}
        self.current_port: Optional[mido.ports.BaseInput] = None
        self.velocity_threshold = 0
        self.load_config(profile_name=profile_name)
    
    def load_config(self, profile_name: Optional[str] = None):
        """Load MIDI to keyboard mapping from config file"""
        if not self.config_path.exists():
            print(f"Config file not found: {self.config_path}")
            print("Creating default config file...")
            self.create_default_config()
            return
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Check if it's the new profile-based format
            if "profiles" in config:
                profiles = config.get("profiles", {})
                
                # Use specified profile or current_profile or default
                if profile_name and profile_name in profiles:
                    selected_profile = profile_name
                elif profile_name is None:
                    selected_profile = config.get("current_profile", "default")
                else:
                    print(f"Warning: Profile '{profile_name}' not found, using default")
                    selected_profile = "default"
                
                if selected_profile not in profiles:
                    print(f"Warning: Profile '{selected_profile}' not found, creating default")
                    profiles[selected_profile] = {"midi_map": {}, "velocity_threshold": 0}
                
                profile_data = profiles[selected_profile]
                self.midi_map = profile_data.get("midi_map", {})
                # Convert string keys to integers (MIDI note numbers)
                self.midi_map = {int(k): v for k, v in self.midi_map.items()}
                
                print(f"Loaded profile '{selected_profile}' with {len(self.midi_map)} MIDI note mappings")
                if profile_data.get("velocity_threshold", 0) > 0:
                    self.velocity_threshold = profile_data.get("velocity_threshold")
                else:
                    self.velocity_threshold = 0
            else:
                # Old format - migrate to profiles
                old_midi_map = config.get("midi_map", {})
                old_midi_map = {int(k): v for k, v in old_midi_map.items()}
                self.midi_map = old_midi_map
                
                print(f"Loaded {len(self.midi_map)} MIDI note mappings (legacy format)")
                if config.get("velocity_threshold", 0) > 0:
                    self.velocity_threshold = config.get("velocity_threshold")
                else:
                    self.velocity_threshold = 0
                    
        except json.JSONDecodeError as e:
            print(f"Error parsing config file: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
    
    def create_default_config(self):
        """Create a default configuration file with profile support"""
        # Default mapping: C4 (MIDI note 60) to 'a', D4 (62) to 's', etc.
        default_profile_map = {
            "60": "a",  # C4
            "62": "s",  # D4
            "64": "d",  # E4
            "65": "f",  # F4
            "67": "g",  # G4
            "69": "h",  # A4
            "71": "j",  # B4
            "72": "k"   # C5
        }
        
        default_config = {
            "profiles": {
                "default": {
                    "midi_map": default_profile_map,
                    "velocity_threshold": 0
                }
            },
            "current_profile": "default",
            "description": "MIDI note number (0-127) maps to keyboard key"
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        self.midi_map = {int(k): v for k, v in default_profile_map.items()}
        self.velocity_threshold = 0
        print(f"Created default config file: {self.config_path}")
        print("You can edit it to customize your MIDI to keyboard mappings")
    
    def list_midi_ports(self):
        """List available MIDI input ports"""
        ports = mido.get_input_names()
        if not ports:
            print("No MIDI input ports found!")
            return []
        
        print("\nAvailable MIDI input ports:")
        for i, port in enumerate(ports):
            print(f"  [{i}] {port}")
        return ports
    
    def open_midi_port(self, port_name: Optional[str] = None):
        """Open a MIDI input port"""
        ports = mido.get_input_names()
        
        if not ports:
            print("Error: No MIDI input ports available!")
            return False
        
        if port_name is None:
            # Use first available port
            port_name = ports[0]
            print(f"Using first available port: {port_name}")
        elif port_name not in ports:
            print(f"Error: Port '{port_name}' not found!")
            print("Available ports:")
            for port in ports:
                print(f"  - {port}")
            return False
        
        try:
            self.current_port = mido.open_input(port_name)
            print(f"Successfully opened MIDI port: {port_name}")
            return True
        except Exception as e:
            print(f"Error opening MIDI port: {e}")
            return False
    
    def press_key(self, key: str):
        """Press a keyboard key using Windows API"""
        key_lower = key.lower().strip()
        
        # Handle modifier combinations (e.g., "ctrl+a")
        if '+' in key_lower:
            parts = key_lower.split('+')
            modifiers = []
            char_key = None
            
            valid_modifiers = {'ctrl', 'shift', 'alt'}
            
            for part in parts:
                part = part.strip()
                if part in valid_modifiers:
                    modifiers.append(part)
                else:
                    char_key = part
            
            if char_key:
                # Press combination
                self.keyboard.press_combination(modifiers, char_key)
            else:
                # Just modifiers
                for mod in modifiers:
                    self.keyboard.press_key(mod)
        else:
            # Single key (regular or special)
            self.keyboard.press_key(key_lower)
    
    def release_key(self, key: str):
        """Release a keyboard key using Windows API"""
        key_lower = key.lower().strip()
        
        # Handle modifier combinations
        if '+' in key_lower:
            parts = key_lower.split('+')
            modifiers = []
            char_key = None
            
            valid_modifiers = {'ctrl', 'shift', 'alt'}
            
            for part in parts:
                part = part.strip()
                if part in valid_modifiers:
                    modifiers.append(part)
                else:
                    char_key = part
            
            if char_key:
                # Release the key first, then modifiers
                self.keyboard.release_key(char_key)
                for mod in reversed(modifiers):
                    self.keyboard.release_key(mod)
            else:
                # Just modifiers
                for mod in reversed(modifiers):
                    self.keyboard.release_key(mod)
        else:
            # Single key
            self.keyboard.release_key(key_lower)
    
    def handle_note_on(self, note: int, velocity: int):
        """Handle MIDI note on event"""
        if velocity < self.velocity_threshold:
            return
        
        if note in self.midi_map:
            key = self.midi_map[note]
            if not self.active_notes.get(note, False):
                self.press_key(key)
                self.active_notes[note] = True
                print(f"Note ON:  MIDI {note} -> Key '{key}' (velocity: {velocity})")
    
    def handle_note_off(self, note: int):
        """Handle MIDI note off event"""
        if note in self.midi_map:
            key = self.midi_map[note]
            if self.active_notes.get(note, False):
                self.release_key(key)
                self.active_notes[note] = False
                print(f"Note OFF: MIDI {note} -> Key '{key}'")
    
    def run(self, port_name: Optional[str] = None):
        """Start listening to MIDI input and mapping to keyboard"""
        if not self.open_midi_port(port_name):
            return
        
        if not self.midi_map:
            print("Error: No MIDI mappings configured!")
            print(f"Please edit {self.config_path} to add mappings.")
            return
        
        print("\nMIDI to Keyboard Mapper is running...")
        print("Press Ctrl+C to stop")
        print("-" * 50)
        
        try:
            for message in self.current_port:
                if message.type == 'note_on':
                    if message.velocity > 0:
                        self.handle_note_on(message.note, message.velocity)
                    else:
                        # Some MIDI devices send note_on with velocity 0 as note_off
                        self.handle_note_off(message.note)
                elif message.type == 'note_off':
                    self.handle_note_off(message.note)
        
        except KeyboardInterrupt:
            print("\n\nStopping MIDI mapper...")
        finally:
            if self.current_port:
                self.current_port.close()
                print("Closed MIDI port")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Map MIDI keyboard notes to computer keyboard keys"
    )
    parser.add_argument(
        '-c', '--config',
        default='config.json',
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
    
    args = parser.parse_args()
    
    if args.gui:
        try:
            import gui
            gui.main()
            return
        except ImportError:
            print("Error: GUI module not found. Make sure gui.py is in the same directory.")
            sys.exit(1)
    
    mapper = MIDIToKeyboardMapper(config_file=args.config)
    mapper.load_config(profile_name=args.profile)
    
    if args.list_ports:
        mapper.list_midi_ports()
        return
    
    mapper.run(port_name=args.port)


if __name__ == "__main__":
    main()
