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

        # Render vibrant thumbnail image
        img = Image.new("RGB", (width, height), "#FFD600")
        draw = ImageDraw.Draw(img)

        # 1. Radial/Diagonal background gradient
        for y in range(height):
            ratio = y / height
            r = int(255 * (1 - ratio * 0.1))
            g = int(214 * (1 - ratio * 0.3))
            b = int(0)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Sunburst lines in background
        center_x, center_y = width // 2, height // 2
        for angle_deg in range(0, 360, 20):
            import math
            rad1 = math.radians(angle_deg)
            rad2 = math.radians(angle_deg + 10)
            x1 = center_x + math.cos(rad1) * 1000
            y1 = center_y + math.sin(rad1) * 1000
            x2 = center_x + math.cos(rad2) * 1000
            y2 = center_y + math.sin(rad2) * 1000
            draw.polygon([(center_x, center_y), (x1, y1), (x2, y2)], fill="#FFEA00")

        # 2. Draw Bobo (Bear) on Left Side
        bobo_x = int(width * 0.18)
        base_y = int(height * 0.52)
        # Ears
        draw.ellipse([bobo_x - 30, base_y - 120, bobo_x + 20, base_y - 70], fill="#8D5B28", outline="#4E342E", width=5)
        draw.ellipse([bobo_x + 110, base_y - 120, bobo_x + 160, base_y - 70], fill="#8D5B28", outline="#4E342E", width=5)
        # Head
        draw.ellipse([bobo_x - 20, base_y - 90, bobo_x + 150, base_y + 80], fill="#B27B38", outline="#4E342E", width=7)
        # Snout
        draw.ellipse([bobo_x + 15, base_y - 20, bobo_x + 115, base_y + 60], fill="#FFE082")
        draw.ellipse([bobo_x + 50, base_y - 15, bobo_x + 80, base_y + 10], fill="#212121")
        # Big Sparkling Eyes
        draw.ellipse([bobo_x + 20, base_y - 65, bobo_x + 55, base_y - 30], fill="#FFFFFF", outline="#000000", width=3)
        draw.ellipse([bobo_x + 75, base_y - 65, bobo_x + 110, base_y - 30], fill="#FFFFFF", outline="#000000", width=3)
        draw.ellipse([bobo_x + 30, base_y - 58, bobo_x + 48, base_y - 38], fill="#212121")
        draw.ellipse([bobo_x + 85, base_y - 58, bobo_x + 103, base_y - 38], fill="#212121")
        # Sparkle dots in eyes
        draw.ellipse([bobo_x + 38, base_y - 55, bobo_x + 44, base_y - 47], fill="#FFFFFF")
        draw.ellipse([bobo_x + 93, base_y - 55, bobo_x + 99, base_y - 47], fill="#FFFFFF")

        # 3. Draw Milo (Robot) on Right Side
        milo_x = int(width * 0.72)
        # Antenna
        draw.line([milo_x + 60, base_y - 110, milo_x + 60, base_y - 50], fill="#78909C", width=8)
        draw.ellipse([milo_x + 45, base_y - 135, milo_x + 75, base_y - 105], fill="#FF1744", outline="#B71C1C", width=4)
        # Head
        draw.rounded_rectangle([milo_x, base_y - 50, milo_x + 120, base_y + 60], radius=20, fill="#29B6F6", outline="#01579B", width=7)
        # Screen Eyes
        draw.rounded_rectangle([milo_x + 15, base_y - 25, milo_x + 105, base_y + 25], radius=10, fill="#212121")
        draw.ellipse([milo_x + 25, base_y - 15, milo_x + 50, base_y + 15], fill="#00E676")
        draw.ellipse([milo_x + 70, base_y - 15, milo_x + 95, base_y + 15], fill="#00E676")

        # 4. Giant Bold Text Header Badge (Centered)
        badge_box = [int(width * 0.12), int(height * 0.68), int(width * 0.88), int(height * 0.92)]
        # Outer border shadow
        draw.rounded_rectangle([badge_box[0] + 6, badge_box[1] + 6, badge_box[2] + 6, badge_box[3] + 6], radius=25, fill="#000000")
        # Main badge fill
        draw.rounded_rectangle(badge_box, radius=25, fill="#D50000", outline="#FFFFFF", width=8)

        # Text banner
        banner_str = f"⭐ {overlay_text} ⭐"
        draw.text((badge_box[0] + 40, badge_box[1] + 35), banner_str, fill="#FFFFFF")

        # Top Badge: "GIGMO GIGGLES"
        top_badge = [int(width * 0.32), 25, int(width * 0.68), 90]
        draw.rounded_rectangle(top_badge, radius=18, fill="#6200EA", outline="#FFFFFF", width=4)
        draw.text((top_badge[0] + 35, top_badge[1] + 18), "🌈 GIGMO GIGGLES", fill="#FFEB3B")

        thumb_img_path = output_dir / "thumbnail.png"
        img.save(str(thumb_img_path), "PNG")
        logger.info(f"Generated YouTube thumbnail image at {thumb_img_path}")
        return thumb_img_path
