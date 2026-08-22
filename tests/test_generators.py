"""Tests for individual generator components (Script, Storyboard, Image, Voice, Thumbnail, Metadata)."""

import pytest
from pathlib import Path
from src.gemini_creator import GeminiCreativeDirector
from src.script_generator import ScriptGenerator
from src.storyboard_generator import StoryboardGenerator
from src.image_generator import ImageGenerator, PILComicProceduralProvider
from src.voice_generator import VoiceGenerator
from src.thumbnail_generator import ThumbnailGenerator
from src.youtube_metadata import YouTubeMetadataGenerator


@pytest.fixture
def mock_episode():
    director = GeminiCreativeDirector(api_key=None)
    topic = {
        "title": "Why Do We Need Trees?",
        "learning_objective": "Trees provide clean oxygen and homes for animals."
    }
    return director.create_episode(topic, "2026-08-22", mock=True)


def test_script_generator_markdown_output(mock_episode, tmp_path: Path):
    """Test generating and saving screenplay markdown."""
    script_path = tmp_path / "script.md"
    ScriptGenerator.save_script(mock_episode, script_path)

    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "Gigmo Giggles Screenplay" in content
    assert "Scene Breakdown" in content
    assert "Bobo" in content
    assert "Interactive Kid Quiz" in content


def test_storyboard_generator_output(mock_episode, tmp_path: Path):
    """Test generating and saving storyboard.json."""
    sb_path = tmp_path / "storyboard.json"
    StoryboardGenerator.save_storyboard(mock_episode, sb_path)

    assert sb_path.exists()
    import json
    with open(sb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["scenes_count"] >= 4
    assert len(data["scenes"]) >= 4
    assert "motion" in data["scenes"][0]


def test_image_generator_pil_comic_render(mock_episode, tmp_path: Path):
    """Test PIL comic image generator renders valid high-res PNG images."""
    img_dir = tmp_path / "images"
    img_gen = ImageGenerator(provider=PILComicProceduralProvider())
    result = img_gen.generate_all_scenes(mock_episode, img_dir)

    assert result["count"] >= 4
    scene_png = img_dir / "scene_01.png"
    assert scene_png.exists()
    assert scene_png.stat().st_size > 1000

    prompts_json = img_dir / "image_prompts.json"
    assert prompts_json.exists()


def test_voice_generator_audio_manifest(mock_episode, tmp_path: Path):
    """Test voice generator creates audio files and voice_manifest.json."""
    audio_dir = tmp_path / "audio"
    voice_gen = VoiceGenerator(enabled=True)
    result = voice_gen.generate_all_scene_audio(mock_episode, audio_dir)

    assert result["scene_count"] >= 4
    manifest_file = audio_dir / "voice_manifest.json"
    assert manifest_file.exists()

    scene_audio = audio_dir / "scene_01_audio.wav"
    assert scene_audio.exists()
    assert scene_audio.stat().st_size > 500


def test_thumbnail_generator_render(mock_episode, tmp_path: Path):
    """Test YouTube thumbnail generation and manifest."""
    thumb_dir = tmp_path / "thumbnail"
    thumb_path = ThumbnailGenerator.generate_thumbnail(mock_episode, thumb_dir)

    assert thumb_path.exists()
    assert thumb_path.name == "thumbnail.png"
    assert thumb_path.stat().st_size > 2000

    manifest = thumb_dir / "thumbnail_prompt.json"
    assert manifest.exists()


def test_youtube_metadata_generator(mock_episode, tmp_path: Path):
    """Test generating formatted YouTube metadata and chapter timestamps."""
    meta_path = tmp_path / "youtube_metadata.json"
    YouTubeMetadataGenerator.save_metadata(mock_episode, meta_path)

    assert meta_path.exists()
    import json
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert "video_metadata" in meta
    assert "chapters" in meta["video_metadata"]
    assert len(meta["video_metadata"]["chapters"]) >= 4
    assert meta["video_metadata"]["made_for_kids"] is True
