# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MidiMap
Generates a standalone .exe with all dependencies bundled
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files for various packages
datas = [
    ('config.json', '.'),
    ('ffmpeg.exe', '.'),
    ('ffprobe.exe', '.'),
    ('models/model.onnx', 'models'),
]

# Collect librosa data files (audio processing needs these)
datas += collect_data_files('librosa')

# Hidden imports for complex packages
hiddenimports = [
    'mido',
    'mido.backends',
    'mido.backends.rtmidi',
    'pynput',
    'pynput.keyboard',
    'pynput.keyboard._win32',
    'pynput._util',
    'pynput._util.win32',
    'librosa',
    'librosa.util',
    'librosa.filters',
    'librosa.feature',
    'librosa.onset',
    'librosa.beat',
    'librosa.core',
    'numpy',
    'numpy.core',
    'scipy',
    'scipy.signal',
    'scipy.fft',
    'soundfile',
    'audioread',
    'onnxruntime',
    'yt_dlp',
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    'tkinter.filedialog',
    'pooch',
    'soxr',
    'lazy_loader',
    'msgpack',
    'decorator',
    'joblib',
    'platformdirs',
    'packaging',
    'ctypes',
    'ctypes.wintypes',
]

# Collect all submodules for complex packages
hiddenimports += collect_submodules('librosa')
hiddenimports += collect_submodules('onnxruntime')
hiddenimports += collect_submodules('yt_dlp')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MidiMap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True if you want to see console output for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

