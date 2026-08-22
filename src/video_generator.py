"""Modular Video Generator using FFmpeg with Ken Burns motion simulation."""

import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import check_ffmpeg_available, save_json, save_text, setup_logger

logger = setup_logger("VideoGenerator")


class VideoGenerator:
    """
    Acts as an assistant to generate DaVinci Resolve Edit Decision Lists (EDL)
    and editing instructions so human creators can manually assemble the episode.
    """

    def __init__(self, fps: int = 24, resolution_16_9: tuple = (1920, 1080)):
        self.fps = fps
        self.width_16_9, self.height_16_9 = resolution_16_9

    def build_davinci_edl(self, scenes: List[Dict[str, Any]], output_path: Path):
        """Generates a text guide representing DaVinci Resolve timeline assembly instructions."""
        lines = ["# 🎬 DaVinci Resolve Assembly Guide\n"]
        lines.append("## Setup Instructions")
        lines.append("1. Open DaVinci Resolve and create a new project.")
        lines.append(f"2. Set your Timeline settings to {self.width_16_9}x{self.height_16_9} at {self.fps}fps.")
        lines.append("3. Import all images from the `images/` folder into your Media Pool.")
        lines.append("4. Import your recorded OBS voiceover into the Media Pool.")
        lines.append("5. Import the background music (from YouTube Audio Library) into the Media Pool.\n")
        lines.append("## Timeline Sequence\n")
        
        current_time = 0.0
        for scene in scenes:
            num = scene.get("scene_number", 1)
            duration = float(scene.get("duration_seconds", 15))
            motion = scene.get("video_prompt", "zoom_in").lower()
            
            lines.append(f"### SCENE {num} (Time: {current_time:.1f}s to {current_time + duration:.1f}s)")
            lines.append(f"- **Video Track 1:** Drag `scene_{num:02d}.png` to timeline. Set duration to {duration} seconds.")
            
            if "zoom-out" in motion or "zoom out" in motion:
                lines.append(f"- **Inspector (Transform):** Add a keyframe at start (Zoom: 1.15) and end (Zoom: 1.0).")
            elif "pan" in motion:
                lines.append(f"- **Inspector (Transform):** Add a keyframe at start (X: -100) and end (X: 100).")
            else:
                lines.append(f"- **Inspector (Transform):** Add a keyframe at start (Zoom: 1.0) and end (Zoom: 1.15).")
            
            lines.append("")
            current_time += duration
            
        lines.append("## Audio Mixing")
        lines.append("- **Audio Track 1:** Place your OBS Voiceover recording. Sync it to match the scene durations above.")
        lines.append("- **Audio Track 2:** Place your YouTube Audio Library music. Lower the volume slider to -15dB so it sits nicely behind the voice.\n")
        
        save_text(output_path, "\n".join(lines))

    def assemble_episode_video(
        self,
        episode_data: Dict[str, Any],
        images_dir: Path,
        audio_dir: Path,
        output_video_dir: Path
    ) -> Dict[str, Any]:
        """
        Creates the DaVinci Resolve Editing Guide. Does NOT assemble any MP4 files.
        """
        output_video_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        
        edl_path = output_video_dir / "DaVinci_Resolve_Assembly_Guide.md"
        self.build_davinci_edl(scenes, edl_path)
        
        logger.info(f"Generated DaVinci Resolve guide at {edl_path}")
        
        return {
            "episode_id": episode_data.get("episode_id"),
            "ffmpeg_available": False,
            "video_file": None,
            "guide_file": str(edl_path),
            "resolution": f"{self.width_16_9}x{self.height_16_9}",
            "fps": self.fps,
            "assembled": False
        }
