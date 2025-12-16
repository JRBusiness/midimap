"""
Resource path utilities for PyInstaller bundled applications.
Handles finding resources in both development and bundled (.exe) mode.
"""

import sys
from pathlib import Path


def get_base_path() -> Path:
    """
    Get the base path for resources.
    
    In development mode: returns the project root directory
    In bundled mode (.exe): returns the directory where resources are extracted
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as a bundled executable (PyInstaller)
        return Path(sys._MEIPASS)
    else:
        # Running in development mode
        return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to a resource file.
    
    Args:
        relative_path: Path relative to the project root (e.g., 'models/model.onnx')
    
    Returns:
        Absolute path to the resource
    """
    return get_base_path() / relative_path


def get_config_path() -> Path:
    """Get path to config.json file."""
    # Config should be writable, so in bundled mode use the exe directory
    if getattr(sys, 'frozen', False):
        # Use the directory containing the .exe for writable config
        return Path(sys.executable).parent / "config.json"
    return get_base_path() / "config.json"


def get_ffmpeg_path() -> Path:
    """Get path to ffmpeg.exe."""
    return get_resource_path("ffmpeg.exe")


def get_ffprobe_path() -> Path:
    """Get path to ffprobe.exe."""
    return get_resource_path("ffprobe.exe")


def get_model_path() -> Path:
    """Get path to the ONNX model."""
    return get_resource_path("models/model.onnx")


def is_bundled() -> bool:
    """Check if running as a bundled executable."""
    return getattr(sys, 'frozen', False)

