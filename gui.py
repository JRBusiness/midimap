#!/usr/bin/env python3
"""
GUI Application for MIDI to Keyboard Mapping
Allows interactive assignment of keyboard keys to MIDI notes
"""

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, scrolledtext
from typing import Dict, Optional, Set

try:
    import mido
except ImportError:
    messagebox.showerror("Error", "mido library not found. Please install it with: pip install mido")
    exit(1)

try:
    from pynput.keyboard import Key, Listener, Controller
except ImportError:
    messagebox.showerror("Error", "pynput library not found. Please install it with: pip install pynput")
    exit(1)

from main import MIDIToKeyboardMapper


class MIDIMapperGUI:
    """GUI application for MIDI to keyboard mapping"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MIDI to Keyboard Mapper")
        self.root.geometry("950x850")
        self.root.minsize(800, 700)
        
        self.config_path = Path("config.json")
        # Create mapper without loading config (we'll load profiles separately)
        # Import PlatformKeyboard from keyboard_backend
        from keyboard_backend import PlatformKeyboard
        self.mapper = MIDIToKeyboardMapper.__new__(MIDIToKeyboardMapper)
        self.mapper.config_path = self.config_path
        self.mapper.keyboard = PlatformKeyboard()
        self.mapper.midi_map = {}
        self.mapper.active_notes = {}
        self.mapper.current_port = None
        self.mapper.velocity_threshold = 0
        self.midi_map: Dict[int, str] = {}
        self.active_notes: Set[int] = set()
        
        self.midi_port: Optional[mido.ports.BaseInput] = None
        self.midi_listener_thread: Optional[threading.Thread] = None
        self.running = False
        self.mapping_enabled = False
        
        self.keyboard_listener: Optional[Listener] = None
        self.capturing_key = False
        self.selected_midi_note: Optional[int] = None
        self.recent_midi_notes: list = []
        self.pressed_modifiers: Set[str] = set()
        self.waiting_for_key = False
        
        self.current_profile: str = "default"
        self.profiles: Dict[str, Dict[int, str]] = {}
        
        self.setup_ui()
        self.load_all_profiles()
        # Load the current profile without saving (initial load)
        self._load_profile_without_save(self.current_profile)
        
    def setup_ui(self):
        """Create the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Profile Selection
        profile_frame = ttk.LabelFrame(main_frame, text="Profile", padding="5")
        profile_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(profile_frame, text="Profile:").grid(row=0, column=0, padx=5)
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(profile_frame, textvariable=self.profile_var, width=30, state="readonly")
        self.profile_combo.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_changed)
        profile_frame.columnconfigure(1, weight=1)
        
        ttk.Button(profile_frame, text="New", command=self.create_new_profile).grid(row=0, column=2, padx=2)
        ttk.Button(profile_frame, text="Rename", command=self.rename_profile).grid(row=0, column=3, padx=2)
        ttk.Button(profile_frame, text="Delete", command=self.delete_profile).grid(row=0, column=4, padx=2)
        
        # MIDI Port Selection
        port_frame = ttk.LabelFrame(main_frame, text="MIDI Input", padding="5")
        port_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(port_frame, text="Port:").grid(row=0, column=0, padx=5)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, width=40, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        port_frame.columnconfigure(1, weight=1)
        
        ttk.Button(port_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=5)
        ttk.Button(port_frame, text="Connect", command=self.connect_midi).grid(row=0, column=3, padx=5)
        ttk.Button(port_frame, text="Disconnect", command=self.disconnect_midi).grid(row=0, column=4, padx=5)
        
        self.status_label = ttk.Label(port_frame, text="Not connected", foreground="red")
        self.status_label.grid(row=1, column=0, columnspan=5, pady=5)
        
        # MIDI Note Detection
        detection_frame = ttk.LabelFrame(main_frame, text="MIDI Note Detection", padding="5")
        detection_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(detection_frame, text="Last detected notes:").grid(row=0, column=0, padx=5)
        self.last_notes_text = scrolledtext.ScrolledText(detection_frame, height=3, width=60, state="disabled")
        self.last_notes_text.grid(row=0, column=1, columnspan=2, padx=5, sticky=(tk.W, tk.E))
        detection_frame.columnconfigure(1, weight=1)
        
        # Key Assignment Section
        assignment_frame = ttk.LabelFrame(main_frame, text="Assign Keyboard Key", padding="5")
        assignment_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(assignment_frame, text="MIDI Note:").grid(row=0, column=0, padx=5)
        self.midi_note_var = tk.StringVar()
        note_frame = ttk.Frame(assignment_frame)
        note_frame.grid(row=0, column=1, padx=5, sticky=tk.W)
        
        self.midi_note_entry = ttk.Entry(note_frame, textvariable=self.midi_note_var, width=10)
        self.midi_note_entry.grid(row=0, column=0, padx=2)
        ttk.Button(note_frame, text="Use Last", command=self.use_last_note).grid(row=0, column=1, padx=2)
        ttk.Button(note_frame, text="Detect", command=self.start_note_detection).grid(row=0, column=2, padx=2)
        
        ttk.Label(assignment_frame, text="Keyboard Key:").grid(row=1, column=0, padx=5, pady=5)
        self.key_var = tk.StringVar()
        key_frame = ttk.Frame(assignment_frame)
        key_frame.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        self.key_entry = ttk.Entry(key_frame, textvariable=self.key_var, width=30)
        self.key_entry.grid(row=0, column=0, padx=2)
        ttk.Button(key_frame, text="Capture Key/Combo", command=self.start_key_capture).grid(row=0, column=1, padx=2)
        self.capture_status_label = ttk.Label(key_frame, text="", foreground="blue")
        self.capture_status_label.grid(row=0, column=2, padx=5)
        
        ttk.Label(assignment_frame, text="Examples: 'a', 'ctrl+c', 'shift+f1', 'ctrl+alt+delete', 'ctrl+shift+a'", 
                 font=("TkDefaultFont", 8), foreground="gray").grid(row=3, column=0, columnspan=2, pady=2)
        
        ttk.Button(assignment_frame, text="Assign", command=self.assign_key).grid(row=2, column=0, columnspan=2, pady=5)
        
        # Mappings Display
        mappings_frame = ttk.LabelFrame(main_frame, text="Current Mappings", padding="5")
        mappings_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(4, weight=1)
        mappings_frame.columnconfigure(0, weight=1)
        mappings_frame.rowconfigure(0, weight=1)
        
        # Treeview for mappings
        columns = ("MIDI Note", "Note Name", "Keyboard Key")
        self.mappings_tree = ttk.Treeview(mappings_frame, columns=columns, show="headings", height=12)
        self.mappings_tree.heading("MIDI Note", text="MIDI Note")
        self.mappings_tree.heading("Note Name", text="Note Name")
        self.mappings_tree.heading("Keyboard Key", text="Keyboard Key")
        self.mappings_tree.column("MIDI Note", width=100)
        self.mappings_tree.column("Note Name", width=100)
        self.mappings_tree.column("Keyboard Key", width=200)
        
        scrollbar = ttk.Scrollbar(mappings_frame, orient=tk.VERTICAL, command=self.mappings_tree.yview)
        self.mappings_tree.configure(yscrollcommand=scrollbar.set)
        
        self.mappings_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Bind double-click to edit
        self.mappings_tree.bind("<Double-1>", self.on_mapping_double_click)
        
        # Buttons for mappings
        button_frame = ttk.Frame(mappings_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Button(button_frame, text="Remove Selected", command=self.remove_mapping).grid(row=0, column=0, padx=2)
        ttk.Button(button_frame, text="Clear All", command=self.clear_all_mappings).grid(row=0, column=1, padx=2)
        ttk.Button(button_frame, text="Save Config", command=self.save_config).grid(row=0, column=2, padx=2)
        ttk.Button(button_frame, text="Load Config", command=self.load_mappings).grid(row=0, column=3, padx=2)
        
        # Control Section
        control_frame = ttk.LabelFrame(main_frame, text="Control", padding="5")
        control_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.enable_var = tk.BooleanVar(value=False)
        enable_check = ttk.Checkbutton(control_frame, text="Enable MIDI to Keyboard Mapping", 
                                       variable=self.enable_var, command=self.toggle_mapping)
        enable_check.grid(row=0, column=0, padx=5)
        
        # Initialize ports
        self.refresh_ports()
    
    def load_all_profiles(self):
        """Load all profiles from config file"""
        if not self.config_path.exists():
            self.profiles = {"default": {}}
            self.save_all_profiles()
            return
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Check if it's the new profile-based format
            if "profiles" in config:
                profiles_data = config.get("profiles", {})
                self.profiles = {}
                for profile_name, profile_data in profiles_data.items():
                    midi_map = profile_data.get("midi_map", {})
                    # Convert string keys to integers
                    self.profiles[profile_name] = {int(k): v for k, v in midi_map.items()}
                self.current_profile = config.get("current_profile", "default")
            else:
                # Old format - migrate to profiles
                old_midi_map = config.get("midi_map", {})
                old_midi_map = {int(k): v for k, v in old_midi_map.items()}
                self.profiles = {"default": old_midi_map}
                self.current_profile = "default"
                self.save_all_profiles()
            
            # Ensure default profile exists
            if "default" not in self.profiles:
                self.profiles["default"] = {}
            
            # Update profile combo
            self.profile_combo['values'] = list(self.profiles.keys())
            if self.current_profile in self.profiles:
                self.profile_var.set(self.current_profile)
            else:
                self.profile_var.set("default")
                self.current_profile = "default"
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load profiles: {e}")
            self.profiles = {"default": {}}
            self.current_profile = "default"
            self.profile_combo['values'] = ["default"]
            self.profile_var.set("default")
    
    def save_all_profiles(self):
        """Save all profiles to config file"""
        try:
            profiles_data = {}
            for profile_name, midi_map in self.profiles.items():
                profiles_data[profile_name] = {
                    "midi_map": {str(k): v for k, v in midi_map.items()},
                    "velocity_threshold": getattr(self.mapper, 'velocity_threshold', 0)
                }
            
            config = {
                "profiles": profiles_data,
                "current_profile": self.current_profile,
                "description": "MIDI note number (0-127) maps to keyboard key"
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save profiles: {e}")
            return False
    
    def _load_profile_without_save(self, profile_name: str):
        """Load a profile without saving (for initial load)"""
        if profile_name not in self.profiles:
            if "default" in self.profiles:
                profile_name = "default"
            else:
                profile_name = list(self.profiles.keys())[0] if self.profiles else "default"
                if profile_name not in self.profiles:
                    self.profiles[profile_name] = {}
        
        self.current_profile = profile_name
        self.midi_map = self.profiles[profile_name].copy()
        self.mapper.midi_map = self.midi_map.copy()
        
        # Update UI
        self.profile_var.set(profile_name)
        self.update_mappings_display()
    
    def switch_profile(self, profile_name: str):
        """Switch to a different profile"""
        if profile_name not in self.profiles:
            messagebox.showwarning("Warning", f"Profile '{profile_name}' not found")
            return
        
        # Save current profile's mappings before switching
        self.profiles[self.current_profile] = self.midi_map.copy()
        
        # Load new profile
        self.current_profile = profile_name
        self.midi_map = self.profiles[profile_name].copy()
        self.mapper.midi_map = self.midi_map.copy()
        
        # Update UI
        self.profile_var.set(profile_name)
        self.update_mappings_display()
        
        # Save the switch (only when user actually switches)
        self.save_all_profiles()
    
    def on_profile_changed(self, event=None):
        """Handle profile selection change"""
        new_profile = self.profile_var.get()
        if new_profile != self.current_profile:
            self.switch_profile(new_profile)
    
    def create_new_profile(self):
        """Create a new profile"""
        dialog = tk.Toplevel(self.root)
        dialog.title("New Profile")
        dialog.geometry("300x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Profile name:").pack(pady=10)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        name_entry.pack(pady=5)
        name_entry.focus()
        
        def create():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Profile name cannot be empty")
                return
            
            if name in self.profiles:
                messagebox.showwarning("Warning", f"Profile '{name}' already exists")
                return
            
            # Save current profile
            self.profiles[self.current_profile] = self.midi_map.copy()
            
            # Create new profile
            self.profiles[name] = {}
            self.profile_combo['values'] = list(self.profiles.keys())
            self.save_all_profiles()
            self.switch_profile(name)
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Create", command=create).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=5)
        
        name_entry.bind('<Return>', lambda e: create())
    
    def rename_profile(self):
        """Rename the current profile"""
        if len(self.profiles) == 1:
            messagebox.showwarning("Warning", "Cannot rename - must have at least one profile")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename Profile")
        dialog.geometry("300x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="New profile name:").pack(pady=10)
        name_var = tk.StringVar(value=self.current_profile)
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        name_entry.pack(pady=5)
        name_entry.select_range(0, tk.END)
        name_entry.focus()
        
        def rename():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("Warning", "Profile name cannot be empty")
                return
            
            if new_name == self.current_profile:
                dialog.destroy()
                return
            
            if new_name in self.profiles:
                messagebox.showwarning("Warning", f"Profile '{new_name}' already exists")
                return
            
            # Save current mappings
            mappings = self.midi_map.copy()
            
            # Remove old profile
            del self.profiles[self.current_profile]
            
            # Create new profile with mappings
            self.profiles[new_name] = mappings
            self.profile_combo['values'] = list(self.profiles.keys())
            self.current_profile = new_name
            self.profile_var.set(new_name)
            self.save_all_profiles()
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Rename", command=rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=5)
        
        name_entry.bind('<Return>', lambda e: rename())
    
    def delete_profile(self):
        """Delete the current profile"""
        if len(self.profiles) == 1:
            messagebox.showwarning("Warning", "Cannot delete - must have at least one profile")
            return
        
        if not messagebox.askyesno("Confirm", f"Delete profile '{self.current_profile}'?\nThis cannot be undone."):
            return
        
        # Save current profile before deletion
        self.profiles[self.current_profile] = self.midi_map.copy()
        
        # Delete profile
        del self.profiles[self.current_profile]
        
        # Switch to default or first available
        if "default" in self.profiles:
            new_profile = "default"
        else:
            new_profile = list(self.profiles.keys())[0]
        
        self.profile_combo['values'] = list(self.profiles.keys())
        self.save_all_profiles()
        self.switch_profile(new_profile)
        
    def refresh_ports(self):
        """Refresh the list of available MIDI ports"""
        ports = mido.get_input_names()
        self.port_combo['values'] = ports
        if ports:
            self.port_var.set(ports[0])
    
    def connect_midi(self):
        """Connect to the selected MIDI port"""
        port_name = self.port_var.get()
        if not port_name:
            messagebox.showwarning("Warning", "Please select a MIDI port")
            return
        
        if self.midi_port:
            self.disconnect_midi()
        
        try:
            self.midi_port = mido.open_input(port_name)
            self.status_label.config(text=f"Connected: {port_name}", foreground="green")
            self.running = True
            self.start_midi_listener()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to MIDI port: {e}")
            self.status_label.config(text="Connection failed", foreground="red")
    
    def disconnect_midi(self):
        """Disconnect from MIDI port"""
        self.running = False
        if self.midi_port:
            self.midi_port.close()
            self.midi_port = None
        self.status_label.config(text="Not connected", foreground="red")
    
    def start_midi_listener(self):
        """Start listening to MIDI input in a separate thread"""
        if self.midi_listener_thread and self.midi_listener_thread.is_alive():
            return
        
        self.midi_listener_thread = threading.Thread(target=self.midi_listener_loop, daemon=True)
        self.midi_listener_thread.start()
    
    def midi_listener_loop(self):
        """Listen to MIDI messages in a loop"""
        if not self.midi_port:
            return
        
        try:
            for message in self.midi_port:
                if not self.running:
                    break
                
                if message.type == 'note_on' and message.velocity > 0:
                    self.root.after(0, self.on_midi_note, message.note, message.velocity)
                elif message.type == 'note_off' or (message.type == 'note_on' and message.velocity == 0):
                    self.root.after(0, self.on_midi_note_off, message.note)
        except Exception as e:
            if self.running:
                self.root.after(0, lambda: messagebox.showerror("Error", f"MIDI listener error: {e}"))
    
    def on_midi_note(self, note: int, velocity: int):
        """Handle incoming MIDI note on event"""
        note_name = self.get_note_name(note)
        
        # Add to recent notes
        self.recent_midi_notes.insert(0, (note, note_name, velocity))
        if len(self.recent_midi_notes) > 10:
            self.recent_midi_notes.pop()
        
        # Update UI
        self.last_notes_text.config(state="normal")
        self.last_notes_text.delete(1.0, tk.END)
        for n, name, vel in self.recent_midi_notes[:5]:
            self.last_notes_text.insert(tk.END, f"Note {n} ({name}) - Velocity: {vel}\n")
        self.last_notes_text.config(state="disabled")
        
        # If detecting, update selected note
        if self.selected_midi_note is None:
            self.selected_midi_note = note
            self.midi_note_var.set(str(note))
        
        # If mapping is enabled, trigger keyboard key
        if self.mapping_enabled and note in self.midi_map:
            key = self.midi_map[note]
            if note not in self.active_notes:
                self.active_notes.add(note)
                try:
                    self.mapper.press_key(key)
                    print(f"Sent key press: MIDI {note} -> '{key}'")
                except Exception as e:
                    print(f"Error sending key '{key}' for MIDI note {note}: {e}")
    
    def on_midi_note_off(self, note: int):
        """Handle incoming MIDI note off event"""
        if self.mapping_enabled and note in self.midi_map:
            if note in self.active_notes:
                self.active_notes.remove(note)
                try:
                    self.mapper.release_key(self.midi_map[note])
                    print(f"Sent key release: MIDI {note} -> '{self.midi_map[note]}'")
                except Exception as e:
                    print(f"Error releasing key '{self.midi_map[note]}' for MIDI note {note}: {e}")
    
    def get_note_name(self, note: int) -> str:
        """Get the musical note name from MIDI note number"""
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (note // 12) - 1
        note_name = note_names[note % 12]
        return f"{note_name}{octave}"
    
    def use_last_note(self):
        """Use the last detected MIDI note"""
        if self.recent_midi_notes:
            note, name, _ = self.recent_midi_notes[0]
            self.midi_note_var.set(str(note))
            self.selected_midi_note = note
    
    def start_note_detection(self):
        """Start detecting the next MIDI note"""
        self.selected_midi_note = None
        self.midi_note_var.set("Waiting for MIDI note...")
    
    def start_key_capture(self):
        """Start capturing the next keyboard key press or combination"""
        if self.capturing_key:
            self.stop_key_capture()
            return
        
        self.capturing_key = True
        self.pressed_modifiers.clear()
        self.waiting_for_key = False
        self.capture_status_label.config(text="Press key/combo (hold modifiers)...")
        self.key_entry.config(state="disabled")
        
        # Start keyboard listener with both press and release handlers
        self.keyboard_listener = Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )
        self.keyboard_listener.start()
    
    def stop_key_capture(self):
        """Stop capturing keyboard input"""
        self.capturing_key = False
        self.pressed_modifiers.clear()
        self.waiting_for_key = False
        self.capture_status_label.config(text="")
        self.key_entry.config(state="normal")
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
    
    def on_key_press(self, key):
        """Handle keyboard key press during capture"""
        if not self.capturing_key:
            return False
        
        # Check if it's a modifier key
        modifier = self.get_modifier(key)
        if modifier:
            if modifier not in self.pressed_modifiers:
                self.pressed_modifiers.add(modifier)
                modifiers_str = "+".join(sorted(self.pressed_modifiers))
                self.root.after(0, lambda: self.capture_status_label.config(
                    text=f"Hold: {modifiers_str}... (press another key)"
                ))
            return True  # Continue listening
        
        # It's a regular key (or special key), combine with modifiers
        key_str = self.format_key(key, include_modifiers=False)
        if key_str:
            # Combine modifiers with the key
            if self.pressed_modifiers:
                modifiers_str = "+".join(sorted(self.pressed_modifiers))
                final_key = f"{modifiers_str}+{key_str}"
            else:
                final_key = key_str
            
            self.root.after(0, lambda k=final_key: self.set_captured_key(k))
            self.stop_key_capture()
            return False  # Stop listening
        
        return True
    
    def on_key_release(self, key):
        """Handle keyboard key release during capture"""
        if not self.capturing_key:
            return False
        
        modifier = self.get_modifier(key)
        if modifier and modifier in self.pressed_modifiers:
            # Don't remove modifiers on release - wait for the actual key
            pass
        
        return True
    
    def get_modifier(self, key) -> Optional[str]:
        """Get modifier name if key is a modifier"""
        if isinstance(key, Key):
            modifier_map = {
                Key.ctrl_l: 'ctrl',
                Key.ctrl_r: 'ctrl',
                Key.ctrl: 'ctrl',
                Key.shift_l: 'shift',
                Key.shift_r: 'shift',
                Key.shift: 'shift',
                Key.alt_l: 'alt',
                Key.alt_r: 'alt',
                Key.alt: 'alt',
                Key.cmd: 'cmd',  # Mac command key
                Key.cmd_l: 'cmd',
                Key.cmd_r: 'cmd',
            }
            return modifier_map.get(key)
        return None
    
    def format_key(self, key, include_modifiers: bool = True) -> Optional[str]:
        """Format a pynput key to string representation"""
        if isinstance(key, Key):
            # Map special keys (excluding modifiers which are handled separately)
            special_map = {
                Key.space: 'space',
                Key.enter: 'enter',
                Key.tab: 'tab',
                Key.esc: 'esc',
                Key.backspace: 'backspace',
                Key.up: 'up',
                Key.down: 'down',
                Key.left: 'left',
                Key.right: 'right',
                Key.f1: 'f1', Key.f2: 'f2', Key.f3: 'f3', Key.f4: 'f4',
                Key.f5: 'f5', Key.f6: 'f6', Key.f7: 'f7', Key.f8: 'f8',
                Key.f9: 'f9', Key.f10: 'f10', Key.f11: 'f11', Key.f12: 'f12',
                Key.delete: 'delete',
                Key.insert: 'insert',
                Key.home: 'home',
                Key.end: 'end',
                Key.page_up: 'page_up',
                Key.page_down: 'page_down',
            }
            return special_map.get(key)
        else:
            # Regular character
            try:
                char = key.char
                if char:
                    return char.lower()
            except:
                pass
        return None
    
    def set_captured_key(self, key_str: str):
        """Set the captured key in the entry field"""
        self.key_var.set(key_str)
    
    def validate_key_combination(self, key_str: str) -> bool:
        """Validate that the key combination format is correct"""
        if not key_str:
            return False
        
        # Valid modifiers
        valid_modifiers = {'ctrl', 'shift', 'alt'}
        
        # Split by '+'
        parts = key_str.split('+')
        
        # Check that all parts except the last are valid modifiers
        if len(parts) > 1:
            modifiers = parts[:-1]
            for mod in modifiers:
                if mod not in valid_modifiers:
                    return False
        
        # Last part should be a valid key (single character or special key)
        last_part = parts[-1]
        
        # Check if it's a single character
        if len(last_part) == 1 and last_part.isalnum():
            return True
        
        # Check if it's a valid special key
        valid_special = {
            'space', 'enter', 'tab', 'esc', 'backspace', 'delete', 'insert',
            'up', 'down', 'left', 'right',
            'home', 'end', 'page_up', 'page_down',
            'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12'
        }
        
        if last_part in valid_special:
            return True
        
        return False
    
    def assign_key(self):
        """Assign the keyboard key to the selected MIDI note"""
        try:
            midi_note = int(self.midi_note_var.get())
        except ValueError:
            messagebox.showwarning("Warning", "Please enter a valid MIDI note number (0-127)")
            return
        
        if midi_note < 0 or midi_note > 127:
            messagebox.showwarning("Warning", "MIDI note must be between 0 and 127")
            return
        
        key_str = self.key_var.get().strip()
        if not key_str:
            messagebox.showwarning("Warning", "Please enter or capture a keyboard key")
            return
        
        # Normalize the key string (lowercase, handle spaces)
        key_str = key_str.lower().replace(" ", "")
        
        # Validate the key combination format
        if not self.validate_key_combination(key_str):
            messagebox.showwarning("Warning", 
                "Invalid key combination format.\n"
                "Examples: 'a', 'ctrl+c', 'shift+f1', 'ctrl+alt+delete'\n"
                "Modifiers: ctrl, shift, alt\n"
                "Can combine: ctrl+shift+a, alt+f4, etc.")
            return
        
        # Add to mapping
        self.midi_map[midi_note] = key_str
        self.mapper.midi_map = self.midi_map.copy()
        # Update profile storage
        self.profiles[self.current_profile] = self.midi_map.copy()
        
        # Update display
        self.update_mappings_display()
        
        # Clear fields
        self.midi_note_var.set("")
        self.key_var.set("")
    
    def on_mapping_double_click(self, event):
        """Handle double-click on mapping to edit"""
        selection = self.mappings_tree.selection()
        if not selection:
            return
        
        item = self.mappings_tree.item(selection[0])
        midi_note = int(item['values'][0])
        key = item['values'][2]
        
        self.midi_note_var.set(str(midi_note))
        self.key_var.set(key)
    
    def remove_mapping(self):
        """Remove the selected mapping"""
        selection = self.mappings_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a mapping to remove")
            return
        
        item = self.mappings_tree.item(selection[0])
        midi_note = int(item['values'][0])
        
        if midi_note in self.midi_map:
            del self.midi_map[midi_note]
            self.mapper.midi_map = self.midi_map.copy()
            # Update profile storage
            self.profiles[self.current_profile] = self.midi_map.copy()
            self.update_mappings_display()
    
    def clear_all_mappings(self):
        """Clear all mappings in current profile"""
        if messagebox.askyesno("Confirm", f"Clear all mappings in profile '{self.current_profile}'?"):
            self.midi_map.clear()
            self.mapper.midi_map.clear()
            # Update profile storage
            self.profiles[self.current_profile] = {}
            self.update_mappings_display()
    
    def update_mappings_display(self):
        """Update the mappings tree display"""
        # Clear existing items
        for item in self.mappings_tree.get_children():
            self.mappings_tree.delete(item)
        
        # Add current mappings
        for midi_note in sorted(self.midi_map.keys()):
            note_name = self.get_note_name(midi_note)
            key = self.midi_map[midi_note]
            self.mappings_tree.insert("", tk.END, values=(midi_note, note_name, key))
    
    def save_config(self):
        """Save current profile mappings to config file"""
        # Update current profile with current mappings
        self.profiles[self.current_profile] = self.midi_map.copy()
        if self.save_all_profiles():
            messagebox.showinfo("Success", f"Profile '{self.current_profile}' saved to {self.config_path}")
    
    def load_mappings(self):
        """Load mappings from current profile"""
        # This is now handled by switch_profile and load_all_profiles
        pass
    
    def toggle_mapping(self):
        """Enable or disable MIDI to keyboard mapping"""
        self.mapping_enabled = self.enable_var.get()
        if not self.mapping_enabled:
            # Release all active notes
            for note in list(self.active_notes):
                if note in self.midi_map:
                    self.mapper.release_key(self.midi_map[note])
            self.active_notes.clear()
    
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.disconnect_midi()
        # Save current profile before closing
        self.profiles[self.current_profile] = self.midi_map.copy()
        self.save_all_profiles()
        self.root.destroy()


def main():
    """Main entry point"""
    root = tk.Tk()
    app = MIDIMapperGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
