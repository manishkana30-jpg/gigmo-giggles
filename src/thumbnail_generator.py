"""YouTube Thumbnail Generator creating eye-catching cartoon thumbnails."""

from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw

from src.utils import save_json, setup_logger

logger = setup_logger("ThumbnailGenerator")


class ThumbnailGenerator:
    """Generates bright, high-contrast, child-friendly YouTube thumbnails."""

    @classmethod
    def generate_thumbnail(
        cls,
        episode_data: Dict[str, Any],
        output_dir: Path,
        width: int = 1280,
        height: int = 720
    ) -> Path:
        """
        Render thumbnail image and save prompt manifest to output_dir.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        thumb_data = episode_data.get("thumbnail", {})
        if not thumb_data or not isinstance(thumb_data, dict):
            thumb_data = {
                "prompt": f"Vibrant kids YouTube thumbnail for {episode_data.get('topic')}",
                "overlay_text": episode_data.get("topic", "GIGMO GIGGLES").upper()
            }

        prompt = thumb_data.get("prompt", "")
        overlay_text = thumb_data.get("overlay_text") or episode_data.get("topic", "FUN KIDS LEARNING").upper()
        if len(overlay_text) > 28:
            overlay_text = overlay_text[:25] + "..."

        # Save prompt manifest
        manifest_path = output_dir / "thumbnail_prompt.json"
        save_json(manifest_path, {
            "episode_id": episode_data.get("episode_id"),
            "prompt": prompt,
            "overlay_text": overlay_text
        })

        # Render Photopea Instructions
        instructions_path = output_dir / "Photopea_Thumbnail_Guide.md"
        lines = [
            f"# 🖼️ Photopea Thumbnail Guide",
            "Follow these instructions to create your thumbnail in [Photopea](https://www.photopea.com/):",
            "1. Create a new project: 1280x720 pixels.",
            "2. Import a vibrant background image from the `images/` folder (e.g. `scene_01.png`).",
            "3. Add a Bright Yellow (#FFD600) radial gradient behind the characters to make them pop.",
            "4. Add a text layer with the following overlay text:",
            f"   > **{overlay_text}**",
            "5. Make the text font bold (e.g., Impact or Montserrat Black), color it White, and add a thick Red or Black stroke (Outline).",
            "6. Export as JPG or PNG and save it to your computer."
        ]
        
        from src.utils import save_text
        save_text(instructions_path, "\n".join(lines))

        logger.info(f"Generated Photopea instructions at {instructions_path}")
        return instructions_path
