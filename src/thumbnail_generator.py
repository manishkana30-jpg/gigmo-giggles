"""YouTube Thumbnail Generator with Gemini AI and PIL fallback."""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import math

from src.utils import save_json, setup_logger

logger = setup_logger("ThumbnailGenerator")

# Try importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class ThumbnailGenerator:
    """Generates eye-catching, child-friendly YouTube thumbnails."""

    @classmethod
    def _try_gemini_thumbnail(cls, prompt: str, output_path: Path) -> bool:
        """Try generating thumbnail via Gemini image generation API."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or not GENAI_AVAILABLE:
            return False

        try:
            client = genai.Client(api_key=api_key)

            enhanced_prompt = (
                f"{prompt}. "
                "Make it a vibrant, eye-catching YouTube thumbnail for a kids cartoon channel. "
                "Bold bright colors, high contrast, cute cartoon characters with big expressive eyes. "
                "Clean professional quality, no text overlays. 16:9 aspect ratio."
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=enhanced_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"]
                )
            )

            if response and response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, "inline_data") and part.inline_data:
                                data = part.inline_data
                                if hasattr(data, "data") and data.data:
                                    output_path.parent.mkdir(parents=True, exist_ok=True)
                                    with open(output_path, "wb") as f:
                                        f.write(data.data)

                                    # Resize to YouTube thumbnail size
                                    try:
                                        img = Image.open(output_path)
                                        if img.size != (1280, 720):
                                            img = img.resize((1280, 720), Image.LANCZOS)
                                            img.save(str(output_path), "PNG")
                                    except Exception:
                                        pass

                                    logger.info(f"Generated Gemini AI thumbnail: {output_path.name}")
                                    return True

            return False
        except Exception as e:
            logger.warning(f"Gemini thumbnail generation failed: {e}")
            return False

    @classmethod
    def _add_text_overlay(cls, img_path: Path, overlay_text: str, channel_name: str = "GIGMO GIGGLES"):
        """Add bold text overlay to the thumbnail image."""
        try:
            img = Image.open(img_path)
            draw = ImageDraw.Draw(img)
            width, height = img.size

            # Try to load a good font (available on Ubuntu runners)
            font_large = None
            font_small = None
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/impact.ttf",
            ]
            for fp in font_paths:
                try:
                    font_large = ImageFont.truetype(fp, 64)
                    font_small = ImageFont.truetype(fp, 36)
                    break
                except (OSError, IOError):
                    continue

            if font_large is None:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

            # Bottom banner with title text
            banner_h = 130
            banner_y = height - banner_h
            # Semi-transparent dark banner
            overlay = Image.new("RGBA", (width, banner_h), (200, 0, 0, 220))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.paste(overlay, (0, banner_y), overlay)
            draw = ImageDraw.Draw(img)

            # Draw title text with white stroke
            text = f"⭐ {overlay_text} ⭐"
            # Shadow
            draw.text((42, banner_y + 22), text, fill="#000000", font=font_large)
            # Main text
            draw.text((40, banner_y + 20), text, fill="#FFFFFF", font=font_large)

            # Top badge with channel name
            badge_w = 380
            badge_h_top = 55
            badge_overlay = Image.new("RGBA", (badge_w, badge_h_top), (98, 0, 234, 230))
            img.paste(badge_overlay, (width // 2 - badge_w // 2, 15), badge_overlay)
            draw = ImageDraw.Draw(img)
            draw.text((width // 2 - badge_w // 2 + 30, 25), f"🌈 {channel_name}", fill="#FFEB3B", font=font_small)

            # Save as RGB PNG
            img = img.convert("RGB")
            img.save(str(img_path), "PNG")
            logger.info("Added text overlay to thumbnail")

        except Exception as e:
            logger.warning(f"Failed to add text overlay: {e}")

    @classmethod
    def _generate_pil_thumbnail(cls, episode_data: Dict[str, Any], output_path: Path, width: int = 1280, height: int = 720):
        """Generate a procedural PIL thumbnail as fallback."""
        img = Image.new("RGB", (width, height), "#FFD600")
        draw = ImageDraw.Draw(img)

        # 1. Gradient background
        for y in range(height):
            ratio = y / height
            r = int(255 * (1 - ratio * 0.1))
            g = int(214 * (1 - ratio * 0.3))
            b = int(0)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Sunburst lines
        center_x, center_y = width // 2, height // 2
        for angle_deg in range(0, 360, 20):
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
        draw.ellipse([bobo_x - 30, base_y - 120, bobo_x + 20, base_y - 70], fill="#8D5B28", outline="#4E342E", width=5)
        draw.ellipse([bobo_x + 110, base_y - 120, bobo_x + 160, base_y - 70], fill="#8D5B28", outline="#4E342E", width=5)
        draw.ellipse([bobo_x - 20, base_y - 90, bobo_x + 150, base_y + 80], fill="#B27B38", outline="#4E342E", width=7)
        draw.ellipse([bobo_x + 15, base_y - 20, bobo_x + 115, base_y + 60], fill="#FFE082")
        draw.ellipse([bobo_x + 50, base_y - 15, bobo_x + 80, base_y + 10], fill="#212121")
        draw.ellipse([bobo_x + 20, base_y - 65, bobo_x + 55, base_y - 30], fill="#FFFFFF", outline="#000000", width=3)
        draw.ellipse([bobo_x + 75, base_y - 65, bobo_x + 110, base_y - 30], fill="#FFFFFF", outline="#000000", width=3)
        draw.ellipse([bobo_x + 30, base_y - 58, bobo_x + 48, base_y - 38], fill="#212121")
        draw.ellipse([bobo_x + 85, base_y - 58, bobo_x + 103, base_y - 38], fill="#212121")
        draw.ellipse([bobo_x + 38, base_y - 55, bobo_x + 44, base_y - 47], fill="#FFFFFF")
        draw.ellipse([bobo_x + 93, base_y - 55, bobo_x + 99, base_y - 47], fill="#FFFFFF")

        # 3. Draw Milo (Robot) on Right Side
        milo_x = int(width * 0.72)
        draw.line([milo_x + 60, base_y - 110, milo_x + 60, base_y - 50], fill="#78909C", width=8)
        draw.ellipse([milo_x + 45, base_y - 135, milo_x + 75, base_y - 105], fill="#FF1744", outline="#B71C1C", width=4)
        draw.rounded_rectangle([milo_x, base_y - 50, milo_x + 120, base_y + 60], radius=20, fill="#29B6F6", outline="#01579B", width=7)
        draw.rounded_rectangle([milo_x + 15, base_y - 25, milo_x + 105, base_y + 25], radius=10, fill="#212121")
        draw.ellipse([milo_x + 25, base_y - 15, milo_x + 50, base_y + 15], fill="#00E676")
        draw.ellipse([milo_x + 70, base_y - 15, milo_x + 95, base_y + 15], fill="#00E676")

        img.save(str(output_path), "PNG")

    @classmethod
    def generate_thumbnail(
        cls,
        episode_data: Dict[str, Any],
        output_dir: Path,
        width: int = 1280,
        height: int = 720
    ) -> Path:
        """Generate thumbnail: try Gemini AI first, fall back to PIL procedural."""
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

        thumb_img_path = output_dir / "thumbnail.png"

        # Try Gemini AI first
        gemini_success = cls._try_gemini_thumbnail(prompt, thumb_img_path)

        if gemini_success:
            # Add text overlay on top of AI image
            cls._add_text_overlay(thumb_img_path, overlay_text)
        else:
            # Fall back to PIL procedural
            logger.info("Falling back to PIL procedural thumbnail generator.")
            cls._generate_pil_thumbnail(episode_data, thumb_img_path, width, height)
            cls._add_text_overlay(thumb_img_path, overlay_text)

        logger.info(f"Generated YouTube thumbnail image at {thumb_img_path}")
        return thumb_img_path
