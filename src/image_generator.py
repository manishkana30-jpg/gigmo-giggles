"""Multi-provider image generation with Gemini AI and comic-cartoon procedural fallback."""

import os
import math
import random
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont

from src.utils import save_json, setup_logger

logger = setup_logger("ImageGenerator")

# Try importing google-genai for image generation
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class BaseImageProvider(ABC):
    """Abstract interface for image generation providers."""

    @abstractmethod
    def generate(self, prompt: str, output_path: Path, width: int = 1920, height: int = 1080, context: Optional[Dict[str, Any]] = None) -> bool:
        """Generate an image given a text prompt and save to output_path."""
        pass


class GeminiImageProvider(BaseImageProvider):
    """Gemini 2.0 Flash image generation provider (free tier compatible)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = "gemini-2.5-flash-image"

    def generate(self, prompt: str, output_path: Path, width: int = 1920, height: int = 1080, context: Optional[Dict[str, Any]] = None) -> bool:
        if not self.api_key or not GENAI_AVAILABLE:
            logger.debug("Gemini API key or SDK not available for image generation.")
            return False

        try:
            client = genai.Client(api_key=self.api_key)

            # Enhance prompt with basic quality tokens if needed, but rely mostly on the detailed prompt
            enhanced_prompt = (
                "High quality, detailed, masterpiece, 16:9 aspect ratio, professional kids show frame. "
                "no text overlays, no watermarks, no borders. "
                f"Scene: {prompt}"
            )

            response = client.models.generate_content(
                model=self.model_name,
                contents=enhanced_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"]
                )
            )

            # Extract image from response
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

                                    # Resize to target resolution if needed
                                    try:
                                        img = Image.open(output_path)
                                        if img.size != (width, height):
                                            img = img.resize((width, height), Image.LANCZOS)
                                            img.save(str(output_path), "PNG")
                                    except Exception:
                                        pass

                                    logger.info(f"Generated Gemini AI image: {output_path.name}")
                                    return True

            logger.warning("No image data in Gemini response.")
            return False

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "too_many_requests" in err_str.lower():
                logger.warning(f"Gemini image gen rate limited: {e}")
            else:
                logger.warning(f"Gemini image generation failed: {e}")
            return False


class HuggingFaceImageProvider(BaseImageProvider):
    """Hugging Face Inference API provider for FLUX / SD models."""

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.environ.get("HF_TOKEN")
        self.api_url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

    def generate(self, prompt: str, output_path: Path, width: int = 1920, height: int = 1080, context: Optional[Dict[str, Any]] = None) -> bool:
        if not self.api_token:
            logger.debug("Hugging Face API token not configured.")
            return False

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.api_token}"}
            payload = {
                "inputs": prompt,
                "parameters": {"width": min(width, 1024), "height": min(height, 1024)}
            }
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=45)
            if response.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(response.content)

                # Upscale to target resolution
                try:
                    img = Image.open(output_path)
                    if img.size != (width, height):
                        img = img.resize((width, height), Image.LANCZOS)
                        img.save(str(output_path), "PNG")
                except Exception:
                    pass

                logger.info(f"Generated HF image: {output_path.name}")
                return True
            else:
                logger.warning(f"HF API returned status {response.status_code}: {response.text[:100]}")
                return False
        except Exception as e:
            logger.warning(f"HF image generation failed: {e}")
            return False


class PILComicProceduralProvider(BaseImageProvider):
    """
    High-quality 2D cartoon comic scene generator using Pillow.
    Guarantees zero-failure, instant, offline generation of colorful cartoon graphics
    featuring canonical characters (Bobo, Luna, Milo) with speech bubbles and scenic backdrops.
    """

    def generate(
        self,
        prompt: str,
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGB", (width, height), "#87CEEB")
            draw = ImageDraw.Draw(img)

            scene_num = context.get("scene_number", 1) if context else 1
            location = context.get("location", "Gigmo Discovery Land") if context else "Gigmo Discovery Land"
            dialogues = context.get("dialogue", []) if context else []

            # 1. Background sky gradient & scenery
            self._draw_scenery(draw, width, height, scene_num)

            # 2. Draw cartoon cast (Bobo, Luna, Milo)
            self._draw_characters(draw, width, height, scene_num)

            # 3. Speech bubble or educational banner
            self._draw_dialogue_bubble(draw, width, height, dialogues, location, scene_num)

            # 4. Save image
            img.save(str(output_path), "PNG")
            logger.info(f"Generated procedural cartoon scene: {output_path.name}")
            return True
        except Exception as e:
            logger.error(f"PIL comic generation error: {e}")
            return False

    def _draw_scenery(self, draw: ImageDraw.ImageDraw, width: int, height: int, scene_num: int):
        """Draw sunny sky, rolling hills, clouds, and bright sunshine."""
        # Sky gradient bands
        sky_colors = ["#4FC3F7", "#81D4FA", "#B3E5FC", "#E1F5FE"]
        band_h = height // 2 // len(sky_colors)
        for idx, col in enumerate(sky_colors):
            draw.rectangle([0, idx * band_h, width, (idx + 1) * band_h], fill=col)

        # Cheerful Sun in top right
        sun_box = [width - 260, 40, width - 80, 220]
        draw.ellipse(sun_box, fill="#FFD700", outline="#FFA000", width=8)
        # Sun rays
        center_x, center_y = width - 170, 130
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            x1 = center_x + math.cos(rad) * 100
            y1 = center_y + math.sin(rad) * 100
            x2 = center_x + math.cos(rad) * 135
            y2 = center_y + math.sin(rad) * 135
            draw.line([x1, y1, x2, y2], fill="#FFA000", width=6)

        # Fluffy white clouds
        cloud_positions = [(200, 100), (650, 80), (1200, 120)]
        for cx, cy in cloud_positions:
            draw.ellipse([cx, cy, cx + 180, cy + 90], fill="#FFFFFF")
            draw.ellipse([cx + 40, cy - 30, cx + 140, cy + 70], fill="#FFFFFF")
            draw.ellipse([cx + 90, cy - 10, cx + 220, cy + 80], fill="#FFFFFF")

        # Rolling green hills at bottom
        hill_y = int(height * 0.55)
        draw.ellipse([-200, hill_y, width // 2 + 300, height + 300], fill="#4CAF50")
        draw.ellipse([width // 3, hill_y - 40, width + 400, height + 400], fill="#66BB6A")
        draw.rectangle([0, int(height * 0.72), width, height], fill="#43A047")

    def _draw_characters(self, draw: ImageDraw.ImageDraw, width: int, height: int, scene_num: int):
        """Draw Bobo (Bear), Luna (Fox), and Milo (Robot)."""
        base_y = int(height * 0.58)

        # Bobo the Bear (Left)
        bobo_x = int(width * 0.22)
        draw.ellipse([bobo_x - 30, base_y - 120, bobo_x + 10, base_y - 80], fill="#8D5B28", outline="#5D3A1A", width=4)
        draw.ellipse([bobo_x + 90, base_y - 120, bobo_x + 130, base_y - 80], fill="#8D5B28", outline="#5D3A1A", width=4)
        draw.ellipse([bobo_x - 40, base_y, bobo_x + 140, base_y + 240], fill="#A0682C", outline="#5D3A1A", width=6)
        draw.ellipse([bobo_x - 20, base_y - 100, bobo_x + 120, base_y + 40], fill="#B27B38", outline="#5D3A1A", width=6)
        draw.ellipse([bobo_x + 10, base_y - 40, bobo_x + 90, base_y + 20], fill="#EAD2AC")
        draw.ellipse([bobo_x + 40, base_y - 35, bobo_x + 60, base_y - 15], fill="#2C1B0D")
        draw.ellipse([bobo_x + 15, base_y - 70, bobo_x + 35, base_y - 45], fill="#FFFFFF", outline="#000000", width=2)
        draw.ellipse([bobo_x + 65, base_y - 70, bobo_x + 85, base_y - 45], fill="#FFFFFF", outline="#000000", width=2)
        draw.ellipse([bobo_x + 22, base_y - 65, bobo_x + 32, base_y - 50], fill="#2C1B0D")
        draw.ellipse([bobo_x + 72, base_y - 65, bobo_x + 82, base_y - 50], fill="#2C1B0D")
        draw.polygon([(bobo_x + 10, base_y + 30), (bobo_x + 90, base_y + 30), (bobo_x + 50, base_y + 80)], fill="#FFEB3B", outline="#F57F17")

        # Luna the Fox (Center)
        luna_x = int(width * 0.48)
        draw.polygon([(luna_x - 10, base_y - 110), (luna_x + 25, base_y - 40), (luna_x - 30, base_y - 40)], fill="#FF7043", outline="#BF360C")
        draw.polygon([(luna_x + 110, base_y - 110), (luna_x + 75, base_y - 40), (luna_x + 130, base_y - 40)], fill="#FF7043", outline="#BF360C")
        draw.ellipse([luna_x - 10, base_y + 10, luna_x + 110, base_y + 220], fill="#FF7043", outline="#BF360C", width=6)
        draw.rectangle([luna_x + 15, base_y + 30, luna_x + 85, base_y + 140], fill="#009688", outline="#004D40", width=4)
        draw.ellipse([luna_x, base_y - 70, luna_x + 100, base_y + 30], fill="#FF8A65", outline="#BF360C", width=5)
        draw.polygon([(luna_x + 20, base_y + 10), (luna_x + 80, base_y + 10), (luna_x + 50, base_y + 40)], fill="#FFFFFF")
        draw.ellipse([luna_x + 43, base_y + 28, luna_x + 57, base_y + 40], fill="#212121")
        draw.ellipse([luna_x + 20, base_y - 45, luna_x + 40, base_y - 20], fill="#FFA726", outline="#000000", width=2)
        draw.ellipse([luna_x + 60, base_y - 45, luna_x + 80, base_y - 20], fill="#FFA726", outline="#000000", width=2)
        draw.ellipse([luna_x + 27, base_y - 40, luna_x + 36, base_y - 25], fill="#212121")
        draw.ellipse([luna_x + 67, base_y - 40, luna_x + 76, base_y - 25], fill="#212121")

        # Milo the Robot (Right)
        milo_x = int(width * 0.72)
        draw.line([milo_x + 45, base_y - 90, milo_x + 45, base_y - 45], fill="#78909C", width=6)
        draw.ellipse([milo_x + 35, base_y - 110, milo_x + 55, base_y - 90], fill="#FFEB3B", outline="#F57F17", width=3)
        draw.rounded_rectangle([milo_x, base_y - 45, milo_x + 90, base_y + 35], radius=15, fill="#42A5F5", outline="#0D47A1", width=5)
        draw.rounded_rectangle([milo_x + 12, base_y - 25, milo_x + 78, base_y + 10], radius=8, fill="#212121")
        draw.ellipse([milo_x + 20, base_y - 20, milo_x + 38, base_y - 2], fill="#76FF03")
        draw.ellipse([milo_x + 52, base_y - 20, milo_x + 70, base_y - 2], fill="#76FF03")
        draw.rounded_rectangle([milo_x - 5, base_y + 45, milo_x + 95, base_y + 160], radius=12, fill="#64B5F6", outline="#0D47A1", width=5)
        draw.ellipse([milo_x + 5, base_y + 160, milo_x + 40, base_y + 195], fill="#37474F", outline="#212121", width=4)
        draw.ellipse([milo_x + 50, base_y + 160, milo_x + 85, base_y + 195], fill="#37474F", outline="#212121", width=4)

    def _draw_dialogue_bubble(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        dialogues: List[Dict[str, Any]],
        location: str,
        scene_num: int
    ):
        """Render top scene title banner and bottom speech card."""
        # Top banner: Location & Scene Number
        banner_box = [int(width * 0.05), 30, int(width * 0.55), 100]
        draw.rounded_rectangle(banner_box, radius=20, fill="#FFFFFF", outline="#FF9800", width=4)
        banner_text = f"✨ Scene {scene_num}: {location}"
        draw.text((banner_box[0] + 25, banner_box[1] + 18), banner_text, fill="#E65100")

        # Bottom Dialogue Card
        if dialogues:
            first_dial = dialogues[0]
            speaker = first_dial.get("character", "Jack")
            speech = first_dial.get("text", "Let's explore!")
            
            if len(speech) > 90:
                speech = speech[:87] + "..."

            card_box = [int(width * 0.10), int(height * 0.82), int(width * 0.90), int(height * 0.96)]
            draw.rounded_rectangle(card_box, radius=24, fill="#FFF9C4", outline="#FBC02D", width=6)
            
            speaker_label = f"📢 {speaker.upper()}:"
            draw.text((card_box[0] + 30, card_box[1] + 15), speaker_label, fill="#E65100")
            draw.text((card_box[0] + 30, card_box[1] + 55), f"\"{speech}\"", fill="#263238")


class ImageGenerator:
    """Multi-provider image generation orchestrator with Gemini AI priority."""

    def __init__(self, provider: Optional[BaseImageProvider] = None):
        if provider:
            self.provider = provider
        elif os.environ.get("GEMINI_API_KEY") and GENAI_AVAILABLE:
            self.provider = GeminiImageProvider()
        elif os.environ.get("HF_TOKEN"):
            self.provider = HuggingFaceImageProvider()
        else:
            self.provider = PILComicProceduralProvider()

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Generate a single image file with cascading provider fallback."""
        if output_path.exists():
            logger.info(f"Image already exists, skipping generation: {output_path.name}")
            return True
        success = self.provider.generate(prompt, output_path, width, height, context)

        # Fallback cascade: Gemini → HuggingFace → PIL
        if not success and isinstance(self.provider, GeminiImageProvider):
            logger.info("Gemini image gen failed. Trying HuggingFace...")
            hf = HuggingFaceImageProvider()
            success = hf.generate(prompt, output_path, width, height, context)

        if not success and not isinstance(self.provider, PILComicProceduralProvider):
            logger.info("External image providers failed. Falling back to PIL Comic Generator...")
            fallback = PILComicProceduralProvider()
            return fallback.generate(prompt, output_path, width, height, context)

        return success

    def generate_all_scenes(self, episode_data: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """Generate images for all scenes in episode and save image_prompts.json manifest."""
        output_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        manifest = []

        for i, scene in enumerate(scenes):
            num = scene.get("scene_number", 1)
            filename = f"scene_{num:02d}.png"
            image_path = output_dir / filename
            prompt = scene.get("image_prompt", "")

            context = {
                "scene_number": num,
                "location": scene.get("location", ""),
                "action": scene.get("action", ""),
                "dialogue": scene.get("dialogue", [])
            }

            success = self.generate_image(prompt, image_path, width=1920, height=1080, context=context)

            # Rate limit protection: small delay between Gemini API calls
            if isinstance(self.provider, GeminiImageProvider) and i < len(scenes) - 1:
                time.sleep(2)

            manifest.append({
                "scene_number": num,
                "filename": filename,
                "prompt": prompt,
                "generated": success
            })

        save_json(output_dir / "image_prompts.json", manifest)
        logger.info(f"Generated {len(manifest)} scene images in {output_dir}")
        return {"manifest": manifest, "count": len(manifest)}
