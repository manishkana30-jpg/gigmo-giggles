"""End-to-end integration tests for the full daily episode pipeline."""

import pytest
from pathlib import Path
from src.main import run_pipeline
from src.utils import load_json


def test_full_pipeline_mock_run(tmp_path: Path, monkeypatch):
    """
    Execute the entire automated pipeline end-to-end in offline mock mode.
    Validates that every single artifact is created and run_status.json reports success.
    """
    # Mock LipsyncGenerator to prevent running Blender in tests (saves runner time)
    from src.lipsync_generator import LipsyncGenerator
    def mock_render(audio_path, output_path, duration_sec):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return True
    monkeypatch.setattr(LipsyncGenerator, "generate_3d_lipsync_clip", mock_render)

    episode_dir = tmp_path / "episodes" / "2026-08-22"

    result = run_pipeline(
        forced_topic="Why Does Rain Happen?",
        date_str="2026-08-22",
        mock_mode=True,
        custom_output_dir=episode_dir
    )

    assert result["status"] == "success"
    assert "topic" in result["completed"]
    assert "creative_direction" in result["completed"]
    assert "script" in result["completed"]
    assert "storyboard" in result["completed"]
    assert "images" in result["completed"]
    assert "audio" in result["completed"]
    assert "subtitles" in result["completed"]
    assert "video" in result["completed"]
    assert "thumbnail" in result["completed"]
    assert "metadata" in result["completed"]

    # Verify generated files on disk
    assert (episode_dir / "episode.json").exists()
    assert (episode_dir / "script.md").exists()
    assert (episode_dir / "storyboard.json").exists()
    assert (episode_dir / "youtube_metadata.json").exists()
    assert (episode_dir / "run_status.json").exists()

    assert (episode_dir / "images" / "image_prompts.json").exists()
    assert (episode_dir / "images" / "scene_01.png").exists()

    assert (episode_dir / "audio" / "voice_manifest.json").exists()
    assert (episode_dir / "audio" / "scene_01_audio.wav").exists()

    assert (episode_dir / "subtitles" / "episode.srt").exists()
    assert (episode_dir / "subtitles" / "episode.vtt").exists()

    assert (episode_dir / "thumbnail" / "thumbnail.png").exists()
    assert (episode_dir / "thumbnail" / "thumbnail_prompt.json").exists()

    assert (episode_dir / "video" / "video_manifest.json").exists()

    # Check status file content
    status_on_disk = load_json(episode_dir / "run_status.json")
    assert status_on_disk["status"] == "success"
    assert status_on_disk["finished_at"] is not None


def test_pipeline_failure_resilience_records_partial_status(tmp_path: Path, monkeypatch):
    """
    Test that when an intermediate step raises an exception,
    run_status.json records status='partial' and stores the error trace without data loss.
    """
    episode_dir = tmp_path / "episodes" / "2026-08-23"

    # Inject an intentional failure in SubtitleGenerator
    from src.subtitle_generator import SubtitleGenerator

    def mock_broken_subtitles(*args, **kwargs):
        raise RuntimeError("Simulated Subtitle Generation Failure")

    monkeypatch.setattr(SubtitleGenerator, "generate_subtitles", mock_broken_subtitles)

    result = run_pipeline(
        forced_topic="Animals and Habitats",
        date_str="2026-08-23",
        mock_mode=True,
        custom_output_dir=episode_dir
    )

    assert result["status"] in ["partial", "failed"]
    assert "Simulated Subtitle Generation Failure" in str(result["error"])

    # Verify that prior generated assets (script, storyboard, images, audio) were preserved on disk
    assert (episode_dir / "script.md").exists()
    assert (episode_dir / "storyboard.json").exists()
    assert (episode_dir / "images" / "scene_01.png").exists()
    assert (episode_dir / "audio" / "scene_01_audio.wav").exists()
