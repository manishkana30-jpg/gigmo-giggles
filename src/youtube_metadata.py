"""YouTube metadata generator and chapter formatter."""

from pathlib import Path
from typing import Dict, Any, List
from src.utils import save_json, setup_logger

logger = setup_logger("YouTubeMetadata")


class YouTubeMetadataGenerator:
    """Formats YouTube video metadata, SEO tags, chapters, and Shorts concepts."""

    @classmethod
    def generate_metadata(cls, episode_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured YouTube metadata with chapter timestamps."""
        yt = episode_data.get("youtube", {})
        scenes = episode_data.get("scenes", [])
        quiz = episode_data.get("quiz", [])
        shorts = episode_data.get("shorts", [])

        # Build chapter timestamps
        chapters = []
        current_time = 0.0
        for scene in scenes:
            mins = int(current_time // 60)
            secs = int(current_time % 60)
            timestamp_str = f"{mins:02d}:{secs:02d}"
            chapters.append(f"{timestamp_str} - Scene {scene.get('scene_number')}: {scene.get('location')}")
            current_time += float(scene.get("duration_seconds", 15))

        # Add Quiz chapter
        if quiz:
            mins = int(current_time // 60)
            secs = int(current_time % 60)
            chapters.append(f"{mins:02d}:{secs:02d} - 🧠 Super Gigmo Quiz!")

        chapters_text = "\n".join(chapters)

        # Build full description
        desc_base = yt.get("description", "")
        hashtags = " ".join(yt.get("hashtags", ["#KidsLearning", "#ScienceForKids", "#GigmoGiggles"]))

        full_description = f"""{desc_base}

⏱️ CHAPTER TIMESTAMPS:
{chapters_text}

✨ ABOUT GIGMO GIGGLES:
Gigmo Giggles is a fun, colorful, educational animated cartoon show for curious kids! Join Bobo the Bear, Luna the Fox, and Milo the Robot as they explore science, nature, good manners, and the wonders of our world!

🔔 Subscribe for a new animated learning adventure every day!

{hashtags}
"""

        return {
            "episode_id": episode_data.get("episode_id"),
            "topic": episode_data.get("topic"),
            "video_metadata": {
                "title": yt.get("title", f"{episode_data.get('topic')} | Gigmo Giggles"),
                "description": full_description.strip(),
                "tags": yt.get("tags", ["kids learning", "educational cartoon", "gigmo giggles"]),
                "category_id": "27",  # Education
                "category_name": "Education",
                "default_language": "en",
                "target_audience": "Children (Made for Kids)",
                "made_for_kids": True,
                "chapters": chapters
            },
            "shorts_metadata": shorts
        }

    @classmethod
    def save_metadata(cls, episode_data: Dict[str, Any], output_path: Path) -> Path:
        """Create and save youtube_metadata.json."""
        metadata = cls.generate_metadata(episode_data)
        save_json(output_path, metadata)
        logger.info(f"Saved YouTube metadata to {output_path}")
        return output_path
