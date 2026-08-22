"""Tests for canonical character consistency and appearance persistence."""

import pytest
from src.utils import get_project_root, load_json
from src.gemini_creator import GeminiCreativeDirector


def test_canonical_characters_configuration():
    """Verify Bobo, Luna, and Milo are configured with canonical visual descriptions."""
    root = get_project_root()
    char_file = root / "config" / "characters.json"
    assert char_file.exists()

    characters = load_json(char_file)
    char_names = {c["name"] for c in characters}
    assert "Bobo" in char_names
    assert "Luna" in char_names
    assert "Milo" in char_names

    for char in characters:
        assert "canonical_visual_description" in char
        assert "voice_style" in char
        assert len(char["canonical_visual_description"]) > 20


def test_gemini_creator_injects_character_canonical_descriptions():
    """Test that the system prompt automatically embeds canonical character specs."""
    director = GeminiCreativeDirector(api_key=None)
    system_prompt = director._build_system_prompt()

    assert "Bobo" in system_prompt
    assert "honey-brown" in system_prompt
    assert "yellow neckerchief" in system_prompt
    assert "Luna" in system_prompt
    assert "teal" in system_prompt or "fox" in system_prompt
    assert "Milo" in system_prompt
    assert "robot" in system_prompt
