"""Validation and Content Safety for Gigmo Giggles YouTube Automation."""

import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Pydantic Schemas for Structured Episode JSON
# ============================================================================

class CharacterEntry(BaseModel):
    name: str = Field(..., description="Character name e.g. Bobo, Luna, Milo")
    role: Optional[str] = Field(default="Main Cast", description="Role in the episode")


class DialogueLine(BaseModel):
    character: str = Field(..., description="Name of speaking character")
    text: str = Field(..., description="Spoken dialogue line")
    translated_text: Optional[str] = Field(default="", description="Spoken dialogue line translated to the spoken_language")
    emotion: Optional[str] = Field(default="happy", description="Emotional tone")
    sound_effect: Optional[str] = Field(default=None, description="Accompanying SFX")


class SceneModel(BaseModel):
    scene_number: int = Field(..., ge=1, description="1-indexed scene number")
    duration_seconds: int = Field(default=15, ge=3, le=60, description="Duration in seconds")
    location: str = Field(..., description="Scene background/location")
    action: str = Field(..., description="Visual action happening in scene")
    narration: Optional[str] = Field(default="", description="Optional narrator line")
    translated_narration: Optional[str] = Field(default="", description="Optional narrator line translated to the spoken_language")
    dialogue: List[DialogueLine] = Field(default_factory=list, description="Character dialogues")
    image_prompt: str = Field(..., description="Prompt for 2D cartoon image generator")
    video_prompt: Optional[str] = Field(default="", description="Ken Burns / motion camera instructions")
    voice_direction: Optional[str] = Field(default="", description="Voice acting directions")
    sound_effects: List[str] = Field(default_factory=list, description="Suggested sound effects")


class QuizItem(BaseModel):
    question: str = Field(..., description="Child-friendly question")
    options: List[str] = Field(..., min_length=2, description="Multiple choice options")
    correct_answer: str = Field(..., description="Correct answer text or option")
    explanation: str = Field(..., description="Simple warm explanation")


class YouTubeMetadataModel(BaseModel):
    title: str = Field(..., min_length=5, max_length=100, description="YouTube Video Title")
    description: str = Field(..., min_length=20, description="YouTube Description")
    tags: List[str] = Field(default_factory=list, min_length=3, description="SEO tags")
    hashtags: List[str] = Field(default_factory=list, description="Hashtags for description")
    category: str = Field(default="Education", description="Video Category")
    target_audience: str = Field(default="Children (Made for Kids)", description="Target Audience")


class ThumbnailModel(BaseModel):
    prompt: str = Field(..., description="Image generation prompt for thumbnail")
    overlay_text: Optional[str] = Field(default="", max_length=30, description="Punchy thumbnail text")


class ShortItem(BaseModel):
    title: str = Field(..., description="Short video title")
    hook: str = Field(..., description="Engaging hook statement")
    scene_reference: Optional[int] = Field(default=1, description="Associated scene number")
    duration_seconds: Optional[int] = Field(default=30, description="Duration of short")


class EpisodeSchema(BaseModel):
    episode_id: str = Field(..., description="Unique episode identifier YYYY-MM-DD-slug")
    topic: str = Field(..., description="Primary educational topic")
    learning_objective: str = Field(..., description="Core learning takeaway")
    target_age: str = Field(default="6-9", description="Target child age group")
    title: str = Field(..., min_length=5, description="Episode title")
    characters: List[CharacterEntry] = Field(default_factory=list, min_length=1)
    scenes: List[SceneModel] = Field(..., min_length=4, max_length=20)
    quiz: List[QuizItem] = Field(default_factory=list, min_length=1)
    youtube: YouTubeMetadataModel
    thumbnail: Optional[ThumbnailModel] = None
    shorts: List[ShortItem] = Field(default_factory=list)

    @field_validator("scenes")
    @classmethod
    def validate_scenes_order(cls, scenes: List[SceneModel]) -> List[SceneModel]:
        for idx, scene in enumerate(scenes, start=1):
            if scene.scene_number != idx:
                scene.scene_number = idx
        return scenes


# ============================================================================
# Content Safety & Quality Validator
# ============================================================================

class SafetyValidator:
    """Validates that all content is 100% safe, educational, and appropriate for children."""

    # Prohibited patterns and forbidden themes
    FORBIDDEN_KEYWORDS = [
        r"\bkill\b", r"\bmurder\b", r"\bblood\b", r"\bgore\b", r"\bdeath\b",
        r"\bweapon\b", r"\bgun\b", r"\bknife\b", r"\bsword\b", r"\bbomb\b",
        r"\bshoot\b", r"\bpoison\b", r"\bdrug\b", r"\balcohol\b", r"\bbeer\b",
        r"\bwine\b", r"\bcigarette\b", r"\btobacco\b", r"\bswear\b", r"\bdamn\b",
        r"\bhell\b", r"\bsexy?\b", r"\bnude\b", r"\bnaked\b", r"\bhorror\b",
        r"\bdemon\b", r"\bterrif(ied|ying)\b", r"\bnightmare\b", r"\bhate\b",
        r"\bracis(t|m)\b", r"\bsuicide\b", r"\bself-harm\b"
    ]

    # Dangerous instructions that kids might imitate
    DANGEROUS_PATTERNS = [
        r"\bplay(ing)? with fire\b",
        r"\bplay(ing)? with matches\b",
        r"\btouch(ing)? (an )?electrical (outlet|socket|wire)\b",
        r"\bdrink(ing)? bleach\b",
        r"\bswallow(ing)? (chemicals|pills|battery)\b",
        r"\bjump(ing)? off (the )?roof\b",
        r"\brun(ning)? into (the )?street\b"
    ]

    @classmethod
    def scan_text(cls, text: str) -> List[str]:
        """Scan a text string for safety violations. Returns list of violation reasons."""
        violations = []
        lower_text = text.lower()

        # Check forbidden keywords
        for pattern in cls.FORBIDDEN_KEYWORDS:
            if re.search(pattern, lower_text, re.IGNORECASE):
                match = re.search(pattern, lower_text, re.IGNORECASE).group(0)
                violations.append(f"Forbidden term detected: '{match}'")

        # Check dangerous imitation patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, lower_text, re.IGNORECASE):
                match = re.search(pattern, lower_text, re.IGNORECASE).group(0)
                violations.append(f"Dangerous action pattern detected: '{match}'")

        return violations

    @classmethod
    def validate_safety(cls, episode_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate all fields of an episode dictionary for child safety.
        Returns (is_safe, list_of_violations).
        """
        all_violations = []

        # Check top-level strings
        for field in ["topic", "learning_objective", "title"]:
            val = episode_data.get(field, "")
            if isinstance(val, str):
                v = cls.scan_text(val)
                if v:
                    all_violations.extend([f"[{field}] {item}" for item in v])

        # Check scenes (dialogue, action, narration, image_prompt, voice_direction)
        scenes = episode_data.get("scenes", [])
        for scene in scenes:
            scene_num = scene.get("scene_number", "?")
            for field in ["action", "narration", "image_prompt", "voice_direction"]:
                val = scene.get(field, "")
                if isinstance(val, str):
                    v = cls.scan_text(val)
                    if v:
                        all_violations.extend([f"[Scene {scene_num} {field}] {item}" for item in v])

            # Check dialogue lines
            for dial in scene.get("dialogue", []):
                text = dial.get("text", "")
                v = cls.scan_text(text)
                if v:
                    all_violations.extend([f"[Scene {scene_num} Dialogue - {dial.get('character')}] {item}" for item in v])

        # Check quiz
        for idx, q in enumerate(episode_data.get("quiz", []), start=1):
            for field in ["question", "explanation", "correct_answer"]:
                val = q.get(field, "")
                v = cls.scan_text(val)
                if v:
                    all_violations.extend([f"[Quiz {idx} {field}] {item}" for item in v])

        # Check YouTube metadata
        yt = episode_data.get("youtube", {})
        for field in ["title", "description"]:
            val = yt.get(field, "")
            v = cls.scan_text(val)
            if v:
                all_violations.extend([f"[YouTube {field}] {item}" for item in v])

        # Check thumbnail
        thumb = episode_data.get("thumbnail", {})
        if isinstance(thumb, dict):
            for field in ["prompt", "overlay_text"]:
                val = thumb.get(field, "")
                v = cls.scan_text(val)
                if v:
                    all_violations.extend([f"[Thumbnail {field}] {item}" for item in v])

        is_safe = len(all_violations) == 0
        return is_safe, all_violations


class QualityGateValidator:
    """Verifies that all required artifacts for an episode exist and are complete."""

    @classmethod
    def check_quality_gate(cls, episode_dir: Path, episode_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Verify all required files and specifications exist before marking the run as success.
        """
        issues = []

        # 1. Check core json and markdown files
        required_files = [
            episode_dir / "episode.json",
            episode_dir / "script.md",
            episode_dir / "storyboard.json",
            episode_dir / "youtube_metadata.json"
        ]
        for req_file in required_files:
            if not req_file.exists() or req_file.stat().st_size == 0:
                issues.append(f"Missing or empty required file: {req_file.name}")

        # 2. Check scenes completeness
        scenes = episode_data.get("scenes", [])
        if len(scenes) < 4:
            issues.append(f"Episode contains too few scenes: {len(scenes)} (minimum 4 required)")

        # 3. Check images / prompts
        images_dir = episode_dir / "images"
        if not images_dir.exists():
            issues.append("Images directory does not exist")
        else:
            image_files = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
            prompts_manifest = images_dir / "image_prompts.json"
            if not image_files and not prompts_manifest.exists():
                issues.append("Neither generated images nor image_prompts.json manifest found")

        # 4. Check audio / voice manifest
        audio_dir = episode_dir / "audio"
        if not audio_dir.exists():
            issues.append("Audio directory does not exist")
        else:
            audio_files = list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav"))
            voice_manifest = audio_dir / "voice_manifest.json"
            if not audio_files and not voice_manifest.exists():
                issues.append("Neither generated audio nor voice_manifest.json found")

        # 5. Check subtitles
        subtitles_dir = episode_dir / "subtitles"
        if not subtitles_dir.exists():
            issues.append("Subtitles directory does not exist")
        else:
            srt_file = subtitles_dir / "episode.srt"
            vtt_file = subtitles_dir / "episode.vtt"
            if not srt_file.exists():
                issues.append("Subtitles file episode.srt is missing")
            if not vtt_file.exists():
                issues.append("Subtitles file episode.vtt is missing")

        # 6. Check video
        video_dir = episode_dir / "video"
        if not video_dir.exists():
            issues.append("Video directory does not exist")
        else:
            video_file = video_dir / "episode.mp4"
            video_manifest = video_dir / "video_manifest.json"
            if not video_file.exists() and not video_manifest.exists():
                issues.append("Neither episode.mp4 nor video_manifest.json found")

        # 7. Check thumbnail
        thumb_dir = episode_dir / "thumbnail"
        if not thumb_dir.exists():
            issues.append("Thumbnail directory does not exist")
        else:
            thumb_file = thumb_dir / "thumbnail.png"
            thumb_manifest = thumb_dir / "thumbnail_prompt.json"
            if not thumb_file.exists() and not thumb_manifest.exists():
                issues.append("Neither thumbnail.png nor thumbnail_prompt.json found")

        # 8. Check safety
        is_safe, safety_violations = SafetyValidator.validate_safety(episode_data)
        if not is_safe:
            issues.extend([f"Safety failure: {v}" for v in safety_violations])

        is_passed = len(issues) == 0
        return is_passed, issues
