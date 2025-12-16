#!/usr/bin/env python3
"""
GUI Application for MIDI to Keyboard Mapping
Allows interactive assignment of keyboard keys to MIDI notes
"""

import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, scrolledtext, filedialog
from typing import Dict, Optional, Set, List, Tuple

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

from src.mapper import MIDIToKeyboardMapper


class MIDIFilePlayer:
    """Plays MIDI files and triggers keyboard keys based on mappings"""
    
    # Default 36-note range (3 octaves starting from C3 = MIDI 48)
    DEFAULT_BASE_NOTE = 48
    DEFAULT_NOTE_RANGE = 36
    
    def __init__(self, mapper: MIDIToKeyboardMapper, midi_map: Dict[int, str]):
        self.mapper = mapper  # Use the mapper for key press/release (handles combinations)
        self.midi_map = midi_map
        self.playing = False
        self.paused = False
        self.speed = 1.0
        self.current_file: Optional[str] = None
        self.original_events: List[Tuple[float, str, int]] = []  # Original events
        self.events: List[Tuple[float, str, int]] = []  # Adjusted events (time, type, note)
        self.play_thread: Optional[threading.Thread] = None
        self.active_notes: Set[int] = set()
        self.on_progress_callback = None
        self.on_note_callback = None
        self.total_duration = 0.0
        self.current_position = 0.0
        
        # Note adjustment settings
        self.adjust_notes = True  # Enable note adjustment by default
        self.base_note = self.DEFAULT_BASE_NOTE  # Starting note of the 36-note range
        self.note_range = self.DEFAULT_NOTE_RANGE  # Number of notes available
        
        # Statistics
        self.original_min_note = 0
        self.original_max_note = 0
        self.adjusted_min_note = 0
        self.adjusted_max_note = 0
        
        # Misclick (humanize) settings
        self.misclick_enabled = False
        self.misclick_rate = 2.0  # Percentage chance of misclick
        self.misclick_range = 2  # How many notes away a misclick can be
    
    def load_file(self, filepath: str) -> bool:
        """Load a MIDI file and extract note events"""
        try:
            mid = mido.MidiFile(filepath)
            self.current_file = filepath
            self.original_events = []
            
            # Convert MIDI to absolute time events
            current_time = 0.0
            for msg in mid:
                current_time += msg.time
                if msg.type == 'note_on' and msg.velocity > 0:
                    self.original_events.append((current_time, 'on', msg.note))
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    self.original_events.append((current_time, 'off', msg.note))
            
            # Sort by time
            self.original_events.sort(key=lambda x: x[0])
            self.total_duration = current_time if self.original_events else 0.0
            
            # Calculate original note range
            notes = [e[2] for e in self.original_events if e[1] == 'on']
            if notes:
                self.original_min_note = min(notes)
                self.original_max_note = max(notes)
            else:
                self.original_min_note = 0
                self.original_max_note = 0
            
            # Apply note adjustment
            self._apply_note_adjustment()
            
            return True
        except Exception as e:
            print(f"Error loading MIDI file: {e}")
            return False
    
    def _apply_note_adjustment(self):
        """Apply note adjustment to fit within the available range"""
        if not self.original_events:
            self.events = []
            return
        
        if not self.adjust_notes:
            # No adjustment - use original events
            self.events = self.original_events.copy()
            self.adjusted_min_note = self.original_min_note
            self.adjusted_max_note = self.original_max_note
            return
        
        # Get all unique notes
        unique_notes = set(e[2] for e in self.original_events)
        if not unique_notes:
            self.events = []
            return
        
        min_note = min(unique_notes)
        max_note = max(unique_notes)
        original_range = max_note - min_note + 1
        
        # Calculate the optimal transpose amount
        # Try to center the song's range within our available range
        if original_range <= self.note_range:
            # Song fits within range - just transpose to fit
            # Center the song in our range
            song_center = (min_note + max_note) // 2
            target_center = self.base_note + (self.note_range // 2)
            transpose = target_center - song_center
            
            # Make sure transposed notes fit within range
            transposed_min = min_note + transpose
            transposed_max = max_note + transpose
            
            if transposed_min < self.base_note:
                transpose += self.base_note - transposed_min
            elif transposed_max >= self.base_note + self.note_range:
                transpose -= transposed_max - (self.base_note + self.note_range - 1)
        else:
            # Song is wider than our range - need octave folding
            # Find the transpose that minimizes the number of notes needing adjustment
            transpose = self.base_note - min_note
        
        # Create note mapping with octave folding
        note_mapping = {}
        for note in unique_notes:
            adjusted = note + transpose
            
            # Octave fold if outside range
            while adjusted < self.base_note:
                adjusted += 12  # Move up one octave
            while adjusted >= self.base_note + self.note_range:
                adjusted -= 12  # Move down one octave
            
            # Final clamp (shouldn't be needed but safety check)
            adjusted = max(self.base_note, min(self.base_note + self.note_range - 1, adjusted))
            note_mapping[note] = adjusted
        
        # Apply mapping to all events
        self.events = []
        for event_time, event_type, note in self.original_events:
            adjusted_note = note_mapping.get(note, note)
            self.events.append((event_time, event_type, adjusted_note))
        
        # Calculate adjusted range
        adjusted_notes = [e[2] for e in self.events if e[1] == 'on']
        if adjusted_notes:
            self.adjusted_min_note = min(adjusted_notes)
            self.adjusted_max_note = max(adjusted_notes)
        else:
            self.adjusted_min_note = self.base_note
            self.adjusted_max_note = self.base_note
    
    def set_note_adjustment(self, enabled: bool, base_note: int = None, note_range: int = None):
        """Configure note adjustment settings"""
        self.adjust_notes = enabled
        if base_note is not None:
            self.base_note = max(0, min(96, base_note))  # Keep within reasonable MIDI range
        if note_range is not None:
            self.note_range = max(12, min(88, note_range))  # At least 1 octave, max piano range
        
        # Re-apply adjustment if we have events loaded
        if self.original_events:
            self._apply_note_adjustment()
    
    def set_misclick_settings(self, enabled: bool = None, rate: float = None, note_range: int = None):
        """Configure misclick (humanize) settings"""
        if enabled is not None:
            self.misclick_enabled = enabled
        if rate is not None:
            self.misclick_rate = max(0.0, min(100.0, rate))
        if note_range is not None:
            self.misclick_range = max(1, min(12, note_range))
    
    def _apply_misclick(self, note: int) -> int:
        """Possibly apply a random misclick to a note"""
        import random
        
        if not self.misclick_enabled:
            return note
        
        # Check if this note should misclick based on rate
        if random.random() * 100 > self.misclick_rate:
            return note  # No misclick this time
        
        # Apply random offset within range
        offset = random.randint(-self.misclick_range, self.misclick_range)
        if offset == 0:
            offset = random.choice([-1, 1])  # Ensure actual misclick
        
        new_note = note + offset
        
        # Keep within MIDI range
        new_note = max(0, min(127, new_note))
        
        return new_note
    
    def get_note_range_info(self) -> Dict:
        """Get information about the note range"""
        return {
            'original_min': self.original_min_note,
            'original_max': self.original_max_note,
            'original_range': self.original_max_note - self.original_min_note + 1 if self.original_events else 0,
            'adjusted_min': self.adjusted_min_note,
            'adjusted_max': self.adjusted_max_note,
            'adjusted_range': self.adjusted_max_note - self.adjusted_min_note + 1 if self.events else 0,
            'base_note': self.base_note,
            'available_range': self.note_range,
        }
    
    def get_note_count(self) -> int:
        """Get the number of note-on events in the loaded file"""
        return sum(1 for e in self.events if e[1] == 'on')
    
    def get_mapped_note_count(self) -> int:
        """Get the number of note-on events that have keyboard mappings"""
        return sum(1 for e in self.events if e[1] == 'on' and e[2] in self.midi_map)
    
    def play(self):
        """Start playing the loaded MIDI file"""
        if not self.events:
            return
        
        if self.paused:
            self.paused = False
            return
        
        self.playing = True
        self.paused = False
        self.current_position = 0.0
        self._misclick_mapping = {}  # Reset misclick tracking for new playback
        self.play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.play_thread.start()
    
    def pause(self):
        """Pause playback"""
        self.paused = True
    
    def stop(self):
        """Stop playback and release all keys"""
        self.playing = False
        self.paused = False
        self._release_all_keys()
        self.current_position = 0.0
    
    def seek_to(self, target_time: float):
        """Seek to a specific time in the MIDI file"""
        if not self.events:
            return
        
        # Clamp target time to valid range
        target_time = max(0.0, min(target_time, self.total_duration))
        
        was_playing = self.playing
        was_paused = self.paused
        
        # Stop current playback and release keys
        self.playing = False
        self.paused = False
        self._release_all_keys()
        
        # Wait for play thread to finish if it's running
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=0.5)
        
        # Update current position
        self.current_position = target_time
        
        # Update progress callback
        if self.on_progress_callback:
            self.on_progress_callback(target_time, self.total_duration)
        
        # If we were playing, restart from new position
        if was_playing and not was_paused:
            self._start_from_position(target_time)
    
    def _start_from_position(self, start_time: float):
        """Start playback from a specific time position"""
        if not self.events:
            return
        
        self.playing = True
        self.paused = False
        self.current_position = start_time
        self._misclick_mapping = {}
        self.play_thread = threading.Thread(
            target=self._play_loop_from_position, 
            args=(start_time,), 
            daemon=True
        )
        self.play_thread.start()
    
    def _play_loop_from_position(self, start_position: float):
        """Playback loop starting from a specific position"""
        # Find the first event at or after the start position
        event_index = 0
        for i, (event_time, _, _) in enumerate(self.events):
            if event_time >= start_position:
                event_index = i
                break
        else:
            # No events after start position, we're at the end
            self.playing = False
            if self.on_progress_callback:
                self.on_progress_callback(self.total_duration, self.total_duration)
            return
        
        # Calculate the time offset
        time_offset = start_position / self.speed
        start_time = time.perf_counter() - time_offset
        
        while self.playing and event_index < len(self.events):
            if self.paused:
                pause_start = time.perf_counter()
                while self.paused and self.playing:
                    time.sleep(0.01)
                start_time += time.perf_counter() - pause_start
                continue
            
            event_time, event_type, note = self.events[event_index]
            target_time = event_time / self.speed
            elapsed = time.perf_counter() - start_time
            
            wait_time = target_time - elapsed
            if wait_time > 0:
                time.sleep(min(wait_time, 0.01))
                continue
            
            # Process event (same as original _play_loop)
            actual_note = note
            if event_type == 'on':
                actual_note = self._apply_misclick(note)
            
            if event_type == 'off' and note in self._misclick_mapping:
                actual_note = self._misclick_mapping.pop(note)
            
            if actual_note in self.midi_map:
                key = self.midi_map[actual_note]
                try:
                    if event_type == 'on':
                        if actual_note != note:
                            if not hasattr(self, '_misclick_mapping'):
                                self._misclick_mapping = {}
                            self._misclick_mapping[note] = actual_note
                        self.mapper.press_key(key)
                        self.active_notes.add(actual_note)
                        if self.on_note_callback:
                            self.on_note_callback(actual_note, key, True)
                    else:
                        self.mapper.release_key(key)
                        self.active_notes.discard(actual_note)
                        if self.on_note_callback:
                            self.on_note_callback(actual_note, key, False)
                except Exception as e:
                    print(f"Error sending key '{key}': {e}")
            
            self.current_position = event_time
            if self.on_progress_callback:
                self.on_progress_callback(event_time, self.total_duration)
            
            event_index += 1
        
        self._release_all_keys()
        self.playing = False
        if self.on_progress_callback:
            self.on_progress_callback(self.total_duration, self.total_duration)
    
    def set_speed(self, speed: float):
        """Set playback speed (0.25 to 4.0)"""
        self.speed = max(0.25, min(4.0, speed))
    
    def update_midi_map(self, midi_map: Dict[int, str]):
        """Update the MIDI to keyboard mapping"""
        self.midi_map = midi_map
    
    def _release_all_keys(self):
        """Release all currently pressed keys"""
        for note in list(self.active_notes):
            if note in self.midi_map:
                try:
                    self.mapper.release_key(self.midi_map[note])
                except:
                    pass
        self.active_notes.clear()
    
    def _play_loop(self):
        """Main playback loop"""
        start_time = time.perf_counter()
        event_index = 0
        
        while self.playing and event_index < len(self.events):
            if self.paused:
                pause_start = time.perf_counter()
                while self.paused and self.playing:
                    time.sleep(0.01)
                # Adjust start time for pause duration
                start_time += time.perf_counter() - pause_start
                continue
            
            event_time, event_type, note = self.events[event_index]
            
            # Calculate when this event should happen
            target_time = event_time / self.speed
            elapsed = time.perf_counter() - start_time
            
            # Wait until it's time for this event
            wait_time = target_time - elapsed
            if wait_time > 0:
                time.sleep(min(wait_time, 0.01))
                continue
            
            # Process the event
            # Apply misclick for note-on events (note-off uses original note to release)
            actual_note = note
            if event_type == 'on':
                actual_note = self._apply_misclick(note)
            
            # For note-off, find the corresponding note that was pressed
            if event_type == 'off' and note in self._misclick_mapping:
                actual_note = self._misclick_mapping.pop(note)
            
            if actual_note in self.midi_map:
                key = self.midi_map[actual_note]
                try:
                    if event_type == 'on':
                        # Track which misclicked note corresponds to which original
                        if actual_note != note:
                            if not hasattr(self, '_misclick_mapping'):
                                self._misclick_mapping = {}
                            self._misclick_mapping[note] = actual_note
                        
                        self.mapper.press_key(key)
                        self.active_notes.add(actual_note)
                        if self.on_note_callback:
                            self.on_note_callback(actual_note, key, True)
                    else:
                        self.mapper.release_key(key)
                        self.active_notes.discard(actual_note)
                        if self.on_note_callback:
                            self.on_note_callback(actual_note, key, False)
                except Exception as e:
                    print(f"Error sending key '{key}': {e}")
            
            self.current_position = event_time
            if self.on_progress_callback:
                self.on_progress_callback(event_time, self.total_duration)
            
            event_index += 1
        
        # Playback finished
        self._release_all_keys()
        self.playing = False
        if self.on_progress_callback:
            self.on_progress_callback(self.total_duration, self.total_duration)


class MIDIMapperGUI:
    """GUI application for MIDI to keyboard mapping"""
    
    # Modern theme colors
    COLORS = {
        'bg_dark': '#1a1a2e',
        'bg_medium': '#16213e',
        'bg_light': '#0f3460',
        'accent': '#e94560',
        'accent_hover': '#ff6b6b',
        'text': '#eaeaea',
        'text_dim': '#a0a0a0',
        'success': '#4ecca3',
        'warning': '#feca57',
        'error': '#ff6b6b',
        'border': '#2d3748',
        'input_bg': '#2d2d44',
        'button_bg': '#e94560',
        'button_hover': '#ff6b6b',
    }
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MIDI to Keyboard Mapper")
        self.root.geometry("1050x1050")
        self.root.minsize(950, 750)
        
        # Set window background
        self.root.configure(bg=self.COLORS['bg_dark'])
        
        self.config_path = Path("config.json")
        # Create mapper without loading config (we'll load profiles separately)
        # Import PlatformKeyboard from keyboard_backend
        from src.keyboard import PlatformKeyboard
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
        
        # Force UI update to ensure all widgets are properly drawn
        self.root.update_idletasks()
    
    def _apply_modern_theme(self):
        """Apply modern dark theme to all widgets"""
        style = ttk.Style()
        
        # Use clam as base theme (most customizable)
        style.theme_use('clam')
        
        c = self.COLORS
        
        # Configure main frame
        style.configure("Main.TFrame", background=c['bg_dark'])
        style.configure("TFrame", background=c['bg_dark'])
        
        # Configure LabelFrame
        style.configure("TLabelframe", background=c['bg_dark'], bordercolor=c['border'], relief='flat')
        style.configure("TLabelframe.Label", background=c['bg_dark'], foreground=c['accent'], 
                       font=('Segoe UI', 10, 'bold'))
        
        # Configure Labels
        style.configure("TLabel", background=c['bg_dark'], foreground=c['text'], font=('Segoe UI', 9))
        style.configure("Status.TLabel", background=c['bg_dark'], foreground=c['success'], font=('Segoe UI', 9))
        style.configure("Error.TLabel", background=c['bg_dark'], foreground=c['error'], font=('Segoe UI', 9))
        style.configure("Dim.TLabel", background=c['bg_dark'], foreground=c['text_dim'], font=('Segoe UI', 8))
        
        # Configure Buttons
        style.configure("TButton", 
                       background=c['button_bg'], 
                       foreground='white',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 5),
                       borderwidth=0)
        style.map("TButton",
                 background=[('active', c['button_hover']), ('pressed', c['accent'])],
                 foreground=[('active', 'white'), ('pressed', 'white')])
        
        # Configure Entry
        style.configure("TEntry", 
                       fieldbackground=c['input_bg'],
                       foreground=c['text'],
                       insertcolor=c['text'],
                       bordercolor=c['border'],
                       font=('Segoe UI', 9))
        style.map("TEntry",
                 fieldbackground=[('focus', c['bg_light'])],
                 bordercolor=[('focus', c['accent'])])
        
        # Configure Combobox
        style.configure("TCombobox",
                       fieldbackground=c['input_bg'],
                       background=c['input_bg'],
                       foreground=c['text'],
                       arrowcolor=c['text'],
                       bordercolor=c['border'],
                       font=('Segoe UI', 9))
        style.map("TCombobox",
                 fieldbackground=[('readonly', c['input_bg'])],
                 selectbackground=[('readonly', c['accent'])],
                 selectforeground=[('readonly', 'white')])
        
        # Configure Checkbutton
        style.configure("TCheckbutton",
                       background=c['bg_dark'],
                       foreground=c['text'],
                       font=('Segoe UI', 9))
        style.map("TCheckbutton",
                 background=[('active', c['bg_dark'])],
                 foreground=[('active', c['accent'])])
        
        # Configure Treeview
        style.configure("Treeview",
                       background=c['input_bg'],
                       foreground=c['text'],
                       fieldbackground=c['input_bg'],
                       bordercolor=c['border'],
                       font=('Segoe UI', 9),
                       rowheight=28)
        style.configure("Treeview.Heading",
                       background=c['bg_light'],
                       foreground=c['text'],
                       font=('Segoe UI', 10, 'bold'),
                       borderwidth=0)
        style.map("Treeview",
                 background=[('selected', c['accent'])],
                 foreground=[('selected', 'white')])
        style.map("Treeview.Heading",
                 background=[('active', c['accent'])])
        
        # Configure Scrollbar
        style.configure("Vertical.TScrollbar",
                       background=c['bg_medium'],
                       troughcolor=c['bg_dark'],
                       bordercolor=c['border'],
                       arrowcolor=c['text'])
        
        # Configure Scale (slider)
        style.configure("Horizontal.TScale",
                       background=c['bg_dark'],
                       troughcolor=c['input_bg'],
                       bordercolor=c['border'])
        
        # Configure Progressbar
        style.configure("Horizontal.TProgressbar",
                       background=c['accent'],
                       troughcolor=c['input_bg'],
                       bordercolor=c['border'])
        
        # Configure Separator
        style.configure("TSeparator", background=c['border'])
        
        # Configure Spinbox
        style.configure("TSpinbox",
                       fieldbackground=c['input_bg'],
                       background=c['input_bg'],
                       foreground=c['text'],
                       arrowcolor=c['text'],
                       bordercolor=c['border'])
        
    def setup_ui(self):
        """Create the user interface"""
        # Apply modern dark theme
        self._apply_modern_theme()
        
        # Create scrollable container
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(self.root, bg=self.COLORS['bg_dark'], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Main container inside canvas
        main_frame = ttk.Frame(self.canvas, padding="10", style="Main.TFrame")
        self.canvas_window = self.canvas.create_window((0, 0), window=main_frame, anchor=tk.NW)
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Bind events for scrolling
        def on_frame_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        def on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        
        main_frame.bind("<Configure>", on_frame_configure)
        self.canvas.bind("<Configure>", on_canvas_configure)
        
        # Enable mouse wheel scrolling
        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
        
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
        
        self.status_label = ttk.Label(port_frame, text="Not connected", foreground=self.COLORS['error'])
        self.status_label.grid(row=1, column=0, columnspan=5, pady=5)
        
        # MIDI Note Detection
        detection_frame = ttk.LabelFrame(main_frame, text="MIDI Note Detection", padding="5")
        detection_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(detection_frame, text="Last detected notes:").grid(row=0, column=0, padx=5)
        self.last_notes_text = scrolledtext.ScrolledText(
            detection_frame, height=3, width=60, state="disabled",
            bg=self.COLORS['input_bg'], fg=self.COLORS['text'],
            insertbackground=self.COLORS['text'], font=('Segoe UI', 9),
            relief='flat', borderwidth=2
        )
        self.last_notes_text.grid(row=0, column=1, columnspan=2, padx=5, sticky=(tk.W, tk.E))
        detection_frame.columnconfigure(1, weight=1)
        
        # Key Assignment Section
        assignment_frame = ttk.LabelFrame(main_frame, text="Assign Keyboard Key", padding="5")
        assignment_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # All inputs on one row
        input_frame = ttk.Frame(assignment_frame)
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # MIDI Note
        ttk.Label(input_frame, text="MIDI Note:").grid(row=0, column=0, padx=(0, 5))
        self.midi_note_var = tk.StringVar()
        self.midi_note_entry = ttk.Entry(input_frame, textvariable=self.midi_note_var, width=8)
        self.midi_note_entry.grid(row=0, column=1, padx=2)
        ttk.Button(input_frame, text="Use Last", command=self.use_last_note, width=8).grid(row=0, column=2, padx=2)
        ttk.Button(input_frame, text="Detect", command=self.start_note_detection, width=7).grid(row=0, column=3, padx=2)
        
        # Separator
        ttk.Separator(input_frame, orient=tk.VERTICAL).grid(row=0, column=4, sticky=(tk.N, tk.S), padx=10)
        
        # Keyboard Key
        ttk.Label(input_frame, text="Key:").grid(row=0, column=5, padx=(0, 5))
        self.key_var = tk.StringVar()
        self.key_entry = ttk.Entry(input_frame, textvariable=self.key_var, width=20)
        self.key_entry.grid(row=0, column=6, padx=2)
        ttk.Button(input_frame, text="Capture Key/Combo", command=self.start_key_capture).grid(row=0, column=7, padx=2)
        self.capture_status_label = ttk.Label(input_frame, text="", foreground=self.COLORS['accent'])
        self.capture_status_label.grid(row=0, column=8, padx=5)
        
        # Assign button
        ttk.Button(input_frame, text="Assign", command=self.assign_key, width=10).grid(row=0, column=9, padx=(10, 0))
        
        # Examples
        ttk.Label(assignment_frame, text="Examples: 'a', 'ctrl+c', 'shift+f1', 'ctrl+alt+delete'", 
                 font=("Segoe UI", 8), foreground=self.COLORS['text_dim']).grid(row=1, column=0, pady=(0, 5), sticky=tk.W)
        
        # Mappings Display
        mappings_frame = ttk.LabelFrame(main_frame, text="Current Mappings", padding="5")
        mappings_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(4, weight=1)
        mappings_frame.columnconfigure(0, weight=1)
        mappings_frame.rowconfigure(0, weight=1)
        mappings_frame.rowconfigure(1, weight=0)
        
        # Treeview for mappings
        columns = ("midi_note", "note_name", "keyboard_key")
        self.mappings_tree = ttk.Treeview(mappings_frame, columns=columns, show="headings", height=10)
        
        # Configure column headings
        self.mappings_tree.heading("midi_note", text="MIDI Note", anchor=tk.CENTER)
        self.mappings_tree.heading("note_name", text="Note Name", anchor=tk.CENTER)
        self.mappings_tree.heading("keyboard_key", text="Keyboard Key", anchor=tk.CENTER)
        
        # Configure column widths and stretch
        self.mappings_tree.column("midi_note", width=150, minwidth=100, anchor=tk.CENTER, stretch=True)
        self.mappings_tree.column("note_name", width=150, minwidth=100, anchor=tk.CENTER, stretch=True)
        self.mappings_tree.column("keyboard_key", width=250, minwidth=150, anchor=tk.CENTER, stretch=True)
        
        # Hide the default first column
        self.mappings_tree.column("#0", width=0, stretch=False)
        
        scrollbar = ttk.Scrollbar(mappings_frame, orient=tk.VERTICAL, command=self.mappings_tree.yview)
        self.mappings_tree.configure(yscrollcommand=scrollbar.set)
        
        self.mappings_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Bind double-click to edit
        self.mappings_tree.bind("<Double-1>", self.on_mapping_double_click)
        
        # Buttons for mappings
        button_frame = ttk.Frame(mappings_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky=tk.W)
        
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
        
        # MIDI File Player Section
        player_frame = ttk.LabelFrame(main_frame, text="MIDI File Player (Auto-Play)", padding="5")
        player_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        player_frame.columnconfigure(1, weight=1)
        
        # File selection row
        ttk.Label(player_frame, text="MIDI File:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.midi_file_var = tk.StringVar()
        self.midi_file_entry = ttk.Entry(player_frame, textvariable=self.midi_file_var, width=50, state="readonly")
        self.midi_file_entry.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        ttk.Button(player_frame, text="Browse...", command=self.browse_midi_file).grid(row=0, column=2, padx=5)
        
        # File info row
        self.file_info_label = ttk.Label(player_frame, text="No file loaded", foreground=self.COLORS['text_dim'])
        self.file_info_label.grid(row=1, column=0, columnspan=3, padx=5, pady=2, sticky=tk.W)
        
        # Seek bar (clickable progress slider)
        self.progress_var = tk.DoubleVar(value=0)
        self._user_seeking = False  # Track if user is dragging the seek bar
        self.seek_scale = ttk.Scale(
            player_frame, from_=0, to=100, variable=self.progress_var,
            orient=tk.HORIZONTAL, command=self._on_seek_scale_changed
        )
        self.seek_scale.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        # Bind mouse events for seek tracking
        self.seek_scale.bind("<ButtonPress-1>", self._on_seek_start)
        self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_end)
        
        # Time label
        self.time_label = ttk.Label(player_frame, text="0:00 / 0:00 (click to seek)")
        self.time_label.grid(row=3, column=0, columnspan=3, padx=5, sticky=tk.W)
        
        # Playback controls row
        playback_frame = ttk.Frame(player_frame)
        playback_frame.grid(row=4, column=0, columnspan=3, pady=5)
        
        self.play_btn = ttk.Button(playback_frame, text="Play", command=self.play_midi_file, width=10)
        self.play_btn.grid(row=0, column=0, padx=2)
        self.test_play_btn = ttk.Button(playback_frame, text="Test & Play", command=self.test_and_play_midi, width=12)
        self.test_play_btn.grid(row=0, column=1, padx=2)
        self.pause_btn = ttk.Button(playback_frame, text="Pause", command=self.pause_midi_file, width=10, state="disabled")
        self.pause_btn.grid(row=0, column=2, padx=2)
        self.practice_btn = ttk.Button(playback_frame, text="Practice", command=self.practice_while_paused, width=10, state="disabled")
        self.practice_btn.grid(row=0, column=3, padx=2)
        self.stop_btn = ttk.Button(playback_frame, text="Stop", command=self.stop_midi_file, width=10, state="disabled")
        self.stop_btn.grid(row=0, column=4, padx=2)
        
        # Speed control
        ttk.Label(playback_frame, text="Speed:").grid(row=0, column=5, padx=(20, 5))
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_scale = ttk.Scale(playback_frame, from_=0.25, to=2.0, variable=self.speed_var, 
                                     orient=tk.HORIZONTAL, length=100, command=self.on_speed_changed)
        self.speed_scale.grid(row=0, column=6, padx=2)
        self.speed_label = ttk.Label(playback_frame, text="1.0x", width=5)
        self.speed_label.grid(row=0, column=7, padx=2)
        
        # Current note display
        self.current_note_label = ttk.Label(player_frame, text="", foreground=self.COLORS['accent'])
        self.current_note_label.grid(row=5, column=0, columnspan=3, padx=5, pady=2, sticky=tk.W)
        
        # Note Adjustment Section
        adjust_frame = ttk.Frame(player_frame)
        adjust_frame.grid(row=6, column=0, columnspan=3, pady=5, sticky=(tk.W, tk.E))
        
        self.adjust_notes_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(adjust_frame, text="Auto-adjust notes to fit 36-note range", 
                       variable=self.adjust_notes_var, command=self.on_adjust_notes_changed).grid(row=0, column=0, padx=5, sticky=tk.W)
        
        ttk.Label(adjust_frame, text="Base Note:").grid(row=0, column=1, padx=(20, 5))
        self.base_note_var = tk.IntVar(value=48)  # C3
        base_note_options = [
            ("C2 (36)", 36), ("C3 (48)", 48), ("C4 (60)", 60), ("C5 (72)", 72)
        ]
        self.base_note_combo = ttk.Combobox(adjust_frame, textvariable=self.base_note_var, width=10, state="readonly")
        self.base_note_combo['values'] = [f"{name}" for name, _ in base_note_options]
        self.base_note_combo.set("C3 (48)")
        self.base_note_combo.grid(row=0, column=2, padx=2)
        self.base_note_combo.bind("<<ComboboxSelected>>", self.on_base_note_changed)
        self._base_note_options = base_note_options
        
        # Random Misclick Section (humanize playback)
        misclick_frame = ttk.Frame(player_frame)
        misclick_frame.grid(row=7, column=0, columnspan=3, pady=2, sticky=(tk.W, tk.E))
        
        self.misclick_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(misclick_frame, text="Random misclicks (humanize)", 
                       variable=self.misclick_enabled_var, command=self.on_misclick_changed).grid(row=0, column=0, padx=5, sticky=tk.W)
        
        ttk.Label(misclick_frame, text="Rate:").grid(row=0, column=1, padx=(20, 5))
        self.misclick_rate_var = tk.DoubleVar(value=2.0)
        self.misclick_scale = ttk.Scale(misclick_frame, from_=0.5, to=15.0, variable=self.misclick_rate_var,
                                        orient=tk.HORIZONTAL, length=100, command=self.on_misclick_rate_changed)
        self.misclick_scale.grid(row=0, column=2, padx=2)
        self.misclick_rate_label = ttk.Label(misclick_frame, text="2.0%", width=5)
        self.misclick_rate_label.grid(row=0, column=3, padx=2)
        
        ttk.Label(misclick_frame, text="Range:").grid(row=0, column=4, padx=(10, 5))
        self.misclick_range_var = tk.IntVar(value=2)
        self.misclick_range_spin = ttk.Spinbox(misclick_frame, from_=1, to=5, textvariable=self.misclick_range_var,
                                               width=3, command=self.on_misclick_changed)
        self.misclick_range_spin.grid(row=0, column=5, padx=2)
        ttk.Label(misclick_frame, text="notes").grid(row=0, column=6, padx=2)
        
        # Test duration setting
        ttk.Label(misclick_frame, text="Test:").grid(row=0, column=7, padx=(15, 5))
        self.test_duration_var = tk.IntVar(value=4)
        self.test_duration_spin = ttk.Spinbox(misclick_frame, from_=1, to=15, textvariable=self.test_duration_var,
                                              width=3)
        self.test_duration_spin.grid(row=0, column=8, padx=2)
        ttk.Label(misclick_frame, text="sec").grid(row=0, column=9, padx=2)
        
        # Note range info display
        self.note_range_label = ttk.Label(player_frame, text="", foreground=self.COLORS['text_dim'])
        self.note_range_label.grid(row=8, column=0, columnspan=3, padx=5, pady=2, sticky=tk.W)
        
        # Initialize MIDI file player (pass mapper for proper key handling with DirectInput)
        self.midi_player = MIDIFilePlayer(self.mapper, self.midi_map)
        self.midi_player.on_progress_callback = self.on_player_progress
        self.midi_player.on_note_callback = self.on_player_note
        
        # Audio to MIDI Converter Section
        converter_frame = ttk.LabelFrame(main_frame, text="Audio to MIDI Converter (AI)", padding="5")
        converter_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        converter_frame.columnconfigure(1, weight=1)
        
        # Audio file/folder selection
        ttk.Label(converter_frame, text="Audio Source:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.audio_file_var = tk.StringVar()
        self.audio_file_entry = ttk.Entry(converter_frame, textvariable=self.audio_file_var, width=50, state="readonly")
        self.audio_file_entry.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        
        # Browse buttons frame
        browse_frame = ttk.Frame(converter_frame)
        browse_frame.grid(row=0, column=2, padx=5)
        ttk.Button(browse_frame, text="File", command=self.browse_audio_file, width=6).grid(row=0, column=0, padx=2)
        ttk.Button(browse_frame, text="Folder", command=self.browse_audio_folder, width=6).grid(row=0, column=1, padx=2)
        
        # Output folder selection
        ttk.Label(converter_frame, text="Output Folder:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.midi_output_folder_var = tk.StringVar()
        # Default to 'midi_output' folder in midimap directory
        default_output = str(Path(__file__).parent.parent / "midi_output")
        self.midi_output_folder_var.set(default_output)
        self.midi_output_entry = ttk.Entry(converter_frame, textvariable=self.midi_output_folder_var, width=50)
        self.midi_output_entry.grid(row=1, column=1, padx=5, sticky=(tk.W, tk.E))
        ttk.Button(converter_frame, text="Browse...", command=self.browse_midi_output_folder).grid(row=1, column=2, padx=5)
        
        # Convert button and status
        convert_controls = ttk.Frame(converter_frame)
        convert_controls.grid(row=2, column=0, columnspan=3, pady=5)
        
        self.convert_btn = ttk.Button(convert_controls, text="Convert", command=self.convert_audio_to_midi, width=12)
        self.convert_btn.grid(row=0, column=0, padx=5)
        
        self.convert_and_load_btn = ttk.Button(convert_controls, text="Convert & Load", command=self.convert_and_load_midi, width=14)
        self.convert_and_load_btn.grid(row=0, column=1, padx=5)
        
        self.convert_folder_btn = ttk.Button(convert_controls, text="Convert Folder", command=self.convert_folder_to_midi, width=14)
        self.convert_folder_btn.grid(row=0, column=2, padx=5)
        
        # Parallel workers control
        ttk.Label(convert_controls, text="Workers:").grid(row=0, column=3, padx=(15, 2))
        self.batch_workers_var = tk.IntVar(value=4)
        self.batch_workers_spinbox = ttk.Spinbox(
            convert_controls, from_=1, to=8, width=3,
            textvariable=self.batch_workers_var
        )
        self.batch_workers_spinbox.grid(row=0, column=4, padx=2)
        
        # Conversion progress
        self.convert_progress_var = tk.DoubleVar(value=0)
        self.convert_progress = ttk.Progressbar(converter_frame, variable=self.convert_progress_var, maximum=100)
        self.convert_progress.grid(row=3, column=0, columnspan=3, padx=5, pady=2, sticky=(tk.W, tk.E))
        
        # Conversion status/log
        self.convert_status_label = ttk.Label(converter_frame, text="Select audio file or folder (MP3, WAV, FLAC, etc.)", foreground=self.COLORS['text_dim'])
        self.convert_status_label.grid(row=4, column=0, columnspan=3, padx=5, pady=2, sticky=tk.W)
        
        # Initialize audio converter (lazy load)
        self.audio_converter = None
        self._batch_converting = False
        self._batch_files = []
        self._batch_current = 0
        
        # YouTube to MP3 Converter Section
        youtube_frame = ttk.LabelFrame(main_frame, text="YouTube to MP3 Converter", padding="5")
        youtube_frame.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        youtube_frame.columnconfigure(1, weight=1)
        
        # YouTube URL input
        ttk.Label(youtube_frame, text="YouTube URL:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.youtube_url_var = tk.StringVar()
        self.youtube_url_entry = ttk.Entry(youtube_frame, textvariable=self.youtube_url_var, width=50)
        self.youtube_url_entry.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        
        # YouTube convert buttons
        yt_btn_frame = ttk.Frame(youtube_frame)
        yt_btn_frame.grid(row=0, column=2, padx=5)
        
        self.yt_download_btn = ttk.Button(yt_btn_frame, text="Download MP3", command=self.download_youtube_mp3, width=15)
        self.yt_download_btn.grid(row=0, column=0, padx=2)
        
        self.yt_convert_btn = ttk.Button(yt_btn_frame, text="Download & Convert", command=self.download_and_convert_youtube, width=18)
        self.yt_convert_btn.grid(row=0, column=1, padx=2)
        
        # YouTube progress
        self.yt_progress_var = tk.DoubleVar(value=0)
        self.yt_progress = ttk.Progressbar(youtube_frame, variable=self.yt_progress_var, maximum=100)
        self.yt_progress.grid(row=1, column=0, columnspan=3, padx=5, pady=2, sticky=(tk.W, tk.E))
        
        # YouTube status
        self.yt_status_label = ttk.Label(youtube_frame, text="Enter a YouTube URL to download as MP3", foreground=self.COLORS['text_dim'])
        self.yt_status_label.grid(row=2, column=0, columnspan=3, padx=5, pady=2, sticky=tk.W)
        
        # Initialize YouTube converter (lazy load)
        self.youtube_converter = None
        
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
        
        # Update MIDI file player if it exists
        if hasattr(self, 'midi_player'):
            self.midi_player.update_midi_map(self.midi_map)
        
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
        
        # Update MIDI file player
        if hasattr(self, 'midi_player'):
            self.midi_player.update_midi_map(self.midi_map)
        
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
            self.status_label.config(text=f"Connected: {port_name}", foreground=self.COLORS['success'])
            self.running = True
            self.start_midi_listener()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to MIDI port: {e}")
            self.status_label.config(text="Connection failed", foreground=self.COLORS['error'])
    
    def disconnect_midi(self):
        """Disconnect from MIDI port"""
        self.running = False
        if self.midi_port:
            self.midi_port.close()
            self.midi_port = None
        self.status_label.config(text="Not connected", foreground=self.COLORS['error'])
    
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
                    # Check if it's a printable character
                    if char.isprintable() and len(char) == 1:
                        return char.lower()
                    # Handle control characters (Ctrl+letter produces control codes)
                    # Control codes are 0x01-0x1A for Ctrl+A through Ctrl+Z
                    elif ord(char) >= 1 and ord(char) <= 26:
                        # Convert control code back to letter (0x01 -> 'a', 0x02 -> 'b', etc.)
                        return chr(ord('a') + ord(char) - 1)
            except AttributeError:
                # key.char doesn't exist, try vk (virtual key code)
                try:
                    vk = key.vk
                    if vk:
                        # Virtual key codes for A-Z are 65-90
                        if 65 <= vk <= 90:
                            return chr(vk).lower()
                        # Virtual key codes for 0-9 are 48-57
                        elif 48 <= vk <= 57:
                            return chr(vk)
                except:
                    pass
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
        # Update MIDI file player
        if hasattr(self, 'midi_player'):
            self.midi_player.update_midi_map(self.midi_map)
        
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
            # Update MIDI file player
            if hasattr(self, 'midi_player'):
                self.midi_player.update_midi_map(self.midi_map)
            self.update_mappings_display()
    
    def clear_all_mappings(self):
        """Clear all mappings in current profile"""
        if messagebox.askyesno("Confirm", f"Clear all mappings in profile '{self.current_profile}'?"):
            self.midi_map.clear()
            self.mapper.midi_map.clear()
            # Update profile storage
            self.profiles[self.current_profile] = {}
            # Update MIDI file player
            if hasattr(self, 'midi_player'):
                self.midi_player.update_midi_map(self.midi_map)
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
            self.mappings_tree.insert("", tk.END, values=(str(midi_note), note_name, key))
        
        # Update MIDI file info if a file is loaded
        self._update_file_info()
    
    def _update_file_info(self):
        """Update the MIDI file info label with current mapping stats"""
        if hasattr(self, 'midi_player') and self.midi_player.events:
            self._update_file_info_full()
    
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
    
    # MIDI File Player Methods
    def browse_midi_file(self):
        """Open file dialog to select a MIDI file"""
        filepath = filedialog.askopenfilename(
            title="Select MIDI File",
            filetypes=[
                ("MIDI Files", "*.mid *.midi"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            self.load_midi_file(filepath)
    
    def load_midi_file(self, filepath: str):
        """Load a MIDI file for playback"""
        # Apply current adjustment settings before loading
        self.midi_player.set_note_adjustment(
            self.adjust_notes_var.get(),
            self._get_selected_base_note(),
            36  # 36-note range
        )
        
        if self.midi_player.load_file(filepath):
            self.midi_file_var.set(Path(filepath).name)
            
            # Update file info and note range
            self._update_file_info_full()
            
            duration = self.midi_player.total_duration
            duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
            self.time_label.config(text=f"0:00 / {duration_str} (click to seek)")
            self.progress_var.set(0)
            self.play_btn.config(state="normal")
        else:
            messagebox.showerror("Error", f"Failed to load MIDI file: {filepath}")
    
    def _get_selected_base_note(self) -> int:
        """Get the selected base note value from combo box"""
        selected = self.base_note_combo.get()
        for name, value in self._base_note_options:
            if name == selected:
                return value
        return 48  # Default C3
    
    def _update_file_info_full(self):
        """Update file info and note range display"""
        if not hasattr(self, 'midi_player') or not self.midi_player.events:
            return
        
        total_notes = self.midi_player.get_note_count()
        mapped_notes = self.midi_player.get_mapped_note_count()
        duration = self.midi_player.total_duration
        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
        
        self.file_info_label.config(
            text=f"Duration: {duration_str} | Notes: {total_notes} | Mapped: {mapped_notes}",
            foreground=self.COLORS['text']
        )
        
        # Update note range info
        range_info = self.midi_player.get_note_range_info()
        orig_min_name = self.get_note_name(range_info['original_min'])
        orig_max_name = self.get_note_name(range_info['original_max'])
        adj_min_name = self.get_note_name(range_info['adjusted_min'])
        adj_max_name = self.get_note_name(range_info['adjusted_max'])
        
        if self.adjust_notes_var.get():
            self.note_range_label.config(
                text=f"Original: {orig_min_name}-{orig_max_name} ({range_info['original_range']} notes) -> "
                     f"Adjusted: {adj_min_name}-{adj_max_name} ({range_info['adjusted_range']} notes)",
                foreground=self.COLORS['success'] if range_info['adjusted_range'] <= 36 else self.COLORS['warning']
            )
        else:
            self.note_range_label.config(
                text=f"Note range: {orig_min_name}-{orig_max_name} ({range_info['original_range']} notes) - No adjustment",
                foreground=self.COLORS['text_dim']
            )
    
    def on_adjust_notes_changed(self):
        """Handle note adjustment checkbox change"""
        if hasattr(self, 'midi_player') and self.midi_player.original_events:
            self.midi_player.set_note_adjustment(
                self.adjust_notes_var.get(),
                self._get_selected_base_note(),
                36
            )
            self._update_file_info_full()
    
    def on_base_note_changed(self, event=None):
        """Handle base note selection change"""
        if hasattr(self, 'midi_player') and self.midi_player.original_events:
            self.midi_player.set_note_adjustment(
                self.adjust_notes_var.get(),
                self._get_selected_base_note(),
                36
            )
            self._update_file_info_full()
    
    def on_misclick_changed(self):
        """Handle misclick checkbox/spinbox change"""
        if hasattr(self, 'midi_player'):
            self.midi_player.set_misclick_settings(
                enabled=self.misclick_enabled_var.get(),
                rate=self.misclick_rate_var.get(),
                note_range=self.misclick_range_var.get()
            )
    
    def on_misclick_rate_changed(self, value):
        """Handle misclick rate slider change"""
        rate = float(value)
        self.misclick_rate_label.config(text=f"{rate:.1f}%")
        if hasattr(self, 'midi_player'):
            self.midi_player.set_misclick_settings(
                enabled=self.misclick_enabled_var.get(),
                rate=rate,
                note_range=self.misclick_range_var.get()
            )
    
    def play_midi_file(self):
        """Start playing the loaded MIDI file"""
        if not self.midi_player.events:
            messagebox.showwarning("Warning", "Please load a MIDI file first")
            return
        
        # Update the player's midi map
        self.midi_player.update_midi_map(self.midi_map)
        
        self.midi_player.play()
        self.play_btn.config(state="disabled")
        self.test_play_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
    
    def test_and_play_midi(self):
        """Play test notes, then a sample from middle, then start full playback"""
        if not self.midi_player.events:
            messagebox.showwarning("Warning", "Please load a MIDI file first")
            return
        
        if not self.midi_map:
            messagebox.showwarning("Warning", "Please assign some key mappings first")
            return
        
        # Update the player's midi map
        self.midi_player.update_midi_map(self.midi_map)
        
        # Disable buttons during test
        self.play_btn.config(state="disabled")
        self.test_play_btn.config(state="disabled")
        self.pause_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        
        self.current_note_label.config(text="Testing keys...")
        
        # Clear any previous cancellation flag
        if hasattr(self, '_test_cancelled'):
            delattr(self, '_test_cancelled')
        
        # Get test duration from UI
        test_duration = self.test_duration_var.get()
        
        # Run test sequence in background thread
        def run_test_sequence():
            import random
            
            # Get mapped notes from the MIDI file
            mapped_notes = []
            for event_time, event_type, note in self.midi_player.events:
                if event_type == 'on' and note in self.midi_map:
                    if note not in mapped_notes:
                        mapped_notes.append(note)
            
            if not mapped_notes:
                self.root.after(0, lambda: self.current_note_label.config(text="No mapped notes found in MIDI"))
                self.root.after(0, lambda: self._enable_play_buttons())
                return
            
            # Phase 1: Play individual test notes (3-5 random notes)
            self.root.after(0, lambda: self.current_note_label.config(text="Phase 1: Testing individual keys..."))
            test_notes = random.sample(mapped_notes, min(5, len(mapped_notes)))
            
            for note in test_notes:
                if hasattr(self, '_test_cancelled'):
                    break
                key = self.midi_map[note]
                note_name = self.get_note_name(note)
                self.root.after(0, lambda n=note, k=key, nn=note_name: self.current_note_label.config(
                    text=f"Testing: Note {n} ({nn}) -> Key '{k}'"
                ))
                try:
                    self.mapper.press_key(key)
                    time.sleep(0.15)
                    self.mapper.release_key(key)
                    time.sleep(0.25)
                except:
                    pass
            
            if hasattr(self, '_test_cancelled'):
                delattr(self, '_test_cancelled')
                return
            
            time.sleep(0.5)
            
            # Phase 2: Play a short melody from the middle of the song
            self.root.after(0, lambda: self.current_note_label.config(text="Phase 2: Playing sample from middle..."))
            
            # Find the middle section of the song
            total_duration = self.midi_player.total_duration
            middle_start = total_duration * 0.4  # Start at 40%
            middle_end = total_duration * 0.5    # End at 50%
            
            # Get events from the middle section
            middle_events = [
                (t, typ, n) for t, typ, n in self.midi_player.events
                if middle_start <= t <= middle_end and n in self.midi_map
            ]
            
            if middle_events:
                # Play up to test_duration seconds of the middle section
                start_time_offset = middle_events[0][0] if middle_events else middle_start
                active_notes = set()
                
                import time as time_module
                playback_start = time_module.perf_counter()
                
                for event_time, event_type, note in middle_events:
                    if hasattr(self, '_test_cancelled'):
                        break
                    
                    # Wait for the right time (relative to start)
                    relative_time = event_time - start_time_offset
                    if relative_time > float(test_duration):  # Max test_duration seconds of sample
                        break
                    
                    elapsed = time_module.perf_counter() - playback_start
                    wait_time = relative_time - elapsed
                    if wait_time > 0:
                        time.sleep(wait_time)
                    
                    key = self.midi_map[note]
                    try:
                        if event_type == 'on':
                            self.mapper.press_key(key)
                            active_notes.add(note)
                            note_name = self.get_note_name(note)
                            self.root.after(0, lambda n=note, k=key, nn=note_name: self.current_note_label.config(
                                text=f"Sample: Note {n} ({nn}) -> Key '{k}'"
                            ))
                        else:
                            self.mapper.release_key(key)
                            active_notes.discard(note)
                    except:
                        pass
                
                # Release any still-held notes
                for note in active_notes:
                    if note in self.midi_map:
                        try:
                            self.mapper.release_key(self.midi_map[note])
                        except:
                            pass
            
            if hasattr(self, '_test_cancelled'):
                delattr(self, '_test_cancelled')
                return
            
            time.sleep(0.8)
            
            # Phase 3: Start full playback
            self.root.after(0, lambda: self.current_note_label.config(text="Starting full playback..."))
            time.sleep(0.3)
            
            def start_playback():
                self.midi_player.play()
                self.pause_btn.config(state="normal")
            
            self.root.after(0, start_playback)
        
        # Start test sequence
        threading.Thread(target=run_test_sequence, daemon=True).start()
    
    def _enable_play_buttons(self):
        """Re-enable play buttons after test"""
        self.play_btn.config(state="normal")
        self.test_play_btn.config(state="normal")
    
    def practice_while_paused(self):
        """Play test notes while paused to practice before resuming"""
        if not self.midi_player.paused:
            return
        
        if not self.midi_map:
            messagebox.showwarning("Warning", "No key mappings available")
            return
        
        # Disable practice button during practice
        self.practice_btn.config(state="disabled")
        self.pause_btn.config(state="disabled")
        
        # Get test duration
        test_duration = self.test_duration_var.get()
        
        self.current_note_label.config(text="Practicing test notes...")
        
        def run_practice():
            import random
            
            # Get mapped notes from the MIDI file
            mapped_notes = []
            for event_time, event_type, note in self.midi_player.events:
                if event_type == 'on' and note in self.midi_map:
                    if note not in mapped_notes:
                        mapped_notes.append(note)
            
            if not mapped_notes:
                # Fall back to all mapped notes
                mapped_notes = list(self.midi_map.keys())
            
            if not mapped_notes:
                self.root.after(0, lambda: self.current_note_label.config(text="No notes to practice"))
                self.root.after(0, lambda: self._finish_practice())
                return
            
            # Phase 1: Play a few individual test notes
            self.root.after(0, lambda: self.current_note_label.config(text="Testing individual keys..."))
            test_notes = random.sample(mapped_notes, min(4, len(mapped_notes)))
            
            for note in test_notes:
                if hasattr(self, '_practice_cancelled'):
                    break
                key = self.midi_map[note]
                note_name = self.get_note_name(note)
                self.root.after(0, lambda n=note, k=key, nn=note_name: self.current_note_label.config(
                    text=f"Practice: Note {n} ({nn}) -> Key '{k}'"
                ))
                try:
                    self.mapper.press_key(key)
                    time.sleep(0.15)
                    self.mapper.release_key(key)
                    time.sleep(0.2)
                except:
                    pass
            
            if hasattr(self, '_practice_cancelled'):
                delattr(self, '_practice_cancelled')
                self.root.after(0, lambda: self._finish_practice())
                return
            
            time.sleep(0.3)
            
            # Phase 2: Play a short sample around current position
            current_pos = self.midi_player.current_position
            sample_start = max(0, current_pos - 2)  # 2 seconds before current position
            sample_end = current_pos + float(test_duration)  # test_duration seconds after
            
            self.root.after(0, lambda: self.current_note_label.config(text="Playing sample around current position..."))
            
            # Get events around current position
            nearby_events = [
                (t, typ, n) for t, typ, n in self.midi_player.events
                if sample_start <= t <= sample_end and n in self.midi_map
            ]
            
            if nearby_events:
                start_time_offset = nearby_events[0][0] if nearby_events else sample_start
                active_notes = set()
                
                import time as time_module
                playback_start = time_module.perf_counter()
                
                for event_time, event_type, note in nearby_events:
                    if hasattr(self, '_practice_cancelled'):
                        break
                    
                    relative_time = event_time - start_time_offset
                    if relative_time > float(test_duration) + 2:  # Max duration
                        break
                    
                    elapsed = time_module.perf_counter() - playback_start
                    wait_time = relative_time - elapsed
                    if wait_time > 0:
                        time.sleep(wait_time)
                    
                    key = self.midi_map[note]
                    try:
                        if event_type == 'on':
                            self.mapper.press_key(key)
                            active_notes.add(note)
                            note_name = self.get_note_name(note)
                            self.root.after(0, lambda n=note, k=key, nn=note_name: self.current_note_label.config(
                                text=f"Practice: Note {n} ({nn}) -> Key '{k}'"
                            ))
                        else:
                            self.mapper.release_key(key)
                            active_notes.discard(note)
                    except:
                        pass
                
                # Release held notes
                for note in active_notes:
                    if note in self.midi_map:
                        try:
                            self.mapper.release_key(self.midi_map[note])
                        except:
                            pass
            
            if hasattr(self, '_practice_cancelled'):
                delattr(self, '_practice_cancelled')
            
            self.root.after(0, lambda: self._finish_practice())
        
        # Clear cancellation flag
        if hasattr(self, '_practice_cancelled'):
            delattr(self, '_practice_cancelled')
        
        threading.Thread(target=run_practice, daemon=True).start()
    
    def _finish_practice(self):
        """Re-enable buttons after practice"""
        if self.midi_player.paused:
            self.practice_btn.config(state="normal")
            self.pause_btn.config(state="normal")
            self.current_note_label.config(text="Practice done - Click 'Resume' to continue playback")
    
    def pause_midi_file(self):
        """Pause/resume playback"""
        if self.midi_player.paused:
            self.midi_player.paused = False
            self.pause_btn.config(text="Pause")
            self.practice_btn.config(state="disabled")
            self.current_note_label.config(text="Resuming playback...")
        else:
            self.midi_player.pause()
            self.pause_btn.config(text="Resume")
            self.practice_btn.config(state="normal")
            self.current_note_label.config(text="Paused - Click 'Practice' to test notes, then 'Resume' to continue")
    
    def stop_midi_file(self):
        """Stop playback"""
        # Cancel test/practice sequence if running
        self._test_cancelled = True
        self._practice_cancelled = True
        
        self.midi_player.stop()
        self.play_btn.config(state="normal")
        self.test_play_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pause")
        self.practice_btn.config(state="disabled")
        self.stop_btn.config(state="disabled")
        self.progress_var.set(0)
        self.current_note_label.config(text="")
        
        # Update time label
        duration = self.midi_player.total_duration
        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
        self.time_label.config(text=f"0:00 / {duration_str} (click to seek)")
    
    def on_speed_changed(self, value):
        """Handle speed slider change"""
        speed = float(value)
        self.midi_player.set_speed(speed)
        self.speed_label.config(text=f"{speed:.2f}x")
    
    def _on_seek_start(self, event):
        """Called when user starts dragging the seek bar"""
        self._user_seeking = True
    
    def _on_seek_end(self, event):
        """Called when user releases the seek bar"""
        self._user_seeking = False
        # Perform the actual seek
        self._perform_seek()
    
    def _on_seek_scale_changed(self, value):
        """Handle seek scale value changes"""
        if self._user_seeking:
            # Update time label while dragging
            progress = float(value)
            total_time = self.midi_player.total_duration
            if total_time > 0:
                current_time = (progress / 100) * total_time
                current_str = f"{int(current_time // 60)}:{int(current_time % 60):02d}"
                total_str = f"{int(total_time // 60)}:{int(total_time % 60):02d}"
                self.time_label.config(text=f"{current_str} / {total_str} (seeking...)")
    
    def _perform_seek(self):
        """Execute seek to current slider position"""
        progress = self.progress_var.get()
        total_time = self.midi_player.total_duration
        if total_time > 0:
            target_time = (progress / 100) * total_time
            self.midi_player.seek_to(target_time)
            
            # Update time label
            current_str = f"{int(target_time // 60)}:{int(target_time % 60):02d}"
            total_str = f"{int(total_time // 60)}:{int(total_time % 60):02d}"
            self.time_label.config(text=f"{current_str} / {total_str}")
    
    def on_player_progress(self, current_time: float, total_time: float):
        """Callback for playback progress updates"""
        def update():
            # Don't update slider if user is seeking
            if self._user_seeking:
                return
            
            if total_time > 0:
                progress = (current_time / total_time) * 100
                self.progress_var.set(progress)
                
                current_str = f"{int(current_time // 60)}:{int(current_time % 60):02d}"
                total_str = f"{int(total_time // 60)}:{int(total_time % 60):02d}"
                self.time_label.config(text=f"{current_str} / {total_str}")
            
            # Check if playback finished
            if current_time >= total_time:
                self.play_btn.config(state="normal")
                self.test_play_btn.config(state="normal")
                self.pause_btn.config(state="disabled", text="Pause")
                self.practice_btn.config(state="disabled")
                self.stop_btn.config(state="disabled")
                self.current_note_label.config(text="Playback finished")
        
        self.root.after(0, update)
    
    def on_player_note(self, note: int, key: str, is_on: bool):
        """Callback for note events during playback"""
        def update():
            note_name = self.get_note_name(note)
            if is_on:
                self.current_note_label.config(text=f"Playing: Note {note} ({note_name}) -> Key '{key}'")
            else:
                self.current_note_label.config(text="")
        
        self.root.after(0, update)
    
    # Audio to MIDI Converter Methods
    def _get_audio_converter(self):
        """Lazy-load the audio converter"""
        if self.audio_converter is None:
            try:
                from src.converters.audio import AudioToMidiConverter
                self.audio_converter = AudioToMidiConverter()
                self.audio_converter.log_callback = self._on_converter_log
                self.audio_converter.progress_callback = self._on_converter_progress
                
                # Check dependencies
                deps_ok, missing = self.audio_converter.check_dependencies()
                if not deps_ok:
                    messagebox.showerror("Missing Dependencies", 
                        f"The following packages are required for audio conversion:\n\n"
                        f"{', '.join(missing)}\n\n"
                        f"Install them with:\npip install {' '.join(missing)}")
                    return None
                    
            except ImportError as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"Import error: {error_details}")
                messagebox.showerror("Error", 
                    f"Audio converter not available: {e}\n\n"
                    f"Make sure librosa and onnxruntime are installed:\n"
                    f"pip install librosa onnxruntime")
                return None
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"Error initializing converter: {error_details}")
                messagebox.showerror("Error", f"Failed to initialize audio converter:\n\n{e}")
                return None
        return self.audio_converter
    
    def browse_audio_file(self):
        """Open file dialog to select an audio file"""
        filepath = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[
                ("Audio Files", "*.mp3 *.wav *.flac *.ogg *.m4a *.wma"),
                ("MP3 Files", "*.mp3"),
                ("WAV Files", "*.wav"),
                ("FLAC Files", "*.flac"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            self.audio_file_var.set(filepath)
            self.convert_status_label.config(text=f"Ready to convert: {Path(filepath).name}", foreground=self.COLORS['text'])
    
    def browse_audio_folder(self):
        """Open folder dialog to select a folder with audio files"""
        folder = filedialog.askdirectory(
            title="Select Folder with Audio Files"
        )
        if folder:
            # Count audio files in folder
            audio_extensions = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma'}
            audio_files = [f for f in Path(folder).iterdir() 
                          if f.is_file() and f.suffix.lower() in audio_extensions]
            
            if audio_files:
                self.audio_file_var.set(folder)
                self.convert_status_label.config(
                    text=f"Folder selected: {len(audio_files)} audio files found", 
                    foreground=self.COLORS['text']
                )
            else:
                messagebox.showwarning("Warning", "No audio files found in the selected folder")
    
    def browse_midi_output_folder(self):
        """Open folder dialog to select MIDI output folder"""
        folder = filedialog.askdirectory(
            title="Select MIDI Output Folder",
            initialdir=self.midi_output_folder_var.get() or str(Path.home())
        )
        if folder:
            self.midi_output_folder_var.set(folder)
    
    def _get_midi_output_path(self, audio_path: str) -> Path:
        """Get the output path for a converted MIDI file"""
        output_folder = Path(self.midi_output_folder_var.get())
        output_folder.mkdir(parents=True, exist_ok=True)
        audio_name = Path(audio_path).stem
        return output_folder / f"{audio_name}.mid"
    
    def convert_audio_to_midi(self):
        """Convert the selected audio file to MIDI"""
        audio_path = self.audio_file_var.get()
        if not audio_path:
            messagebox.showwarning("Warning", "Please select an audio file first")
            return
        
        converter = self._get_audio_converter()
        if converter is None:
            return
        
        # Check if model is available
        if not converter.is_model_available():
            messagebox.showerror("Error", "AI model not found!\n\nThe model file should be at:\nmidimap/models/model.onnx")
            return
        
        # Disable buttons during conversion
        self.convert_btn.config(state="disabled")
        self.convert_and_load_btn.config(state="disabled")
        self.convert_folder_btn.config(state="disabled")
        self.convert_progress_var.set(0)
        
        # Use the configured output folder
        output_path = self._get_midi_output_path(audio_path)
        
        # Convert in background
        def on_complete(result):
            self.root.after(0, lambda: self._on_conversion_complete(result, load_after=False))
        
        converter.convert_async(audio_path, str(output_path), on_complete)
    
    def convert_and_load_midi(self):
        """Convert audio to MIDI and load it for playback"""
        audio_path = self.audio_file_var.get()
        if not audio_path:
            messagebox.showwarning("Warning", "Please select an audio file first")
            return
        
        converter = self._get_audio_converter()
        if converter is None:
            return
        
        if not converter.is_model_available():
            messagebox.showerror("Error", "AI model not found!\n\nThe model file should be at:\nmidimap/models/model.onnx")
            return
        
        # Disable buttons during conversion
        self.convert_btn.config(state="disabled")
        self.convert_and_load_btn.config(state="disabled")
        self.convert_folder_btn.config(state="disabled")
        self.convert_progress_var.set(0)
        
        # Use the configured output folder
        output_path = self._get_midi_output_path(audio_path)
        
        # Convert in background
        def on_complete(result):
            self.root.after(0, lambda: self._on_conversion_complete(result, load_after=True))
        
        converter.convert_async(audio_path, str(output_path), on_complete)
    
    def convert_folder_to_midi(self):
        """Convert all audio files in a folder to MIDI using parallel processing"""
        folder_path = self.audio_file_var.get()
        
        if not folder_path:
            messagebox.showwarning("Warning", "Please select a folder first using the 'Folder' button")
            return
        
        folder = Path(folder_path)
        if not folder.is_dir():
            messagebox.showwarning("Warning", "Please select a folder (not a file) using the 'Folder' button")
            return
        
        # Find all audio files
        audio_extensions = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma'}
        audio_files = [f for f in folder.iterdir() 
                      if f.is_file() and f.suffix.lower() in audio_extensions]
        
        if not audio_files:
            messagebox.showwarning("Warning", "No audio files found in the selected folder")
            return
        
        converter = self._get_audio_converter()
        if converter is None:
            return
        
        if not converter.is_model_available():
            messagebox.showerror("Error", "AI model not found!\n\nThe model file should be at:\nmidimap/models/model.onnx")
            return
        
        # Get number of workers
        num_workers = self.batch_workers_var.get()
        
        # Confirm batch conversion
        if not messagebox.askyesno("Parallel Batch Conversion", 
                                   f"Convert {len(audio_files)} audio files to MIDI?\n\n"
                                   f"Parallel workers: {num_workers}\n"
                                   f"Output folder: {self.midi_output_folder_var.get()}"):
            return
        
        # Prepare file pairs (input, output)
        file_pairs = []
        for audio_file in audio_files:
            output_path = self._get_midi_output_path(str(audio_file))
            file_pairs.append((str(audio_file), str(output_path)))
        
        # Setup batch state
        self._batch_converting = True
        self._batch_total = len(file_pairs)
        self._batch_completed = 0
        self._batch_success = 0
        self._batch_failed = 0
        
        # Disable buttons
        self.convert_btn.config(state="disabled")
        self.convert_and_load_btn.config(state="disabled")
        self.convert_folder_btn.config(state="disabled")
        self.batch_workers_spinbox.config(state="disabled")
        
        self.convert_status_label.config(
            text=f"Starting parallel conversion of {len(file_pairs)} files with {num_workers} workers...",
            foreground=self.COLORS['accent']
        )
        self.convert_progress_var.set(0)
        
        # Callbacks for parallel conversion
        def on_file_complete(filename: str, success: bool):
            self.root.after(0, lambda: self._on_parallel_file_complete(filename, success))
        
        def on_all_complete(success_count: int, failed_count: int):
            self.root.after(0, lambda: self._on_parallel_batch_complete(success_count, failed_count))
        
        def on_progress(completed: int, total: int):
            self.root.after(0, lambda: self._on_parallel_progress(completed, total))
        
        # Start parallel conversion
        converter.convert_batch_parallel(
            file_pairs=file_pairs,
            max_workers=num_workers,
            on_file_complete=on_file_complete,
            on_all_complete=on_all_complete,
            on_progress=on_progress
        )
    
    def _on_parallel_file_complete(self, filename: str, success: bool):
        """Handle completion of one file in parallel batch"""
        if success:
            self._batch_success += 1
        else:
            self._batch_failed += 1
        self._batch_completed += 1
        
        self.convert_status_label.config(
            text=f"[{self._batch_completed}/{self._batch_total}] {'Done' if success else 'Failed'}: {filename}",
            foreground=self.COLORS['success'] if success else self.COLORS['error']
        )
    
    def _on_parallel_progress(self, completed: int, total: int):
        """Update progress bar during parallel conversion"""
        progress = (completed / total) * 100
        self.convert_progress_var.set(progress)
    
    def _on_parallel_batch_complete(self, success_count: int, failed_count: int):
        """Handle parallel batch conversion completion"""
        self._batch_converting = False
        
        # Re-enable buttons
        self.convert_btn.config(state="normal")
        self.convert_and_load_btn.config(state="normal")
        self.convert_folder_btn.config(state="normal")
        self.batch_workers_spinbox.config(state="normal")
        self.convert_progress_var.set(100)
        
        total = success_count + failed_count
        self.convert_status_label.config(
            text=f"Batch complete: {success_count}/{total} converted successfully",
            foreground=self.COLORS['success'] if failed_count == 0 else self.COLORS['warning']
        )
        
        messagebox.showinfo("Parallel Batch Conversion Complete", 
                           f"Converted {success_count} of {total} files\n"
                           f"Success: {success_count}\n"
                           f"Failed: {failed_count}\n\n"
                           f"Output folder: {self.midi_output_folder_var.get()}")
    
    def _on_conversion_complete(self, result: Optional[str], load_after: bool):
        """Handle conversion completion"""
        self.convert_btn.config(state="normal")
        self.convert_and_load_btn.config(state="normal")
        self.convert_folder_btn.config(state="normal")
        self.convert_progress_var.set(100 if result else 0)
        
        if result:
            self.convert_status_label.config(text=f"Conversion complete: {Path(result).name}", foreground=self.COLORS['success'])
            if load_after:
                # Load the converted MIDI file
                self.load_midi_file(result)
                messagebox.showinfo("Success", f"Audio converted and loaded!\n\nMIDI saved to:\n{result}")
        else:
            self.convert_status_label.config(text="Conversion failed - see error below", foreground=self.COLORS['error'])
            # Show error details
            error_msg = "Conversion failed!\n\n"
            if self.audio_converter and self.audio_converter.last_error:
                error_msg += self.audio_converter.last_error
            else:
                error_msg += "Check the console for details.\n\n"
                error_msg += "Common issues:\n"
                error_msg += "- Missing ffmpeg (needed for MP3/other formats)\n"
                error_msg += "- Missing dependencies (librosa, onnxruntime)\n"
                error_msg += "- Corrupted or unsupported audio file"
            messagebox.showerror("Conversion Failed", error_msg)
    
    def _on_converter_log(self, message: str):
        """Handle log messages from converter"""
        # Print to console for debugging
        print(f"[AudioConverter] {message}")
        
        def update():
            # Color code based on message type
            if message.startswith("ERROR"):
                color = self.COLORS['error']
            elif message.startswith("WARNING"):
                color = self.COLORS['warning']
            else:
                color = self.COLORS['accent']
            self.convert_status_label.config(text=message, foreground=color)
        self.root.after(0, update)
    
    def _on_converter_progress(self, action: str, value):
        """Handle progress updates from converter"""
        def update():
            if action == 'value':
                # Convert segment progress to percentage
                if hasattr(self, '_convert_max') and self._convert_max > 0:
                    pct = (value / self._convert_max) * 100
                    self.convert_progress_var.set(pct)
            elif action == 'max':
                self._convert_max = value
            elif action == 'visible':
                pass  # Progress bar is always visible
        self.root.after(0, update)
    
    # YouTube to MP3 Converter Methods
    def _get_youtube_converter(self):
        """Lazy-load the YouTube converter"""
        if self.youtube_converter is None:
            try:
                from src.converters.youtube import YouTubeConverter
                downloads_dir = Path(__file__).parent / "downloads"
                self.youtube_converter = YouTubeConverter(str(downloads_dir))
                self.youtube_converter.set_log_callback(self._on_youtube_log)
                self.youtube_converter.set_progress_callback(self._on_youtube_progress)
                
                # Check if yt-dlp is available
                if not self.youtube_converter.is_available():
                    messagebox.showerror("Missing Dependency",
                        "yt-dlp is required for YouTube downloads.\n\n"
                        "Install it with:\npip install yt-dlp")
                    return None
                
                # Check if ffmpeg is available
                if not self.youtube_converter.is_ffmpeg_available():
                    messagebox.showerror("Missing Dependency",
                        "ffmpeg is required for converting YouTube videos to MP3.\n\n"
                        "Download from: https://ffmpeg.org/download.html\n\n"
                        "Or install via winget:\nwinget install ffmpeg")
                    return None
                    
            except ImportError as e:
                import traceback
                traceback.print_exc()
                messagebox.showerror("Error",
                    f"YouTube converter not available: {e}\n\n"
                    f"Install yt-dlp with:\npip install yt-dlp")
                return None
        return self.youtube_converter
    
    def download_youtube_mp3(self):
        """Download YouTube video as MP3"""
        url = self.youtube_url_var.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a YouTube URL")
            return
        
        converter = self._get_youtube_converter()
        if converter is None:
            return
        
        # Validate URL
        video_id = converter.extract_video_id(url)
        if not video_id:
            messagebox.showerror("Error", "Invalid YouTube URL.\n\nSupported formats:\n- youtube.com/watch?v=...\n- youtu.be/...\n- youtube.com/shorts/...")
            return
        
        # Disable buttons
        self.yt_download_btn.config(state="disabled")
        self.yt_convert_btn.config(state="disabled")
        self.yt_progress_var.set(0)
        self.yt_status_label.config(text="Starting download...", foreground=self.COLORS['accent'])
        
        # Download in background
        def on_complete(result):
            self.root.after(0, lambda: self._on_youtube_complete(result, convert_after=False))
        
        converter.convert_async(url, callback=on_complete)
    
    def download_and_convert_youtube(self):
        """Download YouTube video as MP3 and convert to MIDI"""
        url = self.youtube_url_var.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please enter a YouTube URL")
            return
        
        converter = self._get_youtube_converter()
        if converter is None:
            return
        
        # Validate URL
        video_id = converter.extract_video_id(url)
        if not video_id:
            messagebox.showerror("Error", "Invalid YouTube URL.\n\nSupported formats:\n- youtube.com/watch?v=...\n- youtu.be/...\n- youtube.com/shorts/...")
            return
        
        # Disable buttons
        self.yt_download_btn.config(state="disabled")
        self.yt_convert_btn.config(state="disabled")
        self.yt_progress_var.set(0)
        self.yt_status_label.config(text="Starting download...", foreground=self.COLORS['accent'])
        
        # Download in background
        def on_complete(result):
            self.root.after(0, lambda: self._on_youtube_complete(result, convert_after=True))
        
        converter.convert_async(url, callback=on_complete)
    
    def _on_youtube_complete(self, result: Optional[str], convert_after: bool):
        """Handle YouTube download completion"""
        self.yt_download_btn.config(state="normal")
        self.yt_convert_btn.config(state="normal")
        
        if result:
            self.yt_progress_var.set(100)
            self.yt_status_label.config(text=f"Downloaded: {Path(result).name}", foreground=self.COLORS['success'])
            
            if convert_after:
                # Set the audio file and trigger conversion
                self.audio_file_var.set(result)
                self.convert_status_label.config(text=f"Ready to convert: {Path(result).name}", foreground=self.COLORS['text'])
                messagebox.showinfo("Download Complete", 
                    f"MP3 downloaded successfully!\n\n{result}\n\nClick 'Convert & Load' to convert to MIDI.")
            else:
                messagebox.showinfo("Download Complete", f"MP3 downloaded:\n\n{result}")
        else:
            self.yt_progress_var.set(0)
            self.yt_status_label.config(text="Download failed - see console for details", foreground=self.COLORS['error'])
            messagebox.showerror("Download Failed", 
                "Failed to download YouTube video.\n\n"
                "Common issues:\n"
                "- Invalid or private video\n"
                "- Video too long (max 30 mins)\n"
                "- Network issues\n\n"
                "Check the console for details.")
    
    def _on_youtube_log(self, message: str, level: str):
        """Handle log messages from YouTube converter"""
        print(f"[YouTube] [{level.upper()}] {message}")
        
        def update():
            color = self.COLORS['error'] if level == "error" else self.COLORS['warning'] if level == "warning" else self.COLORS['accent']
            self.yt_status_label.config(text=message, foreground=color)
        self.root.after(0, update)
    
    def _on_youtube_progress(self, status: str, percent: float):
        """Handle progress updates from YouTube converter"""
        def update():
            self.yt_progress_var.set(percent)
            self.yt_status_label.config(text=status, foreground=self.COLORS['accent'])
        self.root.after(0, update)
    
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        # Unbind mousewheel to prevent errors during shutdown
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        # Stop MIDI file player
        if hasattr(self, 'midi_player'):
            self.midi_player.stop()
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
