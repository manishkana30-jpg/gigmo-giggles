"""Tests for safety validator and quality gate validation."""

import pytest
from pathlib import Path
from src.validator import SafetyValidator, QualityGateValidator


def test_safety_scanner_detects_prohibited_terms():
    """Test that violent, scary, or inappropriate keywords are flagged."""
    bad_text = "The character decided to use a weapon to fight and kill the monster in blood."
    violations = SafetyValidator.scan_text(bad_text)
    assert len(violations) >= 3


def test_safety_scanner_detects_dangerous_instructions():
    """Test that hazardous activities kids might imitate are caught."""
    dangerous_text = "Let's go play with matches and touch an electrical outlet!"
    violations = SafetyValidator.scan_text(dangerous_text)
    assert len(violations) >= 2


def test_safe_content_passes_cleanly():
    """Test that wholesome educational content returns zero violations."""
    clean_text = "Bobo the friendly bear shared a juicy red apple with Luna under the sunny tree."
    violations = SafetyValidator.scan_text(clean_text)
    assert len(violations) == 0


def test_episode_dict_safety_validation():
    """Test validation of a complete episode data structure."""
    safe_episode = {
        "topic": "Why Does Rain Happen?",
        "learning_objective": "Learn how water evaporates into clouds.",
        "title": "Rainy Day Fun with Bobo!",
        "scenes": [
            {
                "scene_number": 1,
                "action": "Bobo holds a colorful umbrella.",
                "dialogue": [{"character": "Bobo", "text": "Look at the raindrops!"}],
                "image_prompt": "Friendly bear in cartoon rain.",
                "voice_direction": "Happy"
            }
        ],
        "quiz": [{"question": "Where does rain come from?", "explanation": "From clouds in the sky!"}],
        "youtube": {"title": "Rain Science", "description": "Educational kids video."},
        "thumbnail": {"prompt": "Cartoon bear with umbrella."}
    }
    is_safe, violations = SafetyValidator.validate_safety(safe_episode)
    assert is_safe
    assert len(violations) == 0

    # Inject unsafe text into scene dialogue
    unsafe_episode = dict(safe_episode)
    unsafe_episode["scenes"] = [
        {
            "scene_number": 1,
            "action": "Fighting scene",
            "dialogue": [{"character": "Bobo", "text": "I will shoot and kill with a gun!"}],
            "image_prompt": "Bear with a weapon.",
            "voice_direction": "Violent"
        }
    ]
    is_safe_2, violations_2 = SafetyValidator.validate_safety(unsafe_episode)
    assert not is_safe_2
    assert len(violations_2) > 0


def test_quality_gate_checks(tmp_path: Path):
    """Test quality gate missing files vs complete files."""
    episode_dir = tmp_path / "episodes" / "2026-08-22"
    episode_dir.mkdir(parents=True)

    dummy_episode_data = {
        "topic": "Shapes",
        "scenes": [
            {"scene_number": 1}, {"scene_number": 2},
            {"scene_number": 3}, {"scene_number": 4}
        ]
    }

    # Initially missing all files -> should fail
    passed, issues = QualityGateValidator.check_quality_gate(episode_dir, dummy_episode_data)
    assert not passed
    assert len(issues) > 0

    # Create all required files
    (episode_dir / "episode.json").write_text("{}", encoding="utf-8")
    (episode_dir / "script.md").write_text("# Script", encoding="utf-8")
    (episode_dir / "storyboard.json").write_text("{}", encoding="utf-8")
    (episode_dir / "youtube_metadata.json").write_text("{}", encoding="utf-8")

    (episode_dir / "images").mkdir()
    (episode_dir / "images" / "image_prompts.json").write_text("[]", encoding="utf-8")

    (episode_dir / "audio").mkdir()
    (episode_dir / "audio" / "voice_manifest.json").write_text("{}", encoding="utf-8")

    (episode_dir / "subtitles").mkdir()
    (episode_dir / "subtitles" / "episode.srt").write_text("1\n00:00:00,000 --> 00:00:05,000\nHello", encoding="utf-8")
    (episode_dir / "subtitles" / "episode.vtt").write_text("WEBVTT\n", encoding="utf-8")

    (episode_dir / "video").mkdir()
    (episode_dir / "video" / "video_manifest.json").write_text("{}", encoding="utf-8")

    (episode_dir / "thumbnail").mkdir()
    (episode_dir / "thumbnail" / "thumbnail_prompt.json").write_text("{}", encoding="utf-8")

    # Now all files and manifests exist
    passed_clean, issues_clean = QualityGateValidator.check_quality_gate(episode_dir, dummy_episode_data)
    assert passed_clean
    assert len(issues_clean) == 0
