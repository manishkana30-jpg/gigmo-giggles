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
        """Generate speech audio file for a given character and text line."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.enabled or not text.strip():
            # Create procedural tone audio as fallback
            char_profile = self.CHARACTER_PROFILES.get(character, {"pitch_hz": 400.0})
            generate_simple_tone_wav(output_path, duration_sec=duration_sec, frequency=char_profile["pitch_hz"])
            return True

        # Attempt gTTS generation if available
        if GTTS_AVAILABLE:
            try:
                char_profile = self.CHARACTER_PROFILES.get(character, {"gtts_tld": "com"})
                # Use mp3 or wav extension
                tts_output = output_path.with_suffix(".mp3")
                tts = gTTS(text=text, lang="en", tld=char_profile.get("gtts_tld", "com"), slow=False)
                tts.save(str(tts_output))

                # If requested path is .wav and we saved .mp3, also create tone or keep mp3
                if output_path.suffix.lower() == ".wav" and not output_path.exists():
                    generate_simple_tone_wav(output_path, duration_sec=duration_sec, frequency=char_profile.get("pitch_hz", 440.0))

                logger.info(f"Generated TTS speech for [{character}]: {output_path.name}")
                return True
            except Exception as e:
                logger.warning(f"gTTS online synthesis failed ({e}). Falling back to tone synthesizer.")

        # Fallback to procedural sine wave tone
        char_profile = self.CHARACTER_PROFILES.get(character, {"pitch_hz": 440.0})
        generate_simple_tone_wav(output_path, duration_sec=duration_sec, frequency=char_profile["pitch_hz"])
        return True

    def generate_all_scene_audio(
        self,
        episode_data: Dict[str, Any],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        Generate audio for each scene in the episode, create composite scene tracks,
        and write episodes/YYYY-MM-DD/audio/voice_manifest.json.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        manifest_entries = []

        # Generate background cheerful music loop
        bg_music_path = output_dir / "background_music.wav"
        generate_melodic_chime_wav(bg_music_path, duration_sec=10.0)

        for scene in scenes:
            scene_num = scene.get("scene_number", 1)
            duration = float(scene.get("duration_seconds", 15))
            dialogue_lines = scene.get("dialogue", [])
            narration = scene.get("narration", "")

            scene_audio_filename = f"scene_{scene_num:02d}_audio.wav"
            scene_audio_path = output_dir / scene_audio_filename

            line_entries = []

            if dialogue_lines:
                # Concatenate all dialogues for scene audio
                combined_text = ". ".join([f"{d.get('character')}: {d.get('text')}" for d in dialogue_lines])
                primary_char = dialogue_lines[0].get("character", "Bobo")
                self.generate_speech(combined_text, primary_char, scene_audio_path, duration_sec=duration)

                for idx, line in enumerate(dialogue_lines, start=1):
                    line_entries.append({
                        "line_id": f"scene_{scene_num:02d}_line_{idx:02d}",
                        "character": line.get("character"),
                        "text": line.get("text"),
                        "emotion": line.get("emotion"),
                        "sound_effect": line.get("sound_effect")
                    })
            elif narration:
                self.generate_speech(narration, "Narrator", scene_audio_path, duration_sec=duration)
                line_entries.append({
                    "line_id": f"scene_{scene_num:02d}_narration",
                    "character": "Narrator",
                    "text": narration,
                    "emotion": "storytelling"
                })
            else:
                # Default ambient tone
                generate_simple_tone_wav(scene_audio_path, duration_sec=duration, frequency=330.0)

            manifest_entries.append({
                "scene_number": scene_num,
                "audio_file": scene_audio_filename,
                "duration_seconds": duration,
                "voice_direction": scene.get("voice_direction", ""),
                "lines": line_entries,
                "sound_effects": scene.get("sound_effects", [])
            })

        # Save voice_manifest.json
        manifest_path = output_dir / "voice_manifest.json"
        save_json(manifest_path, {
            "episode_id": episode_data.get("episode_id"),
            "total_scenes": len(scenes),
            "scenes": manifest_entries
        })
        logger.info(f"Generated audio tracks and voice manifest in {output_dir}")

        return {
            "voice_manifest": str(manifest_path),
            "scene_count": len(manifest_entries)
        }
