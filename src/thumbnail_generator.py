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

        # 2. Draw Jack (Left Side) — Brown hair, blue overalls, yellow shirt
        jack_x = int(width * 0.18)
        base_y = int(height * 0.52)
        # Tousled brown hair
        hair_y = base_y - 65
        for spike in [
            [(jack_x - 10, hair_y), (jack_x + 5, hair_y - 35), (jack_x + 20, hair_y)],
            [(jack_x + 10, hair_y), (jack_x + 30, hair_y - 40), (jack_x + 50, hair_y)],
            [(jack_x + 35, hair_y), (jack_x + 55, hair_y - 35), (jack_x + 75, hair_y)],
            [(jack_x + 60, hair_y), (jack_x + 75, hair_y - 30), (jack_x + 90, hair_y)],
        ]:
            draw.polygon(spike, fill="#6B4226")
        # Head
        draw.ellipse([jack_x - 5, base_y - 55, jack_x + 75, base_y + 30], fill="#FFD1A4", outline="#3E2723", width=4)
        # Eyes
        draw.ellipse([jack_x + 8, base_y - 25, jack_x + 28, base_y - 5], fill="#FFFFFF", outline="#000000", width=2)
        draw.ellipse([jack_x + 42, base_y - 25, jack_x + 62, base_y - 5], fill="#FFFFFF", outline="#000000", width=2)
        draw.ellipse([jack_x + 14, base_y - 20, jack_x + 22, base_y - 10], fill="#6D4C41")  # Hazel
        draw.ellipse([jack_x + 48, base_y - 20, jack_x + 56, base_y - 10], fill="#6D4C41")
        # Blush & nose
        draw.ellipse([jack_x + 2, base_y - 3, jack_x + 15, base_y + 8], fill="#FFAB91")
        draw.ellipse([jack_x + 55, base_y - 3, jack_x + 68, base_y + 8], fill="#FFAB91")
        draw.ellipse([jack_x + 28, base_y - 5, jack_x + 40, base_y + 5], fill="#FFB088")
        # Smile
        draw.arc([jack_x + 20, base_y + 5, jack_x + 50, base_y + 22], start=0, end=180, fill="#3E2723", width=3)
        # Yellow T-shirt
        draw.rectangle([jack_x + 10, base_y + 30, jack_x + 60, base_y + 50], fill="#FFD600", outline="#F9A825", width=2)
        # Blue overalls
        draw.rectangle([jack_x - 5, base_y + 45, jack_x + 75, base_y + 100], fill="#1565C0", outline="#0D47A1", width=3)

        # 3. Draw Jill (Right Side) — Dark brown pigtails, pink dungaree
        jill_x = int(width * 0.72)
        # Pigtails
        draw.ellipse([jill_x - 30, base_y - 55, jill_x + 20, base_y + 80], fill="#3E2723")
        draw.ellipse([jill_x + 60, base_y - 55, jill_x + 110, base_y + 80], fill="#3E2723")
        # Pink ribbons
        draw.polygon([(jill_x - 5, base_y - 30), (jill_x - 18, base_y - 48), (jill_x - 18, base_y - 12)], fill="#F06292")
        draw.polygon([(jill_x + 85, base_y - 30), (jill_x + 98, base_y - 48), (jill_x + 98, base_y - 12)], fill="#F06292")
        # Head
        draw.ellipse([jill_x - 5, base_y - 55, jill_x + 85, base_y + 30], fill="#FFD1A4", outline="#3E2723", width=4)
        # Eyes
        draw.ellipse([jill_x + 10, base_y - 25, jill_x + 33, base_y - 5], fill="#FFFFFF", outline="#000000", width=2)
        draw.ellipse([jill_x + 47, base_y - 25, jill_x + 70, base_y - 5], fill="#FFFFFF", outline="#000000", width=2)
        draw.ellipse([jill_x + 17, base_y - 20, jill_x + 26, base_y - 10], fill="#4E342E")
        draw.ellipse([jill_x + 54, base_y - 20, jill_x + 63, base_y - 10], fill="#4E342E")
        # Freckles
        for fx, fy in [(jill_x + 28, base_y - 3), (jill_x + 36, base_y - 5), (jill_x + 44, base_y - 3), (jill_x + 52, base_y - 5)]:
            draw.ellipse([fx - 2, fy - 2, fx + 2, fy + 2], fill="#A1887F")
        # Smile
        draw.arc([jill_x + 25, base_y + 5, jill_x + 55, base_y + 22], start=0, end=180, fill="#3E2723", width=3)
        # Striped pastel shirt
        draw.rectangle([jill_x + 10, base_y + 30, jill_x + 70, base_y + 50], fill="#E8D5E0", outline="#D7CCC8", width=2)
        # Pink dungaree dress
        draw.rectangle([jill_x - 5, base_y + 45, jill_x + 85, base_y + 100], fill="#F48FB1", outline="#EC407A", width=3)

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
