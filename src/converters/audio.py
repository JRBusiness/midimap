"""
Audio to MIDI Converter.
Converts audio files (mp3, wav, etc.) to MIDI files using AI transcription.
"""

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Callable, List, Tuple

import numpy as np


class AudioToMidiConverter:
    
    def __init__(self):
        self.model = None
        self.transcriber = None
        self.model_loaded = False
        self.converting = False
        self.progress_callback: Optional[Callable] = None
        self.log_callback: Optional[Callable] = None
        self._model_path = Path(__file__).parent.parent.parent / "models" / "model.onnx"
        self.last_error: Optional[str] = None
    
    def is_model_available(self) -> bool:
        """Check if the AI model file exists."""
        return self._model_path.exists()
    
    def check_dependencies(self) -> tuple:
        """Check if all required dependencies are installed."""
        missing = []
        
        try:
            import librosa
        except ImportError:
            missing.append("librosa")
        
        try:
            import onnxruntime
        except ImportError:
            missing.append("onnxruntime")
        
        try:
            import mido
        except ImportError:
            missing.append("mido")
        
        return len(missing) == 0, missing
    
    def load_model(self) -> bool:
        """Load the ONNX model for audio transcription."""
        if self.model_loaded:
            return True
        
        deps_ok, missing = self.check_dependencies()
        if not deps_ok:
            self._log(f"ERROR: Missing dependencies: {', '.join(missing)}")
            self._log(f"Install with: pip install {' '.join(missing)}")
            return False
        
        if not self.is_model_available():
            self._log(f"ERROR: Model not found at {self._model_path}")
            return False
        
        try:
            self._log("Loading AI model...")
            
            try:
                import onnxruntime as ort
                providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
                self.model = ort.InferenceSession(str(self._model_path), providers=providers)
                self._log("Model loaded with DirectML (GPU)")
            except Exception as e:
                self._log(f"DirectML not available: {e}")
                import onnxruntime as ort
                self.model = ort.InferenceSession(
                    str(self._model_path), providers=['CPUExecutionProvider']
                )
                self._log("Model loaded with CPU")
            
            self._log("Initializing transcriber...")
            from src.converters.inference import PianoConverter
            self.transcriber = PianoConverter(model=self.model)
            
            self.model_loaded = True
            self._log("Model ready for transcription")
            return True
            
        except Exception as e:
            error_msg = f"Failed to load model: {e}\n{traceback.format_exc()}"
            self._log(error_msg)
            self.last_error = error_msg
            return False
    
    def convert_audio_to_midi(self, audio_path: str, 
                              output_midi_path: Optional[str] = None) -> Optional[str]:
        """Convert an audio file to MIDI."""
        self.last_error = None
        
        try:
            if not self.model_loaded:
                self._log("Loading model...")
                if not self.load_model():
                    self._log("ERROR: Model failed to load")
                    return None
            
            audio_path = Path(audio_path)
            if not audio_path.exists():
                self._log(f"ERROR: Audio file not found: {audio_path}")
                return None
            
            if output_midi_path is None:
                output_midi_path = audio_path.with_suffix('.mid')
            else:
                output_midi_path = Path(output_midi_path)
            
            self.converting = True
            self._log(f"Converting: {audio_path.name}")
            
            self._log("Loading audio file...")
            audio = self._load_audio(str(audio_path))
            
            if audio is None:
                self._log("ERROR: Failed to load audio file - check if ffmpeg is installed")
                self.converting = False
                return None
            
            duration = len(audio) / 16000
            self._log(f"Audio loaded: {duration:.1f} seconds ({len(audio)} samples)")
            
            if duration < 1:
                self._log("ERROR: Audio too short (less than 1 second)")
                self.converting = False
                return None
            
            self._log("Transcribing audio to MIDI (this may take a while)...")
            result = self.transcriber.transcribe(
                audio=audio,
                midi_path=str(output_midi_path),
                setProgressBarValue=self._set_progress,
                setProgressBarVisibility=self._set_progress_visible,
                setProgressBarFullValue=self._set_progress_max,
                logUpdate=self._log
            )
            
            notes_count = len(result.get('est_note_events', []))
            self._log(f"Conversion complete! Notes found: {notes_count}")
            
            if notes_count == 0:
                self._log("WARNING: No notes detected - audio may not contain piano music")
            
            self._log(f"Saved to: {output_midi_path}")
            
            self.converting = False
            return str(output_midi_path)
            
        except Exception as e:
            error_msg = f"Conversion error: {e}\n{traceback.format_exc()}"
            self._log(error_msg)
            self.last_error = error_msg
            self.converting = False
            return None
    
    def convert_async(self, audio_path: str, output_midi_path: Optional[str] = None,
                      on_complete: Optional[Callable] = None):
        """Convert audio to MIDI in a background thread."""
        def _convert():
            try:
                result = self.convert_audio_to_midi(audio_path, output_midi_path)
                if on_complete:
                    on_complete(result)
            except Exception as e:
                error_msg = f"Async conversion error: {e}\n{traceback.format_exc()}"
                self._log(error_msg)
                self.last_error = error_msg
                if on_complete:
                    on_complete(None)
        
        thread = threading.Thread(target=_convert, daemon=True)
        thread.start()
        return thread
    
    def convert_batch_parallel(
        self, 
        file_pairs: List[Tuple[str, str]], 
        max_workers: int = 4,
        on_file_complete: Optional[Callable[[str, bool], None]] = None,
        on_all_complete: Optional[Callable[[int, int], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None
    ):
        """
        Convert multiple audio files to MIDI in parallel using thread pool.
        
        Args:
            file_pairs: List of (audio_path, output_midi_path) tuples
            max_workers: Maximum number of parallel conversions
            on_file_complete: Callback(filename, success) for each file
            on_all_complete: Callback(success_count, failed_count) when all done
            on_progress: Callback(completed, total) for progress updates
        """
        def _batch_convert():
            # Pre-load model before starting parallel conversions
            if not self.model_loaded:
                self._log("Loading model for batch conversion...")
                if not self.load_model():
                    self._log("ERROR: Failed to load model")
                    if on_all_complete:
                        on_all_complete(0, len(file_pairs))
                    return
            
            success_count = 0
            failed_count = 0
            completed = 0
            total = len(file_pairs)
            
            # Use lock for thread-safe counter updates
            lock = threading.Lock()
            
            def convert_one(audio_path: str, output_path: str) -> Tuple[str, bool]:
                """Convert a single file (runs in thread pool)."""
                try:
                    result = self._convert_single_threadsafe(audio_path, output_path)
                    return (audio_path, result is not None)
                except Exception as e:
                    self._log(f"Error converting {Path(audio_path).name}: {e}")
                    return (audio_path, False)
            
            self._log(f"Starting batch conversion of {total} files with {max_workers} workers...")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all conversion tasks
                futures = {
                    executor.submit(convert_one, audio_path, output_path): (audio_path, output_path)
                    for audio_path, output_path in file_pairs
                }
                
                # Process completed tasks as they finish
                for future in as_completed(futures):
                    audio_path, success = future.result()
                    filename = Path(audio_path).name
                    
                    with lock:
                        completed += 1
                        if success:
                            success_count += 1
                            self._log(f"[{completed}/{total}] Completed: {filename}")
                        else:
                            failed_count += 1
                            self._log(f"[{completed}/{total}] Failed: {filename}")
                    
                    if on_file_complete:
                        on_file_complete(filename, success)
                    
                    if on_progress:
                        on_progress(completed, total)
            
            self._log(f"Batch conversion complete: {success_count} succeeded, {failed_count} failed")
            
            if on_all_complete:
                on_all_complete(success_count, failed_count)
        
        # Run batch conversion in background thread
        thread = threading.Thread(target=_batch_convert, daemon=True)
        thread.start()
        return thread
    
    def _convert_single_threadsafe(self, audio_path: str, output_midi_path: str) -> Optional[str]:
        """Thread-safe single file conversion (model must be pre-loaded)."""
        try:
            audio_path = Path(audio_path)
            if not audio_path.exists():
                return None
            
            output_midi_path = Path(output_midi_path)
            
            # Load audio
            audio = self._load_audio(str(audio_path))
            if audio is None:
                return None
            
            duration = len(audio) / 16000
            if duration < 1:
                return None
            
            # Create a separate transcriber instance for thread safety
            from src.converters.inference import PianoConverter
            transcriber = PianoConverter(model=self.model)
            
            # Transcribe (no progress callbacks in parallel mode)
            result = transcriber.transcribe(
                audio=audio,
                midi_path=str(output_midi_path),
                setProgressBarValue=lambda x: None,
                setProgressBarVisibility=lambda x: None,
                setProgressBarFullValue=lambda x: None,
                logUpdate=lambda x: None  # Suppress per-file logs in parallel mode
            )
            
            return str(output_midi_path) if result else None
            
        except Exception as e:
            return None
    
    def _load_audio(self, path: str, sr: int = 16000) -> Optional[np.ndarray]:
        """Load audio file and resample to target sample rate."""
        self._log(f"Attempting to load: {path}")
        
        try:
            import librosa
            self._log("Using librosa to load audio...")
            audio, _ = librosa.load(path, sr=sr, mono=True)
            self._log(f"Loaded with librosa: {len(audio)} samples")
            return audio
        except Exception as e:
            self._log(f"librosa failed: {type(e).__name__}: {e}")
        
        try:
            self._log("Trying audioread fallback...")
            from utils.audio import load_audio
            audio, _ = load_audio(path, sr=sr, mono=True)
            self._log(f"Loaded with audioread: {len(audio)} samples")
            return audio
        except Exception as e:
            self._log(f"audioread failed: {type(e).__name__}: {e}")
        
        self._log("ERROR: Could not load audio file!")
        self._log("Possible solutions:")
        self._log("  1. Install ffmpeg: https://ffmpeg.org/download.html")
        self._log("  2. Make sure the audio file is not corrupted")
        self._log("  3. Try converting to WAV format first")
        return None
    
    def _log(self, message: str):
        """Send log message to callback."""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def _set_progress(self, value: int):
        """Update progress value."""
        if self.progress_callback:
            self.progress_callback('value', value)
    
    def _set_progress_max(self, max_value: int):
        """Set maximum progress value."""
        if self.progress_callback:
            self.progress_callback('max', max_value)
    
    def _set_progress_visible(self, visible: bool):
        """Set progress visibility."""
        if self.progress_callback:
            self.progress_callback('visible', visible)


# Singleton instance
_converter_instance: Optional[AudioToMidiConverter] = None

def get_converter() -> AudioToMidiConverter:
    """Get or create the audio converter instance."""
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = AudioToMidiConverter()
    return _converter_instance

