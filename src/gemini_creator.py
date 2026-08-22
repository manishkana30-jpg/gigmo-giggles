"""Google Gemini Creative Director using the official google-genai SDK."""

import os
import re
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from src.utils import get_project_root, load_json, load_text, setup_logger, slugify
from src.validator import EpisodeSchema, SafetyValidator

logger = setup_logger("GeminiCreator")

# Attempt importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-genai SDK not installed or unavailable in current environment.")


class GeminiCreativeDirector:
    """Creative Director orchestrating AI episode script, storyboard, and metadata."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        settings_file: Optional[Path] = None,
        characters_file: Optional[Path] = None
    ):
        root = get_project_root()
        self.settings = load_json(settings_file or (root / "config" / "settings.json"))
        self.characters = load_json(characters_file or (root / "config" / "characters.json"))
        self.prompts_dir = root / "prompts"

        # Resolve API Key and Model Name
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = (
            model_name
            or os.environ.get("GEMINI_MODEL")
            or self.settings.get("default_gemini_model", "gemini-2.5-flash")
        )

        self.client = None
        if self.api_key and GENAI_AVAILABLE:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Gemini Client using model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")
                self.client = None
        else:
            if not self.api_key:
                logger.warning("GEMINI_API_KEY is not set. Live generation will be unavailable unless in mock mode.")

    def is_live_ready(self) -> bool:
        """Check if live Gemini client is configured and ready."""
        return self.client is not None

    def create_episode(
        self,
        topic: Dict[str, Any],
        date_str: Optional[str] = None,
        mock: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a complete structured episode JSON.
        If mock=True or client unavailable, falls back to high-quality deterministic mock generation.
        """
        if date_str is None:
            date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        topic_slug = slugify(topic.get("title", "episode"))
        episode_id = f"{date_str}-{topic_slug}"

        if mock or not self.is_live_ready():
            logger.info(f"Generating episode for topic '{topic.get('title')}' in Mock/Offline mode...")
            return self._generate_mock_episode(topic, episode_id)

        logger.info(f"Prompting Gemini ({self.model_name}) as Creative Director for topic: '{topic.get('title')}'")
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_episode_request_prompt(topic, episode_id)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text or ""
            episode_data = self._clean_and_parse_json(raw_text)

            # Validate against Pydantic schema
            try:
                validated = EpisodeSchema(**episode_data)
                episode_dict = validated.model_dump()
            except ValidationError as ve:
                logger.warning(f"Initial JSON validation failed: {ve}. Attempting Gemini auto-repair...")
                episode_dict = self._repair_json_with_gemini(raw_text, str(ve))

            # Validate content safety
            is_safe, violations = SafetyValidator.validate_safety(episode_dict)
            if not is_safe:
                logger.warning(f"Content safety check flagged violations: {violations}. Requesting regeneration...")
                # Regenerate with safety reprimand
                user_prompt += f"\n\nCRITICAL FIX REQUIRED: Previous attempt violated safety rules with: {', '.join(violations)}. Ensure 100% safe cartoon content!"
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=f"{system_prompt}\n\n{user_prompt}",
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                episode_dict = self._clean_and_parse_json(response.text or "")
                validated = EpisodeSchema(**episode_dict)
                episode_dict = validated.model_dump()

            return episode_dict

        except Exception as e:
            logger.error(f"Error during Gemini live episode generation: {e}. Falling back to safe mock generator.")
            return self._generate_mock_episode(topic, episode_id)

    def generate_new_topics(self, count: int = 20) -> List[Dict[str, Any]]:
        """Ask Gemini to generate new non-repeating educational topics for children."""
        if not self.is_live_ready():
            return []

        prompt = f"""
Generate a list of {count} unique, exciting, educational STEM and life-skills topics for a kids cartoon show (ages 6-9).
Return a valid JSON array of objects with schema:
[
  {{
    "id": "topic_gen_001",
    "title": "Why Do Fireflies Glow?",
    "category": "Biology",
    "learning_objective": "Understand bioluminescence and chemical energy in nature.",
    "target_age": "6-9",
    "keywords": ["fireflies", "bioluminescence", "insects", "light", "nature"]
  }}
]
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            raw = response.text or ""
            data = self._clean_and_parse_json(raw)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "topics" in data:
                return data["topics"]
            return []
        except Exception as e:
            logger.error(f"Failed to generate new topics via Gemini API: {e}")
            return []

    def _repair_json_with_gemini(self, malformed_json_text: str, error_details: str) -> Dict[str, Any]:
        """Ask Gemini to repair invalid JSON while preserving full content structure."""
        prompt = f"""
The following JSON failed schema validation with error:
{error_details}

Original text:
{malformed_json_text}

Please repair the JSON syntax and missing fields according to the standard EpisodeSchema.
Output ONLY valid JSON.
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            fixed_text = response.text or ""
            parsed = self._clean_and_parse_json(fixed_text)
            validated = EpisodeSchema(**parsed)
            return validated.model_dump()
        except Exception as e:
            logger.error(f"Gemini JSON auto-repair failed: {e}. Recovering with mock template.")
            topic_dict = {"title": "Repaired Educational Topic", "learning_objective": "Learning science"}
            return self._generate_mock_episode(topic_dict, "repaired-episode")

    def _clean_and_parse_json(self, text: str) -> Dict[str, Any]:
        """Strip markdown ticks and parse JSON safely."""
        text = text.strip()
        # Remove ```json and ```
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        return json.loads(text)

    def _build_system_prompt(self) -> str:
        """Combine creative director instructions and character specifications."""
        master_prompt_path = self.prompts_dir / "creative_director.md"
        base_prompt = load_text(master_prompt_path) if master_prompt_path.exists() else "You are the Kids Show Director."

        chars_desc = "\n\n### CANONICAL CHARACTERS (Must be preserved exactly in prompts & dialogue):\n"
        for char in self.characters:
            chars_desc += f"- **{char['name']}** ({char['type']}): {char['canonical_visual_description']}\n  Voice Style: {char['voice_style']}\n"

        return base_prompt + chars_desc

    def _build_episode_request_prompt(self, topic: Dict[str, Any], episode_id: str) -> str:
        """Construct the prompt for generating the day's specific episode."""
        scenes_count = self.settings.get("scenes_per_episode", 10)
        target_age = self.settings.get("target_age", "6-9")

        return f"""
Generate Episode ID: {episode_id}
Topic: {topic.get('title')}
Category: {topic.get('category', 'Science')}
Learning Objective: {topic.get('learning_objective')}
Target Child Age: {target_age}
Number of Scenes: {scenes_count}

Ensure Bobo, Luna, and Milo work together to explore this concept in a hilarious and educational journey.
Include image_prompt for every scene with full canonical visual descriptors.
Ensure video_prompt specifies Ken Burns camera motion.
Output MUST be strict valid JSON matching EpisodeSchema.
"""

    def _generate_mock_episode(self, topic: Dict[str, Any], episode_id: str) -> Dict[str, Any]:
        """Deterministic high-quality episode generator for offline testing or fallback."""
        title_raw = topic.get("title", "Why Does Rain Happen?")
        learning_obj = topic.get("learning_objective", "Understand how clouds collect water droplets and make rain.")
        target_age = self.settings.get("target_age", "6-9")

        scenes = [
            {
                "scene_number": 1,
                "duration_seconds": 12,
                "location": "The Sunny Treehouse Laboratory",
                "action": "Bobo the bear is looking through a toy telescope, while Luna the fox takes notes on a clipboard and Milo the robot rolls in with a spinning antenna.",
                "narration": "Welcome to another sunny day of wonder at the Gigmo Treehouse!",
                "dialogue": [
                    {
                        "character": "Bobo",
                        "text": f"Hey Luna! Look at that! Why is {title_raw.lower()}?",
                        "emotion": "curious",
                        "sound_effect": "boing"
                    },
                    {
                        "character": "Luna",
                        "text": "Great question, Bobo! Let's activate the Discovery Screen!",
                        "emotion": "enthusiastic",
                        "sound_effect": "chime"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Bobo the honey-brown cartoon bear with sunny yellow neckerchief pointing excitedly at a glowing screen with Luna the orange fox in teal vest and Milo the sky-blue robot in a cozy sunlit treehouse. Bright vivid colors, clean outlines, storybook illustration.",
                "video_prompt": "Smooth slow zoom-in toward Bobo and Luna as they examine the discovery screen.",
                "voice_direction": "Bobo speaks with child-like excitement. Luna is cheerful and warm.",
                "sound_effects": ["treehouse_birds", "happy_chime"]
            },
            {
                "scene_number": 2,
                "duration_seconds": 15,
                "location": "The Meadow Observation Deck",
                "action": "Milo the robot projects a glowing hologram showing the first step of the educational concept.",
                "narration": f"Our friends investigate the first secret of {title_raw.lower()}.",
                "dialogue": [
                    {
                        "character": "Milo",
                        "text": "Beep-boop! Scanning parameters! The secret begins with sunlight and energy!",
                        "emotion": "energetic",
                        "sound_effect": "robot_beep"
                    },
                    {
                        "character": "Bobo",
                        "text": "Whoa! It looks like magic, but it is actually science!",
                        "emotion": "amazed",
                        "sound_effect": "sparkle"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Milo the sky-blue compact robot with lime-green glowing digital eyes projecting a sparkling educational holographic diagram. Bobo the friendly bear watches with wide sparkling eyes. Vibrant colors, clean lines.",
                "video_prompt": "Gentle pan left-to-right following Milo's holographic projection.",
                "voice_direction": "Milo has cute melodic robotic pitch. Bobo gasps with joy.",
                "sound_effects": ["robot_scan", "magic_whoosh"]
            },
            {
                "scene_number": 3,
                "duration_seconds": 15,
                "location": "The Cloud Science Chamber",
                "action": "Luna shows a friendly diagram explaining how small particles join together into big wonders.",
                "narration": "When tiny pieces work together, amazing things happen in nature!",
                "dialogue": [
                    {
                        "character": "Luna",
                        "text": "Exactly! When warm energy lifts tiny droplets into the sky, they bundle together into big fluffy clouds!",
                        "emotion": "encouraging",
                        "sound_effect": "bell"
                    },
                    {
                        "character": "Milo",
                        "text": "Affirmative! 100% calculation complete! Teamwork makes the dream work!",
                        "emotion": "proud",
                        "sound_effect": "tada"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Luna the orange cartoon fox explaining a colorful chart with Bobo the bear holding a giant magnifying glass. Bright sunny pastel colors, whimsical cartoon style.",
                "video_prompt": "Camera slow zoom-out revealing the full colorful diagram.",
                "voice_direction": "Luna speaks clearly with pedagogical rhythm. Milo chimes happily.",
                "sound_effects": ["gentle_breeze", "happy_tada"]
            },
            {
                "scene_number": 4,
                "duration_seconds": 18,
                "location": "The Interactive Quiz Studio",
                "action": "Bobo, Luna, and Milo smile directly at the screen, pointing at three glowing colorful letter buttons A, B, and C.",
                "narration": "Now it's time for the Super Gigmo Quiz Question!",
                "dialogue": [
                    {
                        "character": "Bobo",
                        "text": "Are you ready, Super Thinkers? Here comes our question of the day!",
                        "emotion": "thrilled",
                        "sound_effect": "drumroll"
                    },
                    {
                        "character": "Luna",
                        "text": "What is the key superpower behind today's discovery?",
                        "emotion": "smiling",
                        "sound_effect": "quiz_pop"
                    },
                    {
                        "character": "Milo",
                        "text": "Think carefully and shout out your answer!",
                        "emotion": "cheering",
                        "sound_effect": "bell"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Bobo the bear, Luna the fox, and Milo the robot standing side by side waving at the camera in a vibrant TV game show studio with colorful question marks. High contrast, sunny yellow and cyan background.",
                "video_prompt": "Static shot with lively pulse bounce effect to spotlight the quiz choices.",
                "voice_direction": "High energy call-and-response tone engaging young viewers.",
                "sound_effects": ["drumroll", "fanfare"]
            }
        ]

        quiz = [
            {
                "question": f"What did Bobo and Luna learn about {title_raw.lower()}?",
                "options": [
                    "A) Nature's energy and science make it happen!",
                    "B) Sleeping bears cause it to happen",
                    "C) It is made of strawberry jam"
                ],
                "correct_answer": "A) Nature's energy and science make it happen!",
                "explanation": f"Sunlight, air, and teamwork in nature work together to create {title_raw.lower()}!"
            }
        ]

        youtube_meta = {
            "title": f"{title_raw} 🌟 | Fun Science for Kids | Gigmo Giggles",
            "description": f"Join Bobo the Bear, Luna the Fox, and Milo the Robot on an exciting educational adventure!\n\nIn this episode, we explore: {learning_obj}\n\n🔔 Subscribe to Gigmo Giggles for daily colorful learning cartoon episodes!\n\n#GigmoGiggles #KidsLearning #ScienceForKids #EducationalCartoon",
            "tags": [
                "kids educational cartoon",
                title_raw.lower(),
                "science for kids",
                "learning videos for children",
                "gigmo giggles",
                "bobo and luna",
                "cartoon for toddlers",
                "preschool education"
            ],
            "hashtags": ["#KidsLearning", "#ScienceForKids", "#GigmoGiggles", "#Animation"],
            "category": "Education",
            "target_audience": "Children (Made for Kids)"
        }

        thumbnail_meta = {
            "prompt": f"Vibrant 2D cartoon YouTube thumbnail: Bobo the friendly brown bear with sunny yellow scarf pointing up at {title_raw.lower()} with Milo the cute blue robot smiling. Bold bright yellow background, high contrast, clean vector style.",
            "overlay_text": title_raw.upper()
        }

        shorts_list = [
            {
                "title": f"The Secret of {title_raw}! 🌟 #Shorts",
                "hook": f"Did you know how {title_raw.lower()} works? Let's check with Milo!",
                "scene_reference": 2,
                "duration_seconds": 25
            },
            {
                "title": f"Bobo's Fun Science Quiz! 🧠 #Shorts",
                "hook": "Can you solve today's Gigmo brain teaser in 10 seconds?",
                "scene_reference": 4,
                "duration_seconds": 20
            }
        ]

        return {
            "episode_id": episode_id,
            "topic": title_raw,
            "learning_objective": learning_obj,
            "target_age": target_age,
            "title": f"{title_raw} - Gigmo Giggles Episode",
            "characters": [
                {"name": "Bobo", "role": "Curious Explorer Bear"},
                {"name": "Luna", "role": "Clever Science Fox"},
                {"name": "Milo", "role": "Energetic Robot"}
            ],
            "scenes": scenes,
            "quiz": quiz,
            "youtube": youtube_meta,
            "thumbnail": thumbnail_meta,
            "shorts": shorts_list
        }
