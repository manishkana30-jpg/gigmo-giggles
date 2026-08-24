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
        
        try:
            self.character_prompts = load_json(root / "config" / "character_prompts.json")
        except FileNotFoundError:
            self.character_prompts = {}

        # Resolve API Key and Model Name
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = (
            model_name
            or os.environ.get("GEMINI_MODEL")
            or self.settings.get("default_gemini_model", "gemini-3.6-flash")
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

You MUST write the `image_prompt` using the exact Character Emotion Prompts provided below for Jack and Jill based on their emotion in the scene. Combine them into a single coherent prompt for the scene. Do not change their descriptions.

Available Character Emotion Prompts:
{json.dumps(self.character_prompts, indent=2)}

Ensure video_prompt specifies: "Slow dramatic push-in zoom on Jack and Jill's expressive faces, subtle multiplane horizontal pan to emphasize foreground/background parallax separation."
"""

    def _generate_mock_episode(self, topic: Dict[str, Any], episode_id: str) -> Dict[str, Any]:
        """Deterministic high-quality episode generator for offline testing or fallback."""
        title_raw = topic.get("title", "The Water Cycle")
        learning_obj = topic.get("learning_objective", "Understand how clouds collect water droplets and make rain.")
        target_age = self.settings.get("target_age", "6-9")

        if title_raw == "The Lost Compass Adventure":
            return {
                "episode_id": episode_id,
                "topic": "The Lost Compass Adventure",
                "learning_objective": "Learn how a compass works and the value of teamwork.",
                "target_age": target_age,
                "title": "The Lost Compass Adventure",
                "characters": [
                    {"name": "Jack", "role": "Adventurous boy"},
                    {"name": "Jill", "role": "Cheerful girl"}
                ],
                "scenes": [
                    {
                        "scene_number": 1,
                        "duration_seconds": 15,
                        "location": "A vibrant, sun-drenched enchanted meadow",
                        "action": "Jack crouches near a glowing wooden stump pointing eagerly. Jill leans over his shoulder.",
                        "narration": "What a beautiful day to explore the enchanted meadow!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Look at this glowing stump, Jill! I wonder if there is a treasure inside?",
                                "translated_text": "जिल, इस चमकते हुए ठूंठ को देखो! मुझे आश्चर्य है कि क्या इसके अंदर कोई खजाना है?",
                                "emotion": "curious",
                                "sound_effect": "magical_chime"
                            },
                            {
                                "character": "Jill",
                                "text": "It looks like something is hidden there! Let's check it out together!",
                                "translated_text": "ऐसा लगता है जैसे वहां कुछ छिपा हुआ है! चलो मिलकर इसका पता लगाते हैं!",
                                "emotion": "excited",
                                "sound_effect": "happy_pop"
                            }
                        ],
                        "image_prompt": "A vibrant, sun-drenched enchanted meadow, lush green rolling hills under warm golden-hour light. Jack crouches near a glowing wooden stump with wide eyes and an open-mouth grin, pointing eagerly. Jill leans over his shoulder with pigtails bouncing, hands clasped in awe, eyebrows arched high. Cinematic 3D render, Pixar style...",
                        "video_prompt": "Slow dramatic push-in zoom on Jack and Jill's expressive faces, subtle multiplane horizontal pan to emphasize foreground/background parallax separation.",
                        "voice_direction": "Jack is extremely curious, Jill is supportive and excited.",
                        "sound_effects": ["outdoor_ambience", "magical_chime"]
                    },
                    {
                        "scene_number": 2,
                        "duration_seconds": 15,
                        "location": "Rocky trail leading up a mist-covered hill",
                        "action": "Jack stands firmly, holding a wooden walking stick. Jill looks down at the steep drop biting her lip.",
                        "narration": "The journey up the hill was going to be tough.",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "This path looks steep, but I know we can make it if we are careful.",
                                "translated_text": "यह रास्ता खड़ी चढ़ाई वाला लग रहा है, लेकिन मुझे पता है कि अगर हम सावधान रहें तो हम इसे पार कर सकते हैं।",
                                "emotion": "determined",
                                "sound_effect": "footsteps_dirt"
                            },
                            {
                                "character": "Jill",
                                "text": "I'm a little scared of how high we are, Jack. Please hold my hand.",
                                "translated_text": "मुझे थोड़ा डर लग रहा है कि हम कितनी ऊंचाई पर हैं, जैक। कृपया मेरा हाथ पकड़ो।",
                                "emotion": "hesitant",
                                "sound_effect": "wind_howl"
                            }
                        ],
                        "image_prompt": "Rocky trail leading up a mist-covered hill. Jack stands firmly, one foot on a boulder, jaw set with determined grit, holding a wooden walking stick. Jill looks down at the steep drop with raised inner eyebrows, biting her lip in mild worry, clutching Jack's sleeve. Dynamic wide-angle, atmospheric haze...",
                        "video_prompt": "Subtle multiplane horizontal pan to emphasize steep drop",
                        "voice_direction": "Jack is brave and resolute, Jill is slightly nervous but trusting.",
                        "sound_effects": ["wind_howl", "footsteps"]
                    },
                    {
                        "scene_number": 3,
                        "duration_seconds": 15,
                        "location": "Slick mossy stone path",
                        "action": "Jack slips, arms pinwheeling. Jill gasps and leans to catch him.",
                        "narration": "Oh no! Watch your step, Jack!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Whoa! This moss is super slippery! Help!",
                                "translated_text": "अरे! यह काई बहुत फिसलन भरी है! बचाओ!",
                                "emotion": "panic",
                                "sound_effect": "slip_slide"
                            },
                            {
                                "character": "Jill",
                                "text": "I got you, Jack! Grab my arm!",
                                "translated_text": "मैंने तुम्हें पकड़ लिया है, जैक! मेरा हाथ पकड़ो!",
                                "emotion": "shocked",
                                "sound_effect": "gasp"
                            }
                        ],
                        "image_prompt": "Jack slips on a slick mossy stone, arms pinwheeling in exaggerated slapstick motion, eyes wide in comic shock. Jill gasps with both hands covering her cheeks, mouth shaped in a round 'O', leaning sideways to catch him. Freeze-frame action shot, slight motion blur...",
                        "video_prompt": "Fast frantic shake effect with motion blur on Jack",
                        "voice_direction": "Jack is in comic panic, Jill yells out in surprise.",
                        "sound_effects": ["slip_slide", "comic_gasp"]
                    },
                    {
                        "scene_number": 4,
                        "duration_seconds": 15,
                        "location": "Top of the hill overlooking a sparkling river valley",
                        "action": "Jack and Jill sit side-by-side on a wooden bench, holding up the shiny golden compass.",
                        "narration": "They finally reached the top and found the shiny golden compass!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "We did it, Jill! We worked together and found the lost compass!",
                                "translated_text": "हमने कर दिखाया, जिल! हमने मिलकर काम किया और खोया हुआ कम्पास ढूंढ लिया!",
                                "emotion": "joyful",
                                "sound_effect": "success_fanfare"
                            },
                            {
                                "character": "Jill",
                                "text": "It's beautiful! And teamwork made the whole adventure so much fun!",
                                "translated_text": "यह खूबसूरत है! और टीमवर्क ने पूरे रोमांच को बहुत मजेदार बना दिया!",
                                "emotion": "proud",
                                "sound_effect": "happy_laugh"
                            }
                        ],
                        "image_prompt": "Top of the hill overlooking a sparkling river valley at sunset. Jack and Jill sit side-by-side on a wooden bench, laughing joyfully with crinkled eyes and rosy cheeks, holding up the shiny golden compass together. Warm rim lighting, rich sunset hues, heartfelt storytelling composition...",
                        "video_prompt": "Warm slow pan revealing the beautiful sunset valley",
                        "voice_direction": "Jack is victorious and thrilled, Jill is relieved and happy.",
                        "sound_effects": ["success_fanfare", "happy_laugh"]
                    }
                ],
                "quiz": [
                    {
                        "question": "What did Jack and Jill find at the top of the hill?",
                        "options": [
                            "A) A shiny golden compass",
                            "B) A giant strawberry",
                            "C) A sleeping dragon"
                        ],
                        "correct_answer": "A) A shiny golden compass",
                        "explanation": "Jack and Jill worked together and found the lost golden compass at the top of the hill!"
                    }
                ],
                "youtube": {
                    "title": "The Lost Compass Adventure 🌟 | Kids Learning | Jack and Jill",
                    "description": "Join Jack and Jill on their exciting adventure to find the lost compass!",
                    "tags": ["kids", "learning", "compass", "jack and jill"],
                    "hashtags": ["#KidsLearning", "#Adventure"],
                    "category": "Education",
                    "target_audience": "Children (Made for Kids)"
                },
                "thumbnail": {
                    "prompt": "Jack and Jill holding a shiny golden compass at the top of a hill",
                    "overlay_text": "THE LOST COMPASS"
                },
                "shorts": []
            }
        else:
            return {
                "episode_id": episode_id,
                "topic": title_raw,
                "learning_objective": learning_obj,
                "target_age": target_age,
                "title": f"{title_raw} - Gigmo Giggles Episode",
                "characters": [
                    {"name": "Bobo", "role": "Friendly bear"},
                    {"name": "Luna", "role": "Clever fox"}
                ],
                "scenes": [
                    {
                        "scene_number": 1,
                        "duration_seconds": 15,
                        "location": "The Sunny Hillside",
                        "action": "Bobo and Luna look at the sky.",
                        "narration": "Welcome to another sunny day of wonder!",
                        "dialogue": [
                            {
                                "character": "Bobo",
                                "text": f"Hey Luna! Look at that! Why is {title_raw.lower()}?",
                                "emotion": "curious",
                                "sound_effect": "boing"
                            },
                            {
                                "character": "Luna",
                                "text": "Great question, Bobo! Let's find out together!",
                                "emotion": "excited",
                                "sound_effect": "chime"
                            }
                        ],
                        "image_prompt": "Bobo the bear and Luna the fox looking at the sky.",
                        "video_prompt": "Slow zoom in",
                        "voice_direction": "Excited",
                        "sound_effects": ["outdoor_birds", "happy_chime"]
                    },
                    {
                        "scene_number": 2,
                        "duration_seconds": 15,
                        "location": "The Meadow Deck",
                        "action": "Luna shows a diagram.",
                        "narration": "They study the first secret.",
                        "dialogue": [
                            {
                                "character": "Luna",
                                "text": "It all starts right here. See?",
                                "emotion": "smart",
                                "sound_effect": "whoosh"
                            },
                            {
                                "character": "Bobo",
                                "text": "Whoa! That is so cool!",
                                "emotion": "amazed",
                                "sound_effect": "sparkle"
                            }
                        ],
                        "image_prompt": "Luna pointing at a diagram.",
                        "video_prompt": "Pan left",
                        "voice_direction": "Pedagogical",
                        "sound_effects": ["whoosh", "sparkle"]
                    },
                    {
                        "scene_number": 3,
                        "duration_seconds": 15,
                        "location": "The Science Room",
                        "action": "Bobo explains more.",
                        "narration": "Learning together is so much fun!",
                        "dialogue": [
                            {
                                "character": "Bobo",
                                "text": "I think I understand how this works now!",
                                "emotion": "happy",
                                "sound_effect": "bell"
                            },
                            {
                                "character": "Luna",
                                "text": "You got it, Bobo! That's exactly right!",
                                "emotion": "proud",
                                "sound_effect": "tada"
                            }
                        ],
                        "image_prompt": "Bobo smiling with a lightbulb idea.",
                        "video_prompt": "Zoom out",
                        "voice_direction": "Encouraging",
                        "sound_effects": ["gentle_breeze", "happy_tada"]
                    },
                    {
                        "scene_number": 4,
                        "duration_seconds": 15,
                        "location": "The Quiz Studio",
                        "action": "They ask a question.",
                        "narration": "Now it's time for the quiz!",
                        "dialogue": [
                            {
                                "character": "Bobo",
                                "text": "Are you ready for the quiz?",
                                "emotion": "thrilled",
                                "sound_effect": "drumroll"
                            },
                            {
                                "character": "Luna",
                                "text": "Here is the question of the day!",
                                "emotion": "smiling",
                                "sound_effect": "quiz_pop"
                            }
                        ],
                        "image_prompt": "Bobo and Luna waving at the screen.",
                        "video_prompt": "Static shot",
                        "voice_direction": "High energy",
                        "sound_effects": ["drumroll", "fanfare"]
                    }
                ],
                "quiz": [
                    {
                        "question": "Who goes on the adventure?",
                        "options": ["A) Bobo and Luna", "B) No one"],
                        "correct_answer": "A) Bobo and Luna",
                        "explanation": "Bobo and Luna explore the topic together."
                    }
                ],
                "youtube": {
                    "title": f"{title_raw} | Fun Science for Kids",
                    "description": f"Learn about {title_raw.lower()} with Bobo and Luna!",
                    "tags": ["kids", "learning", "science"],
                    "hashtags": ["#KidsLearning"],
                    "category": "Education",
                    "target_audience": "Children (Made for Kids)"
                },
                "thumbnail": {
                    "prompt": "Bobo and Luna pointing at the sky",
                    "overlay_text": title_raw.upper()
                },
                "shorts": []
            }
