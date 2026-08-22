"""Utility helpers for Gigmo Giggles YouTube Automation."""

import os
import re
import json
import math
import struct
import wave
import shutil
import logging
from pathlib import Path
from typing import Any, Dict, Optional


def get_project_root() -> Path:
    """Return the root directory of the project."""
    return Path(__file__).resolve().parent.parent


def setup_logger(name: str = "GigmoGiggles", log_file: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """Configure and return a structured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler if specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    return logger


def load_json(filepath: Path) -> Any:
    """Load and parse a JSON file with UTF-8 encoding."""
    if not filepath.exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: Path, data: Any, indent: int = 2) -> None:
    """Save data as a formatted JSON file with UTF-8 encoding."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_text(filepath: Path) -> str:
    """Read a text file with UTF-8 encoding."""
    if not filepath.exists():
        raise FileNotFoundError(f"Text file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def save_text(filepath: Path, content: str) -> None:
    """Write string content to a text file with UTF-8 encoding."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(text: str) -> str:
    """Convert text into a URL and filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg executable is available on the system PATH."""
    return shutil.which("ffmpeg") is not None


def generate_simple_tone_wav(
    output_path: Path,
    duration_sec: float = 2.0,
    frequency: float = 440.0,
    sample_rate: int = 22050,
    volume: float = 0.5
) -> Path:
    """
    Generate a simple sine-wave WAV file using Python standard library.
    Acts as a zero-dependency fallback for audio generation and unit testing.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    
    with wave.open(str(output_path), "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        frames = bytearray()
        for i in range(num_samples):
            # Calculate sine wave value
            t = float(i) / sample_rate
            # Simple envelope fade-in/fade-out to prevent clicks
            fade_samples = int(sample_rate * 0.05)
            envelope = 1.0
            if i < fade_samples:
                envelope = i / fade_samples
            elif i > num_samples - fade_samples:
                envelope = (num_samples - i) / fade_samples
                
            sample = volume * envelope * math.sin(2.0 * math.pi * frequency * t)
            sample_val = int(sample * 32767.0)
            sample_val = max(-32768, min(32767, sample_val))
            frames.extend(struct.pack("<h", sample_val))
            
        wav_file.writeframes(frames)
        
    return output_path


def generate_melodic_chime_wav(
    output_path: Path,
    duration_sec: float = 3.0,
    chord_freqs: Optional[list] = None
) -> Path:
    """Generate a cheerful kids background music loop with melody, bass, and chimes."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 22050
    num_samples = int(duration_sec * sample_rate)

    # Musical notes (Hz) for a cheerful C Major / G Major progression
    melody_notes = [523.25, 587.33, 659.25, 698.46, 783.99, 659.25, 523.25, 783.99]  # C5 D5 E5 F5 G5 E5 C5 G5
    bass_notes = [130.81, 164.81, 146.83, 130.81, 196.00, 164.81, 146.83, 130.81]    # C3 E3 D3 C3 G3 E3 D3 C3
    chime_freqs = [1046.50, 1318.51, 1567.98]  # C6 E6 G6 high sparkle

    note_duration = max(0.4, duration_sec / len(melody_notes))  # Duration per note

    with wave.open(str(output_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / sample_rate

            # Determine current note index (loop through melody)
            note_idx = int(t / note_duration) % len(melody_notes)
            note_t = t - (int(t / note_duration) * note_duration)  # Time within current note

            val = 0.0

            # Melody: soft sine with envelope
            melody_freq = melody_notes[note_idx]
            melody_env = math.exp(-2.5 * note_t) * 0.20  # Pluck-like decay
            val += melody_env * math.sin(2.0 * math.pi * melody_freq * note_t)

            # Bass: low hum
            bass_freq = bass_notes[note_idx]
            bass_env = 0.12 * math.exp(-1.0 * note_t)
            val += bass_env * math.sin(2.0 * math.pi * bass_freq * note_t)

            # Chime sparkle: very subtle high notes every 2 beats
            if note_idx % 2 == 0:
                chime_idx = (note_idx // 2) % len(chime_freqs)
                chime_env = 0.06 * math.exp(-5.0 * note_t)
                val += chime_env * math.sin(2.0 * math.pi * chime_freqs[chime_idx] * note_t)

            # Gentle rhythm pulse (soft kick-like thump)
            kick_period = note_duration
            kick_t = t % kick_period
            if kick_t < 0.05:
                val += 0.08 * math.sin(2.0 * math.pi * 80 * kick_t) * math.exp(-40.0 * kick_t)

            # Master volume fade in/out
            if t < 1.0:
                val *= t  # Fade in over 1 second
            if t > duration_sec - 1.5:
                val *= max(0, (duration_sec - t) / 1.5)  # Fade out over 1.5 seconds

            sample_val = int(val * 32767.0)
            sample_val = max(-32768, min(32767, sample_val))
            frames.extend(struct.pack("<h", sample_val))

        wav_file.writeframes(frames)
    return output_path

