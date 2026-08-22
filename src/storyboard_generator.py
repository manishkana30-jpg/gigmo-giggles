"""Storyboard generator structuring visual and audio production sequences."""

from pathlib import Path
from typing import Dict, Any, List
from src.utils import save_json, setup_logger

logger = setup_logger("StoryboardGenerator")


class StoryboardGenerator:
    """Generates structured storyboard specifications for video and animation assembly."""

    @classmethod
    def create_storyboard(cls, episode_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert episode data into an animation-ready storyboard document."""
        scenes = episode_data.get("scenes", [])
        total_duration = sum(s.get("duration_seconds", 15) for s in scenes)

        storyboard_scenes: List[Dict[str, Any]] = []
        current_timestamp = 0.0

        for s in scenes:
            duration = float(s.get("duration_seconds", 15))
            start_time = current_timestamp
            end_time = start_time + duration
            current_timestamp = end_time

            # Format camera motion from prompt or default
            v_prompt = s.get("video_prompt", "").lower()
            if "zoom-in" in v_prompt or "zoom in" in v_prompt:
                motion_type = "zoom_in"
            elif "zoom-out" in v_prompt or "zoom out" in v_prompt:
                motion_type = "zoom_out"
            elif "pan" in v_prompt:
                motion_type = "pan_horizontal"
            else:
                motion_type = "ken_burns_gentle"

            storyboard_scenes.append({
                "scene_number": s.get("scene_number"),
                "timing": {
                    "start_seconds": round(start_time, 2),
                    "end_seconds": round(end_time, 2),
                    "duration_seconds": duration
                },
                "location": s.get("location"),
                "action": s.get("action"),
                "motion": {
                    "type": motion_type,
                    "prompt": s.get("video_prompt")
                },
                "visual": {
                    "image_prompt": s.get("image_prompt"),
                    "image_filename": f"scene_{s.get('scene_number', 1):02d}.png"
                },
                "audio": {
                    "voice_filename": f"scene_{s.get('scene_number', 1):02d}_audio.wav",
                    "voice_direction": s.get("voice_direction"),
                    "dialogue_lines": s.get("dialogue", []),
                    "sound_effects": s.get("sound_effects", [])
                }
            })

        return {
            "episode_id": episode_data.get("episode_id"),
            "topic": episode_data.get("topic"),
            "title": episode_data.get("title"),
            "total_duration_seconds": round(total_duration, 2),
            "scenes_count": len(scenes),
            "scenes": storyboard_scenes
        }

    @classmethod
    def save_storyboard(cls, episode_data: Dict[str, Any], output_path: Path) -> Path:
        """Create and save storyboard.json."""
        sb = cls.create_storyboard(episode_data)
        save_json(output_path, sb)
        logger.info(f"Saved storyboard specification to {output_path}")
        return output_path
