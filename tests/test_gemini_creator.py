"""Tests for Gemini Creative Director and JSON parsing/repair."""

import pytest
from unittest.mock import MagicMock, patch
from src.gemini_creator import GeminiCreativeDirector
from src.validator import EpisodeSchema


@pytest.fixture
def sample_topic():
    return {
        "id": "topic_test_01",
        "title": "Why Is the Sky Blue?",
        "category": "Science",
        "learning_objective": "Understand how sunlight scatters through Earth's atmosphere.",
        "target_age": "6-9",
        "keywords": ["sky", "sunlight", "blue", "atmosphere"]
    }


def test_missing_api_key_graceful_handling(monkeypatch):
    """Test that missing GEMINI_API_KEY does not crash initialization and falls back cleanly."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    director = GeminiCreativeDirector(api_key=None)
    assert not director.is_live_ready()


def test_mock_episode_generation(sample_topic):
    """Test that offline/mock generation produces schema-compliant episode data."""
    director = GeminiCreativeDirector(api_key=None)
    episode = director.create_episode(topic=sample_topic, date_str="2026-08-22", mock=True)

    assert episode["episode_id"] == "2026-08-22-why-is-the-sky-blue"
    assert episode["topic"] == "Why Is the Sky Blue?"
    assert len(episode["scenes"]) >= 4
    assert len(episode["quiz"]) >= 1
    assert "youtube" in episode
    assert "thumbnail" in episode

    # Validate with Pydantic
    validated = EpisodeSchema(**episode)
    assert validated.episode_id == episode["episode_id"]


def test_clean_and_parse_json_markdown_stripping():
    """Test that markdown code blocks (```json ... ```) are stripped cleanly."""
    director = GeminiCreativeDirector(api_key=None)
    raw_response = """
```json
{
  "test_key": "test_value"
}
```
"""
    parsed = director._clean_and_parse_json(raw_response)
    assert parsed == {"test_key": "test_value"}


def test_live_gemini_mocked_success(sample_topic):
    """Test live generation workflow when Gemini API returns valid JSON."""
    director = GeminiCreativeDirector(api_key="fake-test-key")
    director.client = MagicMock()

    mock_json_str = """{
      "episode_id": "2026-08-22-test",
      "topic": "Why Is the Sky Blue?",
      "learning_objective": "Light scattering",
      "target_age": "6-9",
      "title": "Why Is the Sky Blue? ☀️",
      "characters": [{"name": "Bobo", "role": "Explorer"}],
      "scenes": [
        {
          "scene_number": 1,
          "duration_seconds": 15,
          "location": "Meadow",
          "action": "Bobo looks up",
          "dialogue": [{"character": "Bobo", "text": "Look at that blue sky!"}],
          "image_prompt": "Bobo looking at blue sky",
          "video_prompt": "Zoom in",
          "voice_direction": "Happy",
          "sound_effects": ["birds"]
        },
        {
          "scene_number": 2,
          "duration_seconds": 15,
          "location": "Treehouse",
          "action": "Luna shows a prism",
          "dialogue": [{"character": "Luna", "text": "Sunlight has all the colors!"}],
          "image_prompt": "Luna with rainbow prism",
          "video_prompt": "Pan left",
          "voice_direction": "Clever",
          "sound_effects": ["chime"]
        },
        {
          "scene_number": 3,
          "duration_seconds": 15,
          "location": "Treehouse",
          "action": "Milo calculates",
          "dialogue": [{"character": "Milo", "text": "Blue light scatters the most!"}],
          "image_prompt": "Milo pointing at screen",
          "video_prompt": "Zoom in",
          "voice_direction": "Robot cheer",
          "sound_effects": ["beep"]
        },
        {
          "scene_number": 4,
          "duration_seconds": 15,
          "location": "Quiz Studio",
          "action": "Friends wave",
          "dialogue": [{"character": "Bobo", "text": "Ready for the quiz?"}],
          "image_prompt": "Friends waving",
          "video_prompt": "Static",
          "voice_direction": "Excited",
          "sound_effects": ["drumroll"]
        }
      ],
      "quiz": [
        {
          "question": "Why is the sky blue?",
          "options": ["A) Blue light scatters", "B) Ocean paint"],
          "correct_answer": "A) Blue light scatters",
          "explanation": "Blue light scatters in all directions."
        }
      ],
      "youtube": {
        "title": "Why Is the Sky Blue?",
        "description": "Fun science episode for children.",
        "tags": ["sky", "science", "kids learning"]
      },
      "thumbnail": {
        "prompt": "Bobo smiling at blue sky",
        "overlay_text": "WHY IS THE SKY BLUE?"
      },
      "shorts": []
    }"""

    mock_resp = MagicMock()
    mock_resp.text = mock_json_str
    director.client.models.generate_content.return_value = mock_resp

    result = director.create_episode(topic=sample_topic, date_str="2026-08-22", mock=False)
    assert result["title"] == "Why Is the Sky Blue? ☀️"
    assert len(result["scenes"]) == 4
