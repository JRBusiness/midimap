"""
Cross-platform keyboard input backend.
Supports Windows, macOS, and Linux.
"""

import platform
import subprocess
from typing import Optional

SYSTEM = platform.system().lower()
IS_WINDOWS = SYSTEM == 'windows'
IS_MAC = SYSTEM == 'darwin'
IS_LINUX = SYSTEM == 'linux'


class PlatformKeyboard:
    """Cross-platform keyboard input handler."""
    
    def __init__(self):
        if IS_WINDOWS:
            self.impl = _WindowsKeyboard()
        elif IS_MAC:
            self.impl = _MacKeyboard()
        elif IS_LINUX:
            self.impl = _LinuxKeyboard()
        else:
            raise RuntimeError(f"Unsupported platform: {SYSTEM}")
    
    def press_key(self, key: str):
        """Press a key."""
        self.impl.press_key(key)
    
    def release_key(self, key: str):
        """Release a key."""
        self.impl.release_key(key)
    
    def press_combination(self, modifiers: list, key: Optional[str] = None):
        """Press a key combination."""
        self.impl.press_combination(modifiers, key)


class _WindowsKeyboard:
    """Windows implementation using DirectInput with scan codes for game compatibility."""
    
    def __init__(self):
        import ctypes
        
        self.ctypes = ctypes
        
        self.KEYEVENTF_SCANCODE = 0x0008
        self.KEYEVENTF_KEYUP = 0x0002
        self.KEYEVENTF_EXTENDEDKEY = 0x0001
        self.INPUT_KEYBOARD = 1
        
        self.SCAN_CODES = {
            'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12, 'f': 0x21,
            'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24, 'k': 0x25, 'l': 0x26,
            'm': 0x32, 'n': 0x31, 'o': 0x18, 'p': 0x19, 'q': 0x10, 'r': 0x13,
            's': 0x1F, 't': 0x14, 'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D,
            'y': 0x15, 'z': 0x2C,
            '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
            '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
            'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E, 'f5': 0x3F,
            'f6': 0x40, 'f7': 0x41, 'f8': 0x42, 'f9': 0x43, 'f10': 0x44,
            'f11': 0x57, 'f12': 0x58,
            'esc': 0x01, 'tab': 0x0F, 'space': 0x39, 'enter': 0x1C,
            'backspace': 0x0E, 'shift': 0x2A, 'ctrl': 0x1D, 'alt': 0x38,
            'up': 0x48, 'down': 0x50, 'left': 0x4B, 'right': 0x4D,
            'insert': 0x52, 'delete': 0x53, 'home': 0x47, 'end': 0x4F,
            'page_up': 0x49, 'page_down': 0x51,
            '-': 0x0C, '=': 0x0D, '[': 0x1A, ']': 0x1B, '\\': 0x2B,
            ';': 0x27, "'": 0x28, '`': 0x29, ',': 0x33, '.': 0x34, '/': 0x35,
        }
        
        self.EXTENDED_KEYS = {
            'up', 'down', 'left', 'right', 'insert', 'delete', 
            'home', 'end', 'page_up', 'page_down'
        }
        
        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
        
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)
            ]
        
        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        
        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_ulong),
                ("union", INPUT_UNION)
            ]
        
        self.KEYBDINPUT = KEYBDINPUT
        self.INPUT_UNION = INPUT_UNION
        self.INPUT = INPUT
        
        user32 = ctypes.windll.user32
        self.SendInput = user32.SendInput
        self.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        self.SendInput.restype = ctypes.c_uint
        
    def _get_scan_code(self, key: str) -> tuple:
        """Get scan code and extended flag for a key."""
        if not key:
            return 0, False
        
        key_lower = key.lower()
        scan_code = self.SCAN_CODES.get(key_lower, 0)
        is_extended = key_lower in self.EXTENDED_KEYS
        
        return scan_code, is_extended
    
    def _send_key_event(self, scan_code: int, is_extended: bool, key_up: bool = False):
        """Send a key event using DirectInput scan codes."""
        flags = self.KEYEVENTF_SCANCODE
        if key_up:
            flags |= self.KEYEVENTF_KEYUP
        if is_extended:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        
        ki = self.KEYBDINPUT(
            wVk=0,
            wScan=self.ctypes.c_ushort(scan_code),
            dwFlags=self.ctypes.c_ulong(flags),
            time=0,
            dwExtraInfo=0
        )
        
        union = self.INPUT_UNION(ki=ki)
        x = self.INPUT(
            type=self.ctypes.c_ulong(self.INPUT_KEYBOARD),
            union=union
        )
        
        is_64bit = self.ctypes.sizeof(self.ctypes.c_void_p) == 8
        input_size = 40 if is_64bit else 28
        
        result = self.SendInput(1, self.ctypes.byref(x), input_size)
        return result == 1
    
    def press_key(self, key: str):
        """Press a key using DirectInput."""
        scan_code, is_extended = self._get_scan_code(key)
        if scan_code:
            self._send_key_event(scan_code, is_extended, key_up=False)
    
    def release_key(self, key: str):
        """Release a key using DirectInput."""
        scan_code, is_extended = self._get_scan_code(key)
        if scan_code:
            self._send_key_event(scan_code, is_extended, key_up=True)
    
    def press_combination(self, modifiers: list, key: Optional[str] = None):
        """Press a key combination using DirectInput."""
        import time
        for mod in modifiers:
            self.press_key(mod)
        if key:
            time.sleep(0.01)
            self.press_key(key)
            time.sleep(0.01)
            self.release_key(key)
        for mod in reversed(modifiers):
            self.release_key(mod)


class _MacKeyboard:
    """macOS implementation using pynput/AppleScript."""
    
    KEY_CODES = {
        'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14, 'f': 3, 'g': 5, 'h': 4,
        'i': 34, 'j': 38, 'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31,
        'p': 35, 'q': 12, 'r': 15, 's': 1, 't': 17, 'u': 32, 'v': 9,
        'w': 13, 'x': 7, 'y': 16, 'z': 6,
        'space': 49, 'enter': 36, 'tab': 48, 'esc': 53,
        'shift': 56, 'ctrl': 59, 'alt': 58, 'cmd': 55,
        'up': 126, 'down': 125, 'left': 123, 'right': 124,
        'f1': 122, 'f2': 120, 'f3': 99, 'f4': 118, 'f5': 96, 'f6': 97,
        'f7': 98, 'f8': 100, 'f9': 101, 'f10': 109, 'f11': 103, 'f12': 111,
        'backspace': 51, 'delete': 117, 'home': 115, 'end': 119,
        'page_up': 116, 'page_down': 121,
    }
    
    def __init__(self):
        try:
            from pynput.keyboard import Key, Controller
            self.use_pynput = True
            self.keyboard = Controller()
            self.Key = Key
        except ImportError:
            self.use_pynput = False
            print("Warning: pynput not available, using AppleScript (less reliable)")
    
    def _get_key_name(self, key: str) -> Optional[str]:
        """Convert key string to pynput Key or character."""
        if self.use_pynput:
            key_map = {
                'space': self.Key.space, 'enter': self.Key.enter, 'tab': self.Key.tab,
                'esc': self.Key.esc, 'shift': self.Key.shift, 'ctrl': self.Key.ctrl,
                'alt': self.Key.alt, 'up': self.Key.up, 'down': self.Key.down,
                'left': self.Key.left, 'right': self.Key.right,
                'f1': self.Key.f1, 'f2': self.Key.f2, 'f3': self.Key.f3, 'f4': self.Key.f4,
                'f5': self.Key.f5, 'f6': self.Key.f6, 'f7': self.Key.f7, 'f8': self.Key.f8,
                'f9': self.Key.f9, 'f10': self.Key.f10, 'f11': self.Key.f11, 'f12': self.Key.f12,
                'backspace': self.Key.backspace, 'delete': self.Key.delete,
                'home': self.Key.home, 'end': self.Key.end,
                'page_up': self.Key.page_up, 'page_down': self.Key.page_down,
            }
            key_lower = key.lower()
            if key_lower in key_map:
                return key_map[key_lower]
            elif len(key) == 1:
                return key
        return None
    
    def _send_applescript(self, key_code: int, key_down: bool):
        """Send key event using AppleScript."""
        action = "key down" if key_down else "key up"
        script = f'''
        tell application "System Events"
            {action} {key_code}
        end tell
        '''
        try:
            subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass
    
    def press_key(self, key: str):
        """Press a key."""
        if self.use_pynput:
            key_obj = self._get_key_name(key)
            if key_obj:
                try:
                    self.keyboard.press(key_obj)
                except:
                    if isinstance(key_obj, str):
                        self.keyboard.press(key_obj)
        else:
            key_lower = key.lower()
            if key_lower in self.KEY_CODES:
                self._send_applescript(self.KEY_CODES[key_lower], True)
    
    def release_key(self, key: str):
        """Release a key."""
        if self.use_pynput:
            key_obj = self._get_key_name(key)
            if key_obj:
                try:
                    self.keyboard.release(key_obj)
                except:
                    if isinstance(key_obj, str):
                        self.keyboard.release(key_obj)
        else:
            key_lower = key.lower()
            if key_lower in self.KEY_CODES:
                self._send_applescript(self.KEY_CODES[key_lower], False)
    
    def press_combination(self, modifiers: list, key: Optional[str] = None):
        """Press a key combination."""
        import time
        if self.use_pynput:
            mod_map = {
                'ctrl': self.Key.ctrl, 'shift': self.Key.shift, 'alt': self.Key.alt
            }
            mod_keys = [mod_map.get(m.lower()) for m in modifiers if m.lower() in mod_map]
            
            for mod in mod_keys:
                if mod:
                    self.keyboard.press(mod)
            
            if key:
                time.sleep(0.01)
                key_obj = self._get_key_name(key)
                if key_obj:
                    self.keyboard.press(key_obj)
                    time.sleep(0.01)
                    self.keyboard.release(key_obj)
            
            for mod in reversed(mod_keys):
                if mod:
                    self.keyboard.release(mod)
        else:
            for mod in modifiers:
                self.press_key(mod)
            if key:
                time.sleep(0.01)
                self.press_key(key)
                time.sleep(0.01)
                self.release_key(key)
            for mod in reversed(modifiers):
                self.release_key(mod)


class _LinuxKeyboard:
    """Linux implementation using xdotool or pynput."""
    
    def __init__(self):
        self.use_xdotool = self._check_command('xdotool')
        
        if not self.use_xdotool:
            try:
                from pynput.keyboard import Key, Controller
                self.use_pynput = True
                self.keyboard = Controller()
                self.Key = Key
                print("Warning: xdotool not found, using pynput (may require X11)")
            except ImportError:
                raise RuntimeError(
                    "Linux requires either 'xdotool' (install: sudo apt install xdotool) or 'pynput'"
                )
    
    def _check_command(self, cmd: str) -> bool:
        """Check if a command is available."""
        try:
            subprocess.run(['which', cmd], check=True, capture_output=True)
            return True
        except:
            return False
    
    def _xdotool_key(self, key: str, press: bool = True):
        """Send key using xdotool."""
        action = 'keydown' if press else 'keyup'
        key_map = {
            'ctrl': 'ctrl', 'shift': 'shift', 'alt': 'alt',
            'space': 'space', 'enter': 'Return', 'tab': 'Tab',
            'esc': 'Escape', 'up': 'Up', 'down': 'Down',
            'left': 'Left', 'right': 'Right',
            'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
            'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8',
            'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
            'backspace': 'BackSpace', 'delete': 'Delete',
            'home': 'Home', 'end': 'End',
            'page_up': 'Page_Up', 'page_down': 'Page_Down',
        }
        
        key_lower = key.lower()
        xdotool_key = key_map.get(key_lower, key)
        
        try:
            subprocess.run(['xdotool', action, xdotool_key], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass
    
    def _get_key_name(self, key: str):
        """Convert key string to pynput Key or character."""
        if hasattr(self, 'use_pynput') and self.use_pynput:
            key_map = {
                'space': self.Key.space, 'enter': self.Key.enter, 'tab': self.Key.tab,
                'esc': self.Key.esc, 'shift': self.Key.shift, 'ctrl': self.Key.ctrl,
                'alt': self.Key.alt, 'up': self.Key.up, 'down': self.Key.down,
                'left': self.Key.left, 'right': self.Key.right,
                'f1': self.Key.f1, 'f2': self.Key.f2, 'f3': self.Key.f3, 'f4': self.Key.f4,
                'f5': self.Key.f5, 'f6': self.Key.f6, 'f7': self.Key.f7, 'f8': self.Key.f8,
                'f9': self.Key.f9, 'f10': self.Key.f10, 'f11': self.Key.f11, 'f12': self.Key.f12,
                'backspace': self.Key.backspace, 'delete': self.Key.delete,
                'home': self.Key.home, 'end': self.Key.end,
                'page_up': self.Key.page_up, 'page_down': self.Key.page_down,
            }
            key_lower = key.lower()
            if key_lower in key_map:
                return key_map[key_lower]
            elif len(key) == 1:
                return key
        return None
    
    def press_key(self, key: str):
        """Press a key."""
        if self.use_xdotool:
            self._xdotool_key(key, press=True)
        elif hasattr(self, 'use_pynput') and self.use_pynput:
            key_obj = self._get_key_name(key)
            if key_obj:
                try:
                    self.keyboard.press(key_obj)
                except:
                    if isinstance(key_obj, str):
                        self.keyboard.press(key_obj)
    
    def release_key(self, key: str):
        """Release a key."""
        if self.use_xdotool:
            self._xdotool_key(key, press=False)
        elif hasattr(self, 'use_pynput') and self.use_pynput:
            key_obj = self._get_key_name(key)
            if key_obj:
                try:
                    self.keyboard.release(key_obj)
                except:
                    if isinstance(key_obj, str):
                        self.keyboard.release(key_obj)
    
    def press_combination(self, modifiers: list, key: Optional[str] = None):
        """Press a key combination."""
        import time
        if self.use_xdotool:
            mod_str = '+'.join(modifiers)
            if key:
                try:
                    subprocess.run(
                        ['xdotool', 'key', f'{mod_str}+{key}'], 
                        check=True, capture_output=True
                    )
                except:
                    pass
            else:
                for mod in modifiers:
                    self.press_key(mod)
        elif hasattr(self, 'use_pynput') and self.use_pynput:
            mod_map = {
                'ctrl': self.Key.ctrl, 'shift': self.Key.shift, 'alt': self.Key.alt
            }
            mod_keys = [mod_map.get(m.lower()) for m in modifiers if m.lower() in mod_map]
            
            for mod in mod_keys:
                if mod:
                    self.keyboard.press(mod)
            
            if key:
                time.sleep(0.01)
                key_obj = self._get_key_name(key)
                if key_obj:
                    self.keyboard.press(key_obj)
                    time.sleep(0.01)
                    self.keyboard.release(key_obj)
            
            for mod in reversed(mod_keys):
                if mod:
                    self.keyboard.release(mod)





