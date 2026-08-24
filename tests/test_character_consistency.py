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
    assert "brown tousled hair" in system_prompt
    assert "Jill" in system_prompt
    assert "braided pigtails" in system_prompt


def test_image_generator_prompt_enhancement():
    """Test that ImageGenerator correctly embeds exact character expression descriptions in image prompts."""
    from src.image_generator import ImageGenerator
    img_gen = ImageGenerator()
    
    context = {
        "dialogue": [
            {"character": "Jack", "text": "Wow!", "emotion": "wink"},
            {"character": "Jill", "text": "Hahaha!", "emotion": "laugh"}
        ]
    }
    
    prompt = "Jack and Jill stand near the bridge."
    enhanced = img_gen._enhance_prompt_with_expressions(prompt, context)
    
    assert "winking one eye cheekily" in enhanced
    assert "winking one eye cheerfully" in enhanced or "Playful Wink" in enhanced
