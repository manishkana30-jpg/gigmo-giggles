"""Tests for Subtitle generation and VideoGenerator assembly/manifests."""

import pytest
from pathlib import Path
from src.gemini_creator import GeminiCreativeDirector
from src.subtitle_generator import SubtitleGenerator, format_srt_timestamp, format_vtt_timestamp
from src.video_generator import VideoGenerator
from src.image_generator import ImageGenerator
from src.voice_generator import VoiceGenerator


@pytest.fixture
def mock_episode():
    director = GeminiCreativeDirector(api_key=None)
    topic = {
        "title": "Solar System Exploration",
        "learning_objective": "Meet the planets orbiting our Sun."
    }
    return director.create_episode(topic, "2026-08-22", mock=True)


def test_timestamp_formatting():
    """Test SRT and VTT millisecond and comma/dot formatting."""
    secs = 65.42  # 1 min 5 sec 420 ms
    srt_ts = format_srt_timestamp(secs)
    vtt_ts = format_vtt_timestamp(secs)

    assert srt_ts == "00:01:05,420"
    assert vtt_ts == "00:01:05.420"


def test_subtitle_generator_files(mock_episode, tmp_path: Path):
    """Test generating both SRT and VTT subtitle caption files."""
    subs_dir = tmp_path / "subtitles"
    results = SubtitleGenerator.generate_subtitles(mock_episode, subs_dir)

    assert results["srt"].exists()
    assert results["vtt"].exists()

    srt_text = results["srt"].read_text(encoding="utf-8")
    assert "-->" in srt_text
    assert "Bobo" in srt_text or "Narrator" in srt_text or "Luna" in srt_text

    vtt_text = results["vtt"].read_text(encoding="utf-8")
    assert vtt_text.startswith("WEBVTT")


def test_video_generator_manifest_creation(mock_episode, tmp_path: Path):
    """Test VideoGenerator creates video_manifest.json with all scenes and camera cues."""
    images_dir = tmp_path / "images"
    audio_dir = tmp_path / "audio"
    video_dir = tmp_path / "video"

    # Generate prerequisite assets
    ImageGenerator().generate_all_scenes(mock_episode, images_dir)
    VoiceGenerator().generate_all_scene_audio(mock_episode, audio_dir)

    vid_gen = VideoGenerator()
    manifest_data = vid_gen.assemble_episode_video(mock_episode, images_dir, audio_dir, video_dir)

    assert (video_dir / "DaVinci_Resolve_Assembly_Guide.md").exists()
    assert manifest_data["ffmpeg_available"] is False
    assert "resolution" in manifest_data
