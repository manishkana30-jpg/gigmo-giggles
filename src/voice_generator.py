"""Character Voice and Text-to-Speech (TTS) generator."""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import save_json, generate_simple_tone_wav, generate_melodic_chime_wav, check_ffmpeg_available, setup_logger, get_project_root, load_json

logger = setup_logger("VoiceGenerator")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not installed. Will use procedural audio tone generator for testing.")


class VoiceGenerator:
    """Generates audio speech tracks for characters with fallback manifest logging."""

    # Character voice profiles with pitch/speed adjustments for differentiation
    CHARACTER_PROFILES = {
        "Jack": {
            "pitch_hz": 340.0,
            "tone": "adventurous_boy",
            "gtts_tld": "co.in",
            "speed_factor": 1.0,
            "pitch_semitones": 2,      # Slightly higher for young boy
        },
        "Jill": {
            "pitch_hz": 440.0,
            "tone": "cheerful_girl",
            "gtts_tld": "co.in",
            "speed_factor": 0.95,     # Slightly slower for warm tone
            "pitch_semitones": 4,      # Higher pitch for young girl
        },
        "Narrator": {
            "pitch_hz": 350.0,
            "tone": "narrator",
            "gtts_tld": "co.in",
            "speed_factor": 0.90,     # Slightly slower for children
            "pitch_semitones": 0,
        }
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.ffmpeg_available = check_ffmpeg_available()
        root = get_project_root()
        self.settings = load_json(root / "config" / "settings.json")
        self.language_setting = self.settings.get("spoken_language", "English").lower()
        self.gtts_lang = "hi" if "hindi" in self.language_setting else "en"

    def _convert_mp3_to_wav(self, mp3_path: Path, wav_path: Path, character: str = "Narrator") -> bool:
        """Convert MP3 to WAV using FFmpeg with character-specific voice adjustments."""
        if not self.ffmpeg_available:
            return False

        profile = self.CHARACTER_PROFILES.get(character, self.CHARACTER_PROFILES["Narrator"])
        speed = profile.get("speed_factor", 1.0)
        semitones = profile.get("pitch_semitones", 0)

        # Build audio filter chain for character differentiation
        filters = []

        # Pitch shift using asetrate + aresample (shift pitch without changing speed)
        if semitones != 0:
            # Calculate pitch multiplier from semitones
            pitch_mult = 2.0 ** (semitones / 12.0)
            new_rate = int(24000 * pitch_mult)
            filters.append(f"asetrate={new_rate}")
            filters.append("aresample=24000")

        # Speed adjustment using atempo
        if speed != 1.0:
            # atempo only accepts 0.5-2.0 range
            clamped_speed = max(0.5, min(2.0, speed))
            filters.append(f"atempo={clamped_speed}")

        # Normalize volume
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

        filter_str = ",".join(filters) if filters else "anull"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(mp3_path),
            "-af", filter_str,
            "-ar", "44100",
            "-ac", "1",
            "-sample_fmt", "s16",
            str(wav_path)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if res.returncode == 0 and wav_path.exists():
                # Clean up mp3
                mp3_path.unlink(missing_ok=True)
                # Add 400ms silence padding for smooth scene transitions
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_wav(str(wav_path))
                    silence = AudioSegment.silent(duration=400)
                    padded = silence + audio + silence
                    padded.export(str(wav_path), format="wav")
                except Exception as pad_err:
                    logger.warning(f"Silence padding skipped: {pad_err}")
                return True
            else:
                logger.warning(f"FFmpeg MP3→WAV conversion failed (exit {res.returncode})")
                return False
        except Exception as e:
            logger.warning(f"FFmpeg MP3→WAV conversion error: {e}")
            return False

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
                # Generate TTS as MP3 first
                tts_mp3_path = output_path.with_suffix(".mp3")
                tts = gTTS(text=text, lang=self.gtts_lang, tld=char_profile.get("gtts_tld", "com"), slow=False)
                tts.save(str(tts_mp3_path))

                # Convert MP3 → WAV with character voice adjustments
                wav_target = output_path.with_suffix(".wav") if output_path.suffix.lower() != ".wav" else output_path
                converted = self._convert_mp3_to_wav(tts_mp3_path, wav_target, character)

                if converted:
                    logger.info(f"Generated TTS speech for [{character}]: {wav_target.name}")
                    # If the caller wanted a different extension, rename
                    if output_path != wav_target and not output_path.exists():
                        wav_target.rename(output_path)
                    return True
                else:
                    # FFmpeg not available — keep the MP3 and also create WAV from it directly
                    # At minimum, rename mp3 if target is wav (lossy but better than beep)
                    if output_path.suffix.lower() == ".wav" and tts_mp3_path.exists():
                        # Last resort: just copy mp3 bytes as the output
                        # FFmpeg unavailable means we can't do proper conversion
                        # But at least we try to use the mp3 directly
                        import shutil
                        shutil.copy2(str(tts_mp3_path), str(output_path))
                        logger.info(f"Generated TTS speech (MP3 as WAV fallback) for [{character}]: {output_path.name}")
                        return True
                    logger.info(f"Generated TTS speech for [{character}]: {tts_mp3_path.name}")
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

        # Generate background cheerful music loop (longer for full episode)
        total_duration = sum(float(s.get("duration_seconds", 15)) for s in scenes)
        bg_music_path = output_dir / "background_music.wav"
        generate_melodic_chime_wav(bg_music_path, duration_sec=max(total_duration, 30.0))

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
                combined_text = ". ".join([f"{d.get('translated_text') or d.get('text')}" for d in dialogue_lines])
                primary_char = dialogue_lines[0].get("character", "Jack")
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
                narr_text = scene.get("translated_narration") or narration
                self.generate_speech(narr_text, "Narrator", scene_audio_path, duration_sec=duration)
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
