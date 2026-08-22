"""Character Voice and Text-to-Speech (TTS) generator."""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import save_json, generate_simple_tone_wav, generate_melodic_chime_wav, setup_logger

logger = setup_logger("VoiceGenerator")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not installed. Will use procedural audio tone generator for testing.")


class VoiceGenerator:
    """Generates audio speech tracks for characters with fallback manifest logging."""

    # Character pitch and vocal frequencies for fallback tone generator
    CHARACTER_PROFILES = {
        "Bobo": {
            "pitch_hz": 260.0,
            "tone": "warm_bear",
            "gtts_tld": "com"
        },
        "Luna": {
            "pitch_hz": 440.0,
            "tone": "cheerful_fox",
            "gtts_tld": "co.uk"
        },
        "Milo": {
            "pitch_hz": 620.0,
            "tone": "cute_robot",
            "gtts_tld": "ca"
        }
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def generate_speech(
        self,
        text: str,
        character: str,
        output_path: Path,
        duration_sec: float = 3.0
    ) -> bool:
        """Skip automated speech generation for Manual Creator Mode."""
        return True

    def generate_all_scene_audio(
        self,
        episode_data: Dict[str, Any],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        Creates an OBS Recording Guide instead of generating audio files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        
        obs_guide_path = output_dir / "OBS_Recording_Guide.md"
        lines = [
            "# 🎙️ OBS Voice Recording Guide",
            "You are in Manual Creator Mode. The bot will NOT generate voice files.",
            "Instead, please follow these steps:",
            "1. Open **OBS Studio** and ensure your microphone is selected as the Audio Input Capture.",
            "2. Open the `script.md` file (generated in the root of the episode folder).",
            "3. Put the OBS Teleprompter Script section on your screen.",
            "4. Hit **Start Recording** in OBS.",
            "5. Read the script aloud, leaving a 1-2 second pause between scenes.",
            "6. Hit **Stop Recording** when finished.",
            "7. Import the resulting OBS recording into DaVinci Resolve.",
            "",
            "## Background Music",
            "1. Go to the [YouTube Audio Library](https://studio.youtube.com/channel/UC/music).",
            "2. Download a cheerful, copyright-free track.",
            "3. Import it into DaVinci Resolve as your background track."
        ]
        
        from src.utils import save_text
        save_text(obs_guide_path, "\n".join(lines))
        logger.info(f"Generated OBS Recording Guide at {obs_guide_path}")

        return {
            "voice_manifest": str(obs_guide_path),
            "scene_count": len(scenes)
        }
