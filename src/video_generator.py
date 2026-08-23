"""Hardened Modular Video Generator with 2.5D Ken Burns animation and robust FFmpeg piping."""

import os
import sys
import time
import random
import shutil
import atexit
import uuid
import importlib.metadata
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import check_ffmpeg_available, save_json, save_text, setup_logger

logger = setup_logger("VideoGenerator")


# ── Randomised Ken Burns zoom/pan directions ────────────────────────────────
ZOOM_DIRECTIONS = [
    # Centre zoom-in
    "zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s=1920x1080:fps={fps}",
    # Top-left to centre
    "zoompan=z='min(zoom+0.0012,1.4)':x=0:y=0:d={d}:s=1920x1080:fps={fps}",
    # Top-right to centre
    "zoompan=z='min(zoom+0.0012,1.4)':x='iw-iw/zoom':y=0:d={d}:s=1920x1080:fps={fps}",
    # Bottom-left to centre
    "zoompan=z='min(zoom+0.0012,1.4)':x=0:y='ih-ih/zoom':d={d}:s=1920x1080:fps={fps}",
    # Bottom-centre push-in
    "zoompan=z='min(zoom+0.0012,1.4)':x='iw/2-(iw/zoom/2)':y='ih-ih/zoom':d={d}:s=1920x1080:fps={fps}",
]


class PipelineTempDir:
    """Strict Context Manager for managing and guaranteeing cleanup of pipeline temporary directories."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.path = base_dir / f"temp_run_{uuid.uuid4().hex}"
        self._cleaned = False

    def __enter__(self):
        # Clear base directory if it exists to purge any legacy leftovers
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        self.path.mkdir(parents=True, exist_ok=True)
        # Register atexit handler for crash protection
        atexit.register(self.cleanup)
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        if not self._cleaned:
            logger.info(f"PipelineTempDir: Cleaning up temporary files in {self.path}")
            shutil.rmtree(self.path, ignore_errors=True)
            self._cleaned = True
            try:
                atexit.unregister(self.cleanup)
            except Exception:
                pass


def cleanup_orphaned_resources(target_dirs: List[Path] = None):
    """Scan directories for files older than 1 hour matching pipeline patterns and purge them."""
    if not target_dirs:
        target_dirs = [Path("/tmp"), Path("./episodes"), Path(".")]
    
    current_time = time.time()
    one_hour_sec = 3600
    patterns = ["*.mp3", "*.wav", "*.png", "*.json", "*.lock", "*.tmp.mp4"]
    
    logger.info("SRE Purge: Scanning for orphaned temporary pipeline files older than 1 hour...")
    for directory in target_dirs:
        if not directory.exists():
            continue
        try:
            for pattern in patterns:
                for file_path in directory.rglob(pattern):
                    try:
                        if file_path.is_file() and (current_time - file_path.stat().st_mtime) > one_hour_sec:
                            logger.info(f"Purging orphaned file: {file_path}")
                            file_path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Failed to scan directory {directory}: {e}")


def validate_environment():
    """Pre-flight check to validate runner environment dependencies."""
    # 1. FFmpeg Validation & Install Attempt
    if not shutil.which("ffmpeg"):
        logger.warning("FFmpeg not found. Attempting emergency installation...")
        try:
            subprocess.run(["sudo", "apt-get", "update", "-y"], check=True, timeout=60)
            subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"], check=True, timeout=120)
        except Exception as e:
            logger.critical(f"FFmpeg not installed and auto-installation failed: {e}")
            raise SystemExit("Environment validation failed: FFmpeg missing.")

    # Check version
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        raise SystemExit("FFmpeg command failed execution.")

    # 2. Python Package Validation
    required_packages = {
        "pillow": "10.0.0",
    }
    for pkg, min_version in required_packages.items():
        try:
            ver = importlib.metadata.version(pkg)
            v_parts = [int(x) for x in ver.split(".")[:2]]
            m_parts = [int(x) for x in min_version.split(".")[:2]]
            if v_parts < m_parts:
                logger.warning(f"Package {pkg} version {ver} is lower than recommended {min_version}.")
        except importlib.metadata.PackageNotFoundError:
            logger.warning(f"Package {pkg} is not installed.")

    # 3. Disk Space Validation (1GB limit)
    try:
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024**3)
        logger.info(f"Pre-flight Check: Free disk space: {free_gb:.2f} GB")
        if free_gb < 1.0:
            logger.warning("Disk space low (< 1GB). Flushing temporary cache.")
            cleanup_orphaned_resources()
    except Exception as e:
        logger.warning(f"Disk check failed: {e}")


def escape_ffmpeg_path(path: Path) -> str:
    """Escapes file paths for safe use in FFmpeg filter graphs (subtitles/complex filters)."""
    p_str = path.resolve().as_posix()
    # Escape colons for Windows paths (e.g. C:/path -> C\:/path)
    p_str = p_str.replace(":", "\\:")
    return p_str


class VideoGenerator:
    """Assembles animated scene clips, dialogue, background music, and subtitles into the final video."""

    def __init__(self, fps: int = 30, resolution_16_9: tuple = (1920, 1080)):
        self.fps = fps
        self.width, self.height = resolution_16_9
        self.ffmpeg_available = check_ffmpeg_available()

    def _get_scene_audio_duration(self, audio_path: Path, fallback_duration: float) -> float:
        """Measure actual WAV/MP3 audio duration using pydub. Falls back to hint if pydub unavailable."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(str(audio_path))
            measured = len(audio) / 1000.0  # ms → seconds
            # Add 1.5s breathing room, minimum 5s for readability
            return max(measured + 1.5, 5.0)
        except Exception as e:
            logger.warning(f"Could not measure audio duration for {audio_path.name}: {e}. Using hint: {fallback_duration}s")
            return max(fallback_duration, 5.0)

    def _generate_2d_scene_clip(self, image_path: Path, audio_path: Path, output_path: Path, duration_sec: float) -> bool:
        """Generates a 2.5D Ken Burns zoom-in video clip from a static image and audio track."""
        if not self.ffmpeg_available:
            return False

        frames = int(duration_sec * self.fps)
        # Pick a random zoom/pan direction for visual variety
        pan_filter = random.choice(ZOOM_DIRECTIONS).format(d=frames, fps=self.fps)

        # Full filter chain: scale → crop to 1920x1080 → Ken Burns → pixel format
        vf_filter = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"{pan_filter},"
            f"format=yuv420p"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(self.fps), "-i", str(image_path),
            "-i", str(audio_path),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration_sec),
            "-shortest",
            str(output_path)
        ]

        try:
            logger.info(f"Rendering 2.5D clip for {output_path.name} ({duration_sec:.1f}s)...")
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
            if res.returncode == 0 and output_path.exists():
                return True
            else:
                logger.error(f"FFmpeg 2D scene generation failed: {res.stderr.decode('utf-8', errors='ignore')[:300]}")
                return False
        except Exception as e:
            logger.error(f"Failed to generate 2D scene clip: {e}")
            return False

    def assemble_episode_video(
        self,
        episode_data: Dict[str, Any],
        images_dir: Path,
        audio_dir: Path,
        output_video_dir: Path
    ) -> Dict[str, Any]:
        """Assemble all scenes using the hardened 2.5D animation and FFmpeg rendering pipeline."""
        # 1. Pre-flight Environment Validation
        validate_environment()
        
        # 2. Cleanup Legacy Temporary Files
        cleanup_orphaned_resources()

        output_video_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        rendered_clips = []
        scene_manifests = []

        # 3. Secure Temporary Context Directory for Intermediates
        with PipelineTempDir(output_video_dir) as temp_clips_dir:
            for scene in scenes:
                num = scene.get("scene_number", 1)
                hint_duration = float(scene.get("duration_seconds", 15))
                audio_path = audio_dir / f"scene_{num:02d}_audio.wav"
                image_path = images_dir / f"scene_{num:02d}.png"

                # Measure actual audio duration instead of using fixed hint
                if audio_path.exists():
                    duration = self._get_scene_audio_duration(audio_path, hint_duration)
                else:
                    duration = hint_duration
                
                # Render directly to a temporary path under the Context Manager
                clip_path = temp_clips_dir / f"scene_{num:02d}.mp4"
                
                success = False
                if self.ffmpeg_available and audio_path.exists() and image_path.exists():
                    success = self._generate_2d_scene_clip(
                        image_path=image_path,
                        audio_path=audio_path,
                        output_path=clip_path,
                        duration_sec=duration
                    )
                    
                    # Hardened check for atomic completion
                    lock_file = clip_path.with_suffix(".lock")
                    if success and clip_path.exists() and not lock_file.exists():
                        rendered_clips.append(clip_path)
                    else:
                        logger.error(f"Render failed or file locked/incomplete for scene {num}")

                scene_manifests.append({
                    "scene_number": num,
                    "duration_seconds": duration,
                    "audio_file": str(audio_path),
                    "rendered": success
                })

            final_video_path = output_video_dir / "episode.mp4"
            manifest_path = output_video_dir / "video_manifest.json"
            assembled = False

            # 4. Final Assembly (Concat, Subtitles Burn, and Mix Music)
            if self.ffmpeg_available and len(rendered_clips) == len(scenes) and rendered_clips:
                concat_list_file = temp_clips_dir / "concat_list.txt"
                concat_lines = [f"file '{clip.resolve().as_posix()}'" for clip in rendered_clips]
                save_text(concat_list_file, "\n".join(concat_lines))

                bg_music = audio_dir / "background_music.wav"
                srt_path = output_video_dir.parent / "subtitles" / "episode.srt"
                
                # Check subtitle existence & prepare path with proper styling
                srt_filter_str = ""
                if srt_path.exists():
                    escaped_srt = escape_ffmpeg_path(srt_path)
                    # Styling: Bottom Centre (Alignment=2), 52pt Arial Bold, White text, Black outline
                    srt_filter_str = (
                        f"subtitles='{escaped_srt}'"
                        f":force_style='Alignment=2,FontName=Arial,FontSize=52,Bold=1,"
                        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                        f"BackColour=&H80000000,Outline=3,Shadow=2,MarginV=60'"
                    )

                # Direct FFmpeg complex filter command to burn subtitles and mix audio
                filter_complex_parts = []
                if srt_filter_str:
                    filter_complex_parts.append(f"[0:v]{srt_filter_str}[v_sub]")
                else:
                    filter_complex_parts.append("[0:v]copy[v_sub]")

                if bg_music.exists():
                    filter_complex_parts.append("[1:a]volume=0.18[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[a]")
                    concat_cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
                        "-i", str(bg_music),
                        "-filter_complex", ";".join(filter_complex_parts),
                        "-map", "[v_sub]", "-map", "[a]",
                        "-c:v", "libx264",
                        "-preset", "slow",
                        "-crf", "18",
                        "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart",
                        "-max_muxing_queue_size", "1024",
                        "-c:a", "aac", "-b:a", "192k",
                        str(final_video_path)
                    ]
                else:
                    concat_cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
                        "-filter_complex", ";".join(filter_complex_parts),
                        "-map", "[v_sub]", "-map", "0:a",
                        "-c:v", "libx264",
                        "-preset", "slow",
                        "-crf", "18",
                        "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart",
                        "-max_muxing_queue_size", "1024",
                        "-c:a", "aac", "-b:a", "192k",
                        str(final_video_path)
                    ]

                try:
                    logger.info("Executing final FFmpeg composite assembly...")
                    res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
                    assembled = (res.returncode == 0 and final_video_path.exists())
                    if not assembled:
                        err_msg = res.stderr.decode("utf-8", errors="ignore")
                        logger.error(f"FFmpeg composite failed:\n{err_msg}")
                except Exception as e:
                    logger.error(f"FFmpeg concat failed: {e}")

            # 5. Pipeline Validation Output
            manifest_data = {
                "episode_id": episode_data.get("episode_id"),
                "ffmpeg_available": self.ffmpeg_available,
                "video_file": str(final_video_path) if assembled else None,
                "resolution": f"{self.width}x{self.height}",
                "fps": self.fps,
                "assembled": assembled,
                "scenes": scene_manifests
            }
            save_json(manifest_path, manifest_data)
            
            if assembled:
                print(f"Pipeline v3.0 YouTube-Ready Render Complete: [{final_video_path}]")
                logger.info(f"Pipeline v3.0 YouTube-Ready Render Complete: [{final_video_path}]")
            else:
                logger.error("Pipeline concluded without rendering the final episode.")

            return manifest_data
