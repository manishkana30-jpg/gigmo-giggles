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
        language = self.settings.get("language", "English")
        spoken_language = self.settings.get("spoken_language", "English")

        return f"""
Generate Episode ID: {episode_id}
Topic: {topic.get('title')}
Category: {topic.get('category', 'Science')}
Learning Objective: {topic.get('learning_objective')}
Target Child Age: {target_age}
Number of Scenes: {scenes_count}

Ensure Jack and Jill work together to explore this concept in a hilarious and educational journey.
CRITICAL: The primary 'text' and 'narration' fields MUST be in {language} for the subtitles. However, if spoken language is different, you MUST also provide 'translated_text' and 'translated_narration' which contain the exact same dialogue translated into natively spoken {spoken_language}.
Include image_prompt for every scene with full canonical visual descriptors. The image_prompt MUST adhere to this exact style:
"Best 2.5D layered cartoon illustration, high-res storybook concept art, crisp clean vector lines with soft volumetric shading. Multiplane depth with clearly separated foreground, midground characters, and background layers. Dynamic comic-strip energy, freeze-frame action pose with extreme exaggerated facial expressions.
[LAYER STRUCTURE]:
- Foreground: Out-of-focus blades of grass, floating leaves, or stones framing the bottom/sides to establish 3D parallax depth.
- Midground: Jack and Jill captured mid-action on a steep grassy hill, completely isolated with clear silhouettes.
- Background: Rolling green countryside, storybook cottage, puffy clouds, and soft blue sky.
[EXPRESSION & POSE]: Jack is frozen mid-action with an exaggerated open-mouth scream/gasp of excitement, eyes wide with raised arches. Jill mirrors the energy with hands thrown up in shock/delight, jaw dropped in cartoon amazement."

Ensure video_prompt specifies: "Slow dramatic push-in zoom on Jack and Jill's expressive faces, subtle multiplane horizontal pan to emphasize foreground/background parallax separation."
Output MUST be strict valid JSON matching EpisodeSchema.
"""

    def _generate_mock_episode(self, topic: Dict[str, Any], episode_id: str) -> Dict[str, Any]:
        """Deterministic high-quality episode generator for offline testing or fallback."""
        # When falling back to the mock script, we force the topic to match the hardcoded script (Water Cycle).
        title_raw = "The Water Cycle"
        learning_obj = "Understand how clouds collect water droplets and make rain."
        target_age = self.settings.get("target_age", "6-9")

        scenes = [
            {
                "scene_number": 1,
                "duration_seconds": 15,
                "location": "The Sunny Hillside",
                "action": "Jack is looking through a toy telescope, while Jill takes notes on a clipboard.",
                "narration": "Welcome to another sunny day of wonder on the hill!",
                "dialogue": [
                    {
                        "character": "Jack",
                        "text": f"Hey Jill! Look at that! I've always wondered, why is {title_raw.lower()}?",
                        "emotion": "curious",
                        "sound_effect": "boing"
                    },
                    {
                        "character": "Jill",
                        "text": "Great question, Jack! Let's activate the Discovery Screen and find out together!",
                        "emotion": "enthusiastic",
                        "sound_effect": "chime"
                    }
                ],
                "image_prompt": "Best 2.5D layered cartoon illustration, high-res storybook concept art, crisp clean vector lines with soft volumetric shading. Multiplane depth with clearly separated foreground, midground characters, and background layers. Dynamic comic-strip energy, freeze-frame action pose with extreme exaggerated facial expressions. Foreground: Out-of-focus blades of grass. Midground: Jack and Jill captured mid-action on a steep grassy hill, completely isolated with clear silhouettes. Background: Rolling green countryside. Jack is frozen mid-action with an exaggerated open-mouth gasp of excitement. Jill mirrors the energy with hands thrown up in shock.",
                "video_prompt": "Slow dramatic push-in zoom on Jack and Jill's expressive faces, subtle multiplane horizontal pan to emphasize foreground/background parallax separation.",
                "voice_direction": "Jack speaks with child-like excitement. Jill is cheerful and warm.",
                "sound_effects": ["outdoor_birds", "happy_chime"]
            },
            {
                "scene_number": 2,
                "duration_seconds": 18,
                "location": "The Meadow Observation Deck",
                "action": "Jill holds up a magnifying glass, showing a glowing diagram of the first step of the educational concept.",
                "narration": f"Our friends investigate the first secret of {title_raw.lower()}.",
                "dialogue": [
                    {
                        "character": "Jill",
                        "text": "According to my notes, it all starts right here. See?",
                        "emotion": "smart",
                        "sound_effect": "whoosh"
                    },
                    {
                        "character": "Jack",
                        "text": "Whoa! That is so cool! It's like magic, but real!",
                        "emotion": "amazed",
                        "sound_effect": "sparkle"
                    }
                ],
                "image_prompt": "Best 2.5D layered cartoon illustration, high-res storybook concept art, crisp clean vector lines with soft volumetric shading. Multiplane depth with clearly separated foreground, midground characters, and background layers. Dynamic comic-strip energy, freeze-frame action pose with extreme exaggerated facial expressions. Foreground: Out-of-focus blades of grass. Midground: Jack and Jill captured mid-action on a steep grassy hill, completely isolated with clear silhouettes. Background: Rolling green countryside. Jack is frozen mid-action with an exaggerated open-mouth gasp of excitement. Jill mirrors the energy with hands thrown up in shock.",
                "video_prompt": "Slow dramatic push-in zoom on Jack and Jill's expressive faces, subtle multiplane horizontal pan to emphasize foreground/background parallax separation.",
                "voice_direction": "Jill is confident. Jack is amazed.",
                "sound_effects": ["whoosh", "sparkle"]
            },
            {
                "scene_number": 3,
                "duration_seconds": 18,
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
                        "text": "Affirmative! One hundred percent calculation complete! Teamwork makes the dream work!",
                        "emotion": "proud",
                        "sound_effect": "tada"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Luna the orange cartoon fox in teal vest explaining a large colorful educational chart with bubbling particles and arrows. Bright sunny pastel colors, whimsical cartoon style.",
                "video_prompt": "Camera slow zoom-out revealing the full colorful diagram.",
                "voice_direction": "Luna speaks clearly with pedagogical rhythm. Milo chimes happily.",
                "sound_effects": ["gentle_breeze", "happy_tada"]
            },
            {
                "scene_number": 4,
                "duration_seconds": 15,
                "location": "The Imagination Garden",
                "action": "Bobo imagines a magical scene where the scientific concept comes alive with sparkling particles and swirling colors.",
                "narration": "Bobo closes his eyes and imagines what it would look like up close!",
                "dialogue": [
                    {
                        "character": "Bobo",
                        "text": f"Wow! If I could shrink myself tiny, I could see {title_raw.lower()} happening right before my eyes!",
                        "emotion": "dreamy",
                        "sound_effect": "twinkle"
                    },
                    {
                        "character": "Luna",
                        "text": "That is exactly what scientists do, Bobo! They use powerful tools to see the invisible world!",
                        "emotion": "impressed",
                        "sound_effect": "sparkle"
                    }
                ],
                "image_prompt": f"Stylized 2D cartoon animation frame: Bobo the honey-brown bear with eyes closed, dreaming inside a magical thought bubble filled with sparkling particles and swirling colors representing {title_raw.lower()}. Dreamy purple and gold colors, fantasy cartoon style.",
                "video_prompt": "Zoom-in toward Bobo's dream bubble revealing magical particles.",
                "voice_direction": "Bobo speaks softly with wonder. Luna is encouraging.",
                "sound_effects": ["dream_harp", "sparkle_cascade"]
            },
            {
                "scene_number": 5,
                "duration_seconds": 18,
                "location": "Milo's Digital Workshop",
                "action": "Milo displays a step-by-step breakdown of the science on his holographic screen with numbered steps and fun icons.",
                "narration": "Milo breaks it down into easy steps that everyone can understand!",
                "dialogue": [
                    {
                        "character": "Milo",
                        "text": f"Step one! Energy from the sun starts the whole process! Step two! Tiny particles begin to move and change! Step three! Something amazing happens!",
                        "emotion": "teaching",
                        "sound_effect": "click"
                    },
                    {
                        "character": "Bobo",
                        "text": "Oh, I get it now! It is like a recipe with three ingredients!",
                        "emotion": "enlightened",
                        "sound_effect": "lightbulb"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Milo the sky-blue robot projecting a holographic numbered step-by-step guide with colorful icons. Bobo and Luna watching attentively in a high-tech digital workshop with glowing screens. Cyan and purple neon accents.",
                "video_prompt": "Pan right revealing each step on the holographic display.",
                "voice_direction": "Milo speaks rhythmically counting each step. Bobo has a eureka moment.",
                "sound_effects": ["digital_click", "lightbulb_ding"]
            },
            {
                "scene_number": 6,
                "duration_seconds": 15,
                "location": "The Outdoor Experiment Field",
                "action": "The three friends conduct a simple hands-on experiment related to the topic using everyday objects.",
                "narration": "Now it is time to try it themselves with a fun experiment!",
                "dialogue": [
                    {
                        "character": "Luna",
                        "text": f"Let us try our own experiment! We can see {title_raw.lower()} happen right here!",
                        "emotion": "excited",
                        "sound_effect": "pop"
                    },
                    {
                        "character": "Bobo",
                        "text": "Look! It is working! Science is SO cool!",
                        "emotion": "thrilled",
                        "sound_effect": "wow"
                    }
                ],
                "image_prompt": f"Stylized 2D cartoon animation frame: Bobo the bear, Luna the fox, and Milo the robot conducting a colorful outdoor experiment with beakers, tubes, and bubbling liquids in a sunny garden. Bright greens and blues, educational cartoon style.",
                "video_prompt": "Zoom-in toward the bubbling experiment revealing colorful reactions.",
                "voice_direction": "Luna is enthusiastic about the experiment. Bobo is amazed at the results.",
                "sound_effects": ["bubble_pop", "amazement_sound"]
            },
            {
                "scene_number": 7,
                "duration_seconds": 15,
                "location": "The Wrap-Up Campfire",
                "action": "The friends sit together around a cozy campfire under a starry sky, reviewing what they learned today.",
                "narration": "As the sun sets, our friends share what they discovered!",
                "dialogue": [
                    {
                        "character": "Luna",
                        "text": f"So today we learned that {title_raw.lower()} is all about energy, particles, and nature working together!",
                        "emotion": "satisfied",
                        "sound_effect": "gentle_chime"
                    },
                    {
                        "character": "Milo",
                        "text": "Data log complete! Today's adventure was rated five stars! Do not forget to tell your friends what you learned!",
                        "emotion": "happy",
                        "sound_effect": "star_sound"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Bobo the bear, Luna the fox, and Milo the robot sitting around a warm campfire under a beautiful starry purple sky. Warm orange and purple tones, cozy and magical atmosphere.",
                "video_prompt": "Slow zoom-out revealing the starry sky above the campfire.",
                "voice_direction": "Luna summarizes warmly. Milo gives an upbeat sign-off.",
                "sound_effects": ["campfire_crackle", "night_crickets"]
            },
            {
                "scene_number": 8,
                "duration_seconds": 18,
                "location": "The Interactive Quiz Studio",
                "action": "Bobo, Luna, and Milo smile directly at the screen, pointing at three glowing colorful letter buttons A, B, and C.",
                "narration": "Now it is time for the Super Gigmo Quiz Question!",
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
                        "text": "Think carefully and shout out your answer! Remember, you are a super scientist!",
                        "emotion": "cheering",
                        "sound_effect": "bell"
                    }
                ],
                "image_prompt": "Stylized 2D cartoon animation frame: Bobo the bear, Luna the fox, and Milo the robot standing side by side waving at the camera in a vibrant TV game show studio with colorful question marks and glowing A B C buttons. High contrast, sunny yellow and cyan background.",
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
            "topic": "The Water Cycle",
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
