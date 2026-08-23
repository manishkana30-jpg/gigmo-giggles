"""Automatic subtitle generator creating SRT and VTT formats."""

from pathlib import Path
from typing import Dict, Any, List
from src.utils import save_text, setup_logger

logger = setup_logger("SubtitleGenerator")


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp string HH:MM:SS,mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """Format seconds into WebVTT timestamp string HH:MM:SS.mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


class SubtitleGenerator:
    """Generates child-friendly, synchronized SRT and VTT subtitle files."""

    @classmethod
    def generate_subtitles(cls, episode_data: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
        """
        Generate episode.srt and episode.vtt from episode scenes and dialogue.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])

        srt_entries = []
        vtt_entries = ["WEBVTT\nKind: captions\nLanguage: en\n"]

        entry_index = 1
        current_time = 0.0

        for scene in scenes:
            scene_duration = float(scene.get("duration_seconds", 15))
            dialogues = scene.get("dialogue", [])
            narration = scene.get("narration", "")

            if dialogues:
                line_duration = scene_duration / len(dialogues)
                for line in dialogues:
                    start_t = current_time
                    end_t = start_t + line_duration
                    char = line.get("character", "Jack")
                    text = line.get("text", "")
                    subtitle_text = f"{char}: {text}"

                    # SRT entry
                    srt_entries.append(
                        f"{entry_index}\n"
                        f"{format_srt_timestamp(start_t)} --> {format_srt_timestamp(end_t)}\n"
                        f"{subtitle_text}\n"
                    )

                    # VTT entry
                    vtt_entries.append(
                        f"{entry_index}\n"
                        f"{format_vtt_timestamp(start_t)} --> {format_vtt_timestamp(end_t)}\n"
                        f"{subtitle_text}\n"
                    )

                    entry_index += 1
                    current_time = end_t
            elif narration:
                start_t = current_time
                end_t = start_t + scene_duration
                subtitle_text = narration

                srt_entries.append(
                    f"{entry_index}\n"
                    f"{format_srt_timestamp(start_t)} --> {format_srt_timestamp(end_t)}\n"
                    f"{subtitle_text}\n"
                )
                vtt_entries.append(
                    f"{entry_index}\n"
                    f"{format_vtt_timestamp(start_t)} --> {format_vtt_timestamp(end_t)}\n"
                    f"{subtitle_text}\n"
                )
                entry_index += 1
                current_time = end_t
            else:
                current_time += scene_duration

        srt_path = output_dir / "episode.srt"
        vtt_path = output_dir / "episode.vtt"

        save_text(srt_path, "\n".join(srt_entries))
        save_text(vtt_path, "\n".join(vtt_entries))

        logger.info(f"Generated subtitles: {srt_path.name} and {vtt_path.name}")
        return {"srt": srt_path, "vtt": vtt_path}
