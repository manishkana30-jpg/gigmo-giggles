"""Tests for canonical character consistency and appearance persistence."""

import pytest
from src.utils import get_project_root, load_json
from src.gemini_creator import GeminiCreativeDirector


def test_canonical_characters_configuration():
    """Verify Jack and Jill are configured with canonical visual descriptions."""
    root = get_project_root()
    char_file = root / "config" / "characters.json"
    assert char_file.exists()

    characters = load_json(char_file)
    char_names = {c["name"] for c in characters}
    assert "Jack" in char_names
    assert "Jill" in char_names

    for char in characters:
        assert "canonical_visual_description" in char
        assert "voice_style" in char
        assert len(char["canonical_visual_description"]) > 20


def test_gemini_creator_injects_character_canonical_descriptions():
    """Test that the system prompt automatically embeds canonical character specs."""
    director = GeminiCreativeDirector(api_key=None)
    system_prompt = director._build_system_prompt()

    assert "Jack" in system_prompt
    assert "orange cap" in system_prompt
    assert "green shorts" in system_prompt
    assert "Jill" in system_prompt
    assert "red bow headband" in system_prompt
