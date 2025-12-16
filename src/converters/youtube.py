"""
YouTube to MP3 Converter module.
Uses yt-dlp for reliable YouTube audio extraction.
"""

import os
import re
import threading
from pathlib import Path
from typing import Callable, Optional


class YouTubeConverter:
    """Convert YouTube videos to MP3 audio files."""
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(output_dir) if output_dir else Path.cwd() / "downloads"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._progress_callback: Optional[Callable[[str, float], None]] = None
        self._log_callback: Optional[Callable[[str, str], None]] = None
        self._cancel_flag = False
        
    def set_progress_callback(self, callback: Callable[[str, float], None]):
        """Set callback for progress updates."""
        self._progress_callback = callback
        
    def set_log_callback(self, callback: Callable[[str, str], None]):
        """Set callback for log messages."""
        self._log_callback = callback
        
    def _log(self, message: str, level: str = "info"):
        """Log a message."""
        if self._log_callback:
            self._log_callback(message, level)
        print(f"[YouTube] [{level.upper()}] {message}")
        
    def _update_progress(self, status: str, percent: float):
        """Update progress."""
        if self._progress_callback:
            self._progress_callback(status, percent)
            
    def cancel(self):
        """Cancel the current download."""
        self._cancel_flag = True
        
    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats."""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
        
    def is_available(self) -> bool:
        """Check if yt-dlp is available."""
        try:
            import yt_dlp
            return True
        except ImportError:
            return False
    
    def _get_ffmpeg_path(self) -> Optional[str]:
        """Get path to ffmpeg executable."""
        import subprocess
        from utils.resources import get_ffmpeg_path
        
        local_ffmpeg = get_ffmpeg_path()
        if local_ffmpeg.exists():
            return str(local_ffmpeg.parent)
        
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                return None
        except (FileNotFoundError, Exception):
            pass
        
        return None
    
    def is_ffmpeg_available(self) -> bool:
        """Check if ffmpeg is available."""
        import subprocess
        from utils.resources import get_ffmpeg_path
        
        local_ffmpeg = get_ffmpeg_path()
        if local_ffmpeg.exists():
            return True
        
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False
            
    def convert(self, url: str, filename: Optional[str] = None) -> Optional[str]:
        """Convert YouTube video to MP3."""
        self._cancel_flag = False
        
        if not self.is_available():
            self._log("yt-dlp not installed. Run: pip install yt-dlp", "error")
            return None
            
        import yt_dlp
        
        video_id = self.extract_video_id(url)
        if not video_id:
            self._log(f"Invalid YouTube URL: {url}", "error")
            return None
            
        self._log(f"Processing video ID: {video_id}", "info")
        self._update_progress("Initializing...", 0)
        
        full_url = f"https://www.youtube.com/watch?v={video_id}"
        
        if filename:
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            output_template = str(self.output_dir / f"{filename}.%(ext)s")
        else:
            output_template = str(self.output_dir / "%(title)s.%(ext)s")
            
        def progress_hook(d):
            if self._cancel_flag:
                raise Exception("Download cancelled")
                
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = (downloaded / total) * 100
                    speed = d.get('speed', 0)
                    speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "..."
                    self._update_progress(f"Downloading: {speed_str}", percent * 0.7)
            elif d['status'] == 'finished':
                self._update_progress("Converting to MP3...", 75)
                
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        ffmpeg_path = self._get_ffmpeg_path()
        if ffmpeg_path:
            ydl_opts['ffmpeg_location'] = ffmpeg_path
        
        try:
            self._update_progress("Fetching video info...", 5)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._log("Extracting video information...", "info")
                info = ydl.extract_info(full_url, download=False)
                
                if self._cancel_flag:
                    self._log("Cancelled", "warning")
                    return None
                    
                title = info.get('title', video_id)
                duration = info.get('duration', 0)
                
                self._log(f"Title: {title}", "info")
                self._log(f"Duration: {duration // 60}:{duration % 60:02d}", "info")
                
                if duration > 1800:
                    self._log("Video too long (max 30 minutes)", "error")
                    return None
                    
                self._update_progress("Starting download...", 10)
                
                self._log("Downloading and converting...", "info")
                ydl.download([full_url])
                
            self._update_progress("Finalizing...", 95)
            
            if filename:
                expected_path = self.output_dir / f"{filename}.mp3"
            else:
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
                expected_path = self.output_dir / f"{safe_title}.mp3"
                
            if not expected_path.exists():
                mp3_files = list(self.output_dir.glob("*.mp3"))
                if mp3_files:
                    expected_path = max(mp3_files, key=lambda p: p.stat().st_mtime)
                    
            if expected_path.exists():
                self._update_progress("Complete!", 100)
                self._log(f"Saved to: {expected_path}", "info")
                return str(expected_path)
            else:
                self._log("Output file not found after conversion", "error")
                return None
                
        except Exception as e:
            if "cancelled" in str(e).lower():
                self._log("Download cancelled", "warning")
            else:
                self._log(f"Conversion failed: {e}", "error")
            return None
            
    def convert_async(self, url: str, filename: Optional[str] = None,
                      callback: Optional[Callable[[Optional[str]], None]] = None):
        """Convert YouTube video to MP3 asynchronously."""
        def run():
            result = self.convert(url, filename)
            if callback:
                callback(result)
                
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread





