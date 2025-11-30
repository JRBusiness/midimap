#!/usr/bin/env python3
"""
Cross-platform keyboard input backend
Supports Windows, macOS, and Linux
"""

import platform
import subprocess
import sys
from typing import Optional

SYSTEM = platform.system().lower()
IS_WINDOWS = SYSTEM == 'windows'
IS_MAC = SYSTEM == 'darwin'
IS_LINUX = SYSTEM == 'linux'


class PlatformKeyboard:
    """Cross-platform keyboard input handler"""
    
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
        """Press a key"""
        self.impl.press_key(key)
    
    def release_key(self, key: str):
        """Release a key"""
        self.impl.release_key(key)
    
    def press_combination(self, modifiers: list, key: Optional[str] = None):
        """Press a key combination"""
        self.impl.press_combination(modifiers, key)


class _WindowsKeyboard:
    """Windows implementation using SendInput API"""
    
    def __init__(self):
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:
            raise RuntimeError("ctypes module not available (should be built-in)")
        
        self.ctypes = ctypes
        self.wintypes = wintypes
        
        # Windows constants
        self.KEYEVENTF_KEYUP = 0x0002
        self.INPUT_KEYBOARD = 1
        
        # Virtual key codes
        self.VK_CODE = {
            'backspace': 0x08, 'tab': 0x09, 'enter': 0x0D, 'shift': 0x10,
            'ctrl': 0x11, 'alt': 0x12, 'pause': 0x13, 'esc': 0x1B,
            'space': 0x20, 'end': 0x23, 'home': 0x24, 'left': 0x25,
            'up': 0x26, 'right': 0x27, 'down': 0x28, 'delete': 0x2E,
            'insert': 0x2D, 'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
            'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77, 'f9': 0x78,
            'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
            'page_up': 0x21, 'page_down': 0x22,
        }
        
        # Setup Windows structures
        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
        
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ULONG_PTR))
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
        
        # Get Windows API functions
        user32 = ctypes.windll.user32
        self.MapVirtualKeyW = user32.MapVirtualKeyW
        self.SendInput = user32.SendInput
        self.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        self.SendInput.restype = ctypes.c_uint
        
        self.VkKeyScanW = user32.VkKeyScanW
        self.VkKeyScanW.argtypes = [ctypes.c_wchar]
        self.VkKeyScanW.restype = wintypes.SHORT
    
    def _get_vk_code(self, key: str) -> int:
        """Get virtual key code for a key"""
        if not key:
            return 0
        
        key_lower = key.lower()
        
        if key_lower in self.VK_CODE:
            return self.VK_CODE[key_lower]
        
        if len(key) == 1:
            char = key.upper() if key.islower() else key
            try:
                vk_scan = self.VkKeyScanW(char)
                vk_code = vk_scan & 0xFF
                if vk_code != 0xFF and vk_code != 0:
                    return vk_code
            except Exception as e:
                print(f"Error getting VK code for '{key}': {e}")
                return 0
        
        return 0
    
    def _send_key_event(self, vk_code: int, key_up: bool = False):
        """Send a single key event using SendInput"""
        flags = self.KEYEVENTF_KEYUP if key_up else 0
        
        scan_code = self.MapVirtualKeyW(vk_code, 0)
        extra = self.ctypes.c_ulonglong(0) if self.ctypes.sizeof(self.ctypes.c_void_p) == 8 else self.ctypes.c_ulong(0)
        
        ki = self.KEYBDINPUT(
            wVk=self.ctypes.c_ushort(vk_code),
            wScan=self.ctypes.c_ushort(scan_code),
            dwFlags=self.ctypes.c_ulong(flags),
            time=self.ctypes.c_ulong(0),
            dwExtraInfo=self.ctypes.pointer(extra)
        )
        
        union = self.INPUT_UNION(ki=ki)
        x = self.INPUT(
            type=self.ctypes.c_ulong(self.INPUT_KEYBOARD),
            union=union
        )
        
        is_64bit = self.ctypes.sizeof(self.ctypes.c_void_p) == 8
        expected_size = 40 if is_64bit else 28
        
        result = self.SendInput(1, self.ctypes.byref(x), expected_size)
        return result == 1
    
    def press_key(self, key: str):
        """Press a key"""
        vk_code = self._get_vk_code(key)
        if vk_code:
            self._send_key_event(vk_code, key_up=False)
    
    def release_key(self, key: str):
        """Release a key"""
        vk_code = self._get_vk_code(key)
        if vk_code:
            self._send_key_event(vk_code, key_up=True)
    
    def press_combination(self, modifiers: list, key: Optional[str] = None):
        """Press a key combination"""
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
    """macOS implementation using AppleScript"""
    
    # macOS key codes (CGKeyCode)
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
        # Try to use pynput for better reliability
        try:
            from pynput.keyboard import Key, Controller
            self.use_pynput = True
            self.keyboard = Controller()
            self.Key = Key
        except ImportError:
            self.use_pynput = False
            print("Warning: pynput not available, using AppleScript (less reliable)")
    
    def _get_key_name(self, key: str) -> Optional[str]:
        """Convert key string to pynput Key or character"""
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
        """Send key event using AppleScript"""
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
        """Press a key"""
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
        """Release a key"""
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
        """Press a key combination"""
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
            # Fallback to individual key presses
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
    """Linux implementation using xdotool or uinput"""
    
    def __init__(self):
        # Try xdotool first (easier, no root required)
        self.use_xdotool = self._check_command('xdotool')
        
        if not self.use_xdotool:
            # Try pynput as fallback
            try:
                from pynput.keyboard import Key, Controller
                self.use_pynput = True
                self.keyboard = Controller()
                self.Key = Key
                print("Warning: xdotool not found, using pynput (may require X11)")
            except ImportError:
                raise RuntimeError("Linux requires either 'xdotool' (install: sudo apt install xdotool) or 'pynput'")
    
    def _check_command(self, cmd: str) -> bool:
        """Check if a command is available"""
        try:
            subprocess.run(['which', cmd], check=True, capture_output=True)
            return True
        except:
            return False
    
    def _xdotool_key(self, key: str, press: bool = True):
        """Send key using xdotool"""
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
        """Convert key string to pynput Key or character"""
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
        """Press a key"""
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
        """Release a key"""
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
        """Press a key combination"""
        import time
        if self.use_xdotool:
            mod_str = '+'.join(modifiers)
            if key:
                try:
                    subprocess.run(['xdotool', 'key', f'{mod_str}+{key}'], check=True, capture_output=True)
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

