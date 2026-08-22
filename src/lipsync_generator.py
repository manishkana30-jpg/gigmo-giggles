"""Audio-reactive 2.5D animation generator for simulating lip-sync and character movement."""

import math
import wave
import struct
import subprocess
from pathlib import Path
from PIL import Image

from src.utils import check_ffmpeg_available, setup_logger

logger = setup_logger("LipsyncGenerator")


class LipsyncGenerator:
    """Generates 2.5D audio-reactive animation to simulate talking."""

    def __init__(self, fps: int = 24, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
        self.ffmpeg_available = check_ffmpeg_available()

    def _compute_audio_rms(self, audio_path: Path, fps: int) -> list[float]:
        """Read WAV file and compute RMS volume for each frame."""
        try:
            with wave.open(str(audio_path), "rb") as wf:
                sample_rate = wf.getframerate()
                num_frames = wf.getnframes()
                samples_per_video_frame = int(sample_rate / fps)
                
                # We assume 16-bit PCM mono or stereo.
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                
                if sampwidth != 2:
                    logger.warning(f"Unsupported sample width {sampwidth} in {audio_path}. Expected 2 (16-bit).")
                    return []

                raw_data = wf.readframes(num_frames)
                
            # Unpack 16-bit integers
            num_samples = len(raw_data) // 2
            samples = struct.unpack(f"<{num_samples}h", raw_data)
            
            # If stereo, take every 2nd sample to get left channel
            if channels == 2:
                samples = samples[0::2]
                
            rms_list = []
            for i in range(0, len(samples), samples_per_video_frame):
                chunk = samples[i:i + samples_per_video_frame]
                if not chunk:
                    break
                
                # Compute RMS (Root Mean Square)
                sum_sq = sum(float(s) * float(s) for s in chunk)
                rms = math.sqrt(sum_sq / len(chunk))
                
                # Normalize (max value for 16-bit signed is 32768)
                normalized = min(1.0, rms / 8000.0) 
                rms_list.append(normalized)
                
            return rms_list
            
        except Exception as e:
            logger.warning(f"Failed to compute audio RMS for {audio_path}: {e}")
            return []

    def generate_audioreactive_clip(
        self,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        duration_sec: float
    ) -> bool:
        """
        Create a video where the image 'bounces' or stretches based on audio volume.
        Pipes raw generated RGB frames directly to FFmpeg.
        """
        if not self.ffmpeg_available:
            return False
            
        if not image_path.exists():
            return False
            
        # Ensure we're reading a .wav file for volume analysis
        wav_path = audio_path
        if audio_path.suffix.lower() == ".mp3":
            wav_path = audio_path.with_suffix(".wav")
            if not wav_path.exists():
                return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Compute volume per frame
        volumes = self._compute_audio_rms(wav_path, self.fps)
        total_frames = int(duration_sec * self.fps)
        
        # Pad or truncate volumes to match duration
        if len(volumes) < total_frames:
            volumes.extend([0.0] * (total_frames - len(volumes)))
        else:
            volumes = volumes[:total_frames]

        try:
            # 2. Open base image
            base_img = Image.open(image_path).convert("RGB")
            if base_img.size != (self.width, self.height):
                base_img = base_img.resize((self.width, self.height), Image.LANCZOS)
                
            # 3. Setup FFmpeg subprocess to receive raw frames via stdin
            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{self.width}x{self.height}",
                "-pix_fmt", "rgb24",
                "-r", str(self.fps),
                "-i", "-",          # Input from stdin
                "-i", str(audio_path), # Audio input
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(output_path)
            ]
            
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 4. Generate and pipe frames
            for frame_idx, vol in enumerate(volumes):
                # Smooth the volume slightly (moving average with previous frame)
                if frame_idx > 0:
                    vol = (vol + volumes[frame_idx - 1]) / 2.0
                    
                # Create bouncing / squashing effect based on volume
                # If volume is high, the character stretches vertically slightly (simulating talking/energy)
                # Max stretch is 5% vertically
                stretch_factor = 1.0 + (vol * 0.05)
                
                # Calculate new dimensions
                new_h = int(self.height * stretch_factor)
                
                # Resize image
                frame_img = base_img.resize((self.width, new_h), Image.BILINEAR)
                
                # Crop back to original size (anchor bottom, so the top "bounces" up)
                crop_y = new_h - self.height
                frame_img = frame_img.crop((0, crop_y, self.width, new_h))
                
                # Write raw RGB bytes to ffmpeg
                process.stdin.write(frame_img.tobytes())
                
            process.stdin.close()
            process.wait(timeout=120)
            
            success = process.returncode == 0 and output_path.exists()
            if success:
                logger.info(f"Generated 2.5D audio-reactive clip: {output_path.name}")
            else:
                logger.warning(f"Failed to generate audio-reactive clip: FFmpeg exit code {process.returncode}")
                
            return success
            
        except Exception as e:
            logger.warning(f"Error during audio-reactive generation: {e}")
            return False
