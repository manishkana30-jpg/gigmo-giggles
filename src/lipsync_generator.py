"""Hardened Audio-reactive 3D and 2.5D animation generator for simulating lip-sync and character movement."""

import os
import sys
import time
import math
import wave
import struct
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import check_ffmpeg_available, setup_logger

logger = setup_logger("LipsyncGenerator")


def retry(attempts=3, delay=1, backoff=2):
    """Custom retry decorator for handling transient subprocess spikes without external dependencies."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            curr_delay = delay
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
                    if attempt == attempts:
                        logger.error(f"Function {func.__name__} failed after {attempts} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempt} failed for {func.__name__}: {e}. Retrying in {curr_delay}s...")
                    time.sleep(curr_delay)
                    curr_delay *= backoff
            return None
        return wrapper
    return decorator


class LipsyncGenerator:
    """Generates 3D and 2.5D audio-reactive animation to simulate talking."""

    def __init__(self, fps: int = 24, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
        self.ffmpeg_available = check_ffmpeg_available()

    def resolve_rhubarb_binary(self) -> str:
        """Dynamically resolve the rhubarb binary, searching paths and directories if not on system PATH."""
        # 1. Check system PATH
        system_path = shutil.which("rhubarb")
        if system_path:
            return system_path

        # 2. Search root directory for compiled/extracted folder
        root_dir = Path(__file__).resolve().parent.parent
        logger.info(f"Rhubarb not found on PATH. Scanning root: {root_dir}")
        
        # Search recursively
        for p in root_dir.rglob("rhubarb"):
            if p.is_file() and os.access(p, os.X_OK):
                logger.info(f"Found executable Rhubarb at: {p}")
                return str(p)
            elif p.is_file() and (p.name == "rhubarb" or p.name == "rhubarb.exe"):
                # Try to make executable
                try:
                    p.chmod(0o755)
                    logger.info(f"Found and marked executable Rhubarb at: {p}")
                    return str(p)
                except Exception as e:
                    logger.warning(f"Failed to chmod executable: {e}")

        # 3. Last resort fallback
        return "rhubarb"

    def resample_audio_ffmpeg(self, input_path: Path, output_path: Path) -> bool:
        """Force resample input audio to exactly 44100 Hz WAV using FFmpeg."""
        if not self.ffmpeg_available:
            logger.error("FFmpeg not available; cannot resample audio.")
            return False

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-ar", "44100",
            "-ac", "1",  # Mono is preferred for Rhubarb processing
            str(output_path)
        ]
        
        try:
            logger.info(f"Resampling audio {input_path.name} to 44100 Hz...")
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            return res.returncode == 0 and output_path.exists()
        except Exception as e:
            logger.error(f"FFmpeg audio resampling failed: {e}")
            return False

    @retry(attempts=3, delay=2, backoff=2)
    def _run_rhubarb(self, rhubarb_path: str, audio_path: Path, json_path: Path) -> bool:
        """Execute Rhubarb with custom retry wrapper."""
        cmd = [
            rhubarb_path,
            "-f", "json",
            "-o", str(json_path),
            str(audio_path)
        ]
        logger.info(f"Running Rhubarb: {' '.join(cmd)}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if res.returncode != 0:
            err_msg = res.stderr.decode("utf-8", errors="ignore")
            raise subprocess.SubprocessError(f"Rhubarb exited with code {res.returncode}. Error: {err_msg}")
        return True

    @retry(attempts=3, delay=5, backoff=2)
    def _run_blender_render(self, audio_path: Path, json_path: Path, temp_video_path: Path) -> bool:
        """Execute Headless Blender render with custom retry wrapper."""
        animator_script = Path(__file__).resolve().parent / "blender_animator.py"
        if not animator_script.exists():
            raise FileNotFoundError(f"Blender animator script not found at {animator_script}")

        # Check if running on Linux and xvfb-run is available
        xvfb_bin = shutil.which("xvfb-run")
        
        cmd = [
            "blender", "-b", "-P", str(animator_script),
            "--",
            "--audio", str(audio_path),
            "--visemes", str(json_path),
            "--output", str(temp_video_path),
            "--fps", str(self.fps)
        ]
        
        if xvfb_bin:
            logger.info("xvfb-run detected. Running Blender inside virtual display...")
            cmd = [xvfb_bin, "--auto-servernum"] + cmd

        logger.info(f"Running Headless Blender Render: {' '.join(cmd)}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if res.returncode != 0:
            err_msg = res.stderr.decode("utf-8", errors="ignore")
            raise subprocess.SubprocessError(f"Blender exited with code {res.returncode}. Error: {err_msg}")
        return True

    def generate_3d_lipsync_clip(
        self,
        audio_path: Path,
        output_path: Path,
        duration_sec: float
    ) -> bool:
        """
        Generates a 3D animated lip-sync video clip using Blender and Rhubarb.
        Ensures atomicity with .lock files and intermediate temp file paths.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Define temporary/atomic paths
        lock_file = output_path.with_suffix(".lock")
        temp_video = output_path.with_suffix(".tmp.mp4")
        temp_audio = output_path.parent / f"{output_path.stem}_resampled.wav"
        temp_json = output_path.parent / f"{output_path.stem}_visemes.json"

        # If locked, wait or cleanup (idempotency safety check)
        if lock_file.exists():
            logger.warning(f"Lock file exists for {output_path.name}. Cleaning up stale lock.")
            try:
                lock_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Could not remove lock file: {e}")

        # Mark rendering in progress
        lock_file.touch()

        success = False
        try:
            # 1. Resolve Rhubarb Binary
            rhubarb_bin = self.resolve_rhubarb_binary()

            # 2. Resample Audio to 44100 Hz
            if not self.resample_audio_ffmpeg(audio_path, temp_audio):
                logger.error("Failed to resample audio. Using original audio file as fallback.")
                temp_audio = audio_path

            # 3. Generate Visemes JSON via Rhubarb
            logger.info("Generating visemes JSON using Rhubarb...")
            self._run_rhubarb(rhubarb_bin, temp_audio, temp_json)

            # 4. Render 3D Animation via Headless Blender
            logger.info("Rendering 3D scene in Blender...")
            self._run_blender_render(temp_audio, temp_json, temp_video)

            # 5. Atomic Rename (Finalize File Write)
            if temp_video.exists():
                if output_path.exists():
                    output_path.unlink()
                shutil.move(str(temp_video), str(output_path))
                success = True
                logger.info(f"Atomic Render Success: {output_path}")

        except Exception as e:
            logger.error(f"Failed to generate 3D lipsync clip for {output_path.name}: {e}")
            if temp_video.exists():
                try:
                    temp_video.unlink()
                except Exception:
                    pass
        finally:
            # Cleanup temporary intermediates
            for path in [temp_audio, temp_json, lock_file]:
                if path.exists():
                    try:
                        path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to clean up temporary file {path}: {e}")

        return success
