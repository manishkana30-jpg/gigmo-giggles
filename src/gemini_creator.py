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
        title_raw = topic.get("title", "The Shared Adventure")
        learning_obj = topic.get("learning_objective", "Learn the joy of sharing and kindness towards forest animals.")
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
                        "image_prompt": "A vibrant, sun-drenched enchanted meadow, lush green rolling hills under warm golden-hour light. Jack (3D stylized boy, curly brown hair, yellow t-shirt, blue pants) crouches near a glowing wooden stump with wide eyes and an open-mouth grin, pointing eagerly. Jill (3D stylized girl, twin braided black pigtails with pink ribbons, green overalls over pink shirt) leans over his shoulder with pigtails bouncing, hands clasped in awe, eyebrows arched high. Cinematic 3D render, Pixar style",
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
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render, vibrant colors. Jack (3D stylized boy, curly brown hair, yellow t-shirt, blue pants, red sneakers) and Jill (3D stylized girl, twin braided black pigtails with pink ribbons, green overalls over pink shirt, pink sneakers) interacting with the environment. Cinematic lighting, shallow depth of field, 8k resolution, highly detailed.",
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
                                "text": "Whoa! Whoa! The rocks are super slippery! Help!",
                                "translated_text": "अरे! अरे! चट्टानें बहुत फिसलन भरी हैं! मदद करो!",
                                "emotion": "scared",
                                "sound_effect": "slip_fall"
                            },
                            {
                                "character": "Jill",
                                "text": "I got you, Jack! Grab my arm!",
                                "translated_text": "मैंने तुम्हें पकड़ लिया है, जैक! मेरा हाथ पकड़ो!",
                                "emotion": "shocked",
                                "sound_effect": "gasp"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render, vibrant colors. Jack (3D stylized boy, curly brown hair, yellow t-shirt, blue pants, red sneakers) and Jill (3D stylized girl, twin braided black pigtails with pink ribbons, green overalls over pink shirt, pink sneakers) interacting with the environment. Cinematic lighting, shallow depth of field, 8k resolution, highly detailed.",
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
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render, vibrant colors. Jack (3D stylized boy, curly brown hair, yellow t-shirt, blue pants, red sneakers) and Jill (3D stylized girl, twin braided black pigtails with pink ribbons, green overalls over pink shirt, pink sneakers) interacting with the environment. Cinematic lighting, shallow depth of field, 8k resolution, highly detailed.",
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
                "learning_objective": "Learn the joy of sharing, kindness towards forest animals, and teamwork.",
                "target_age": target_age,
                "title": f"{title_raw}: Forest Picnic 🧺 | Jack and Jill" if title_raw == "The Shared Adventure" else f"{title_raw} 🌟 | Jack and Jill",
                "characters": [
                    {"name": "Jack", "role": "Adventurous and kind boy"},
                    {"name": "Jill", "role": "Helpful and observant girl"}
                ],
                "scenes": [
                    {
                        "scene_number": 1,
                        "duration_seconds": 30,
                        "location": "A sunlit mossy forest clearing under a giant oak tree",
                        "action": "Jack and Jill sit on a checkered picnic blanket enjoying fresh sandwiches.",
                        "narration": "What a beautiful, sunny afternoon for a forest picnic with Jack and Jill!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Mmm, these sandwiches are so delicious! What a wonderful day for a picnic, Jill!",
                                "translated_text": "वाह, ये सैंडविच बहुत स्वादिष्ट हैं! जिल, पिकनिक के लिए कितना बढ़िया दिन है!",
                                "emotion": "joyful",
                                "sound_effect": "happy_cheer"
                            },
                            {
                                "character": "Jill",
                                "text": "I packed plenty of yummy treats for our forest adventure! It's so peaceful here.",
                                "translated_text": "मैंने हमारे जंगल के रोमांच के लिए ढेर सारे स्वादिष्ट स्नैक्स पैक किए हैं! यहाँ कितनी शांति है।",
                                "emotion": "cheerful",
                                "sound_effect": "birds_chirping"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack (yellow t-shirt, blue pants) sitting on a checkered picnic blanket eating a sandwich with a big smile. Jill (green overalls, pink shirt) happily holding a wicker picnic basket under a giant mossy oak tree. Warm dappled sunlight filtering through lush forest canopy, vibrant 8k cinematic lighting.",
                        "video_prompt": "Slow dramatic push-in zoom on Jack and Jill enjoying their picnic",
                        "voice_direction": "Jack is cheerful and satisfied, Jill is bright and excited.",
                        "sound_effects": ["forest_birds", "gentle_breeze"]
                    },
                    {
                        "scene_number": 2,
                        "duration_seconds": 30,
                        "location": "Forest clearing near the picnic blanket",
                        "action": "A mischievous raccoon snatches the picnic basket and scurries into the woods. Jack and Jill stand up in shock.",
                        "narration": "Suddenly, a cheeky little raccoon makes off with their picnic basket!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Hey! Look! That little raccoon is running away with our picnic basket!",
                                "translated_text": "अरे! देखो! वह छोटा रैकून हमारी पिकनिक की टोकरी लेकर भाग रहा है!",
                                "emotion": "surprised",
                                "sound_effect": "comic_boing"
                            },
                            {
                                "character": "Jill",
                                "text": "Oh no! We have to follow it and find out where it's taking our snacks!",
                                "translated_text": "ओह नहीं! हमें उसका पीछा करना होगा और देखना होगा कि वह हमारे स्नैक्स कहाँ ले जा रहा है!",
                                "emotion": "shocked",
                                "sound_effect": "gasp"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack and Jill standing on the checkered blanket looking shocked. A cute cartoon raccoon running into the forest carrying the red-and-white picnic basket in its paws. Mossy ancient trees, glowing magical mushrooms, vibrant colors, cinematic depth of field.",
                        "video_prompt": "Quick horizontal pan following the scurrying raccoon into the deep forest",
                        "voice_direction": "Jack is alarmed and surprised, Jill is determined to follow.",
                        "sound_effects": ["scurry_leaves", "surprised_gasp"]
                    },
                    {
                        "scene_number": 3,
                        "duration_seconds": 30,
                        "location": "Mysterious forest trail leading to a hollow tree root",
                        "action": "Jack kneels down pointing at tiny muddy raccoon paw prints. Jill watches closely.",
                        "narration": "Jack and Jill follow the tiny paw prints deeper into the enchanted woods.",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Look down here, Jill! The footprints lead right into that cozy hollow tree!",
                                "translated_text": "यहाँ नीचे देखो, जिल! पैरों के निशान सीधे उस खोखले पेड़ के अंदर जा रहे हैं!",
                                "emotion": "curious",
                                "sound_effect": "footstep_clues"
                            },
                            {
                                "character": "Jill",
                                "text": "Let's tiptoe quietly so we don't scare our little furry friend.",
                                "translated_text": "चलो धीरे-धीरे और चुपचाप चलें ताकि हम अपने प्यारे दोस्त को डरा न दें।",
                                "emotion": "thoughtful",
                                "sound_effect": "tiptoe_steps"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack kneeling on the forest dirt path, pointing at glowing paw prints. Jill standing beside him with hands on her hips, looking curiously into a large dark hollow at the base of a huge mossy tree trunk. The striped tail of a raccoon is visible disappearing inside. Deep forest ambiance, volumetric beams.",
                        "video_prompt": "Slow camera dolly following the paw prints toward the hollow tree entrance",
                        "voice_direction": "Jack is whispering with excitement, Jill speaks softly and kindly.",
                        "sound_effects": ["twig_snap", "curious_chime"]
                    },
                    {
                        "scene_number": 4,
                        "duration_seconds": 30,
                        "location": "Inside a warm, glowing hollow tree",
                        "action": "Jack kneels warmly, offering a shiny red apple to the adorable raccoon next to the picnic basket.",
                        "narration": "Instead of being upset, Jack and Jill decide to share their picnic with their new friend!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Here you go, little buddy! We are happy to share our fresh apple with you!",
                                "translated_text": "यह लो, छोटे दोस्त! हम तुम्हारे साथ अपना ताजा सेब बांटकर बहुत खुश हैं!",
                                "emotion": "joyful",
                                "sound_effect": "gentle_sparkle"
                            },
                            {
                                "character": "Jill",
                                "text": "See? Sharing makes every adventure so much sweeter and full of friendship!",
                                "translated_text": "देखा? बांटने से हर रोमांच और भी प्यारा और दोस्ती से भरा बन जाता है!",
                                "emotion": "proud",
                                "sound_effect": "happy_fanfare"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Warm golden light illuminating the inside of a hollow tree. Jack smiling warmly, holding out a shiny red apple to an adorable cartoon raccoon holding its paws up happily. The opened picnic basket rests nearby with berries. Magical firefly sparkles, cozy and heartwarming atmosphere, 8k Pixar quality.",
                        "video_prompt": "Gentle zoom-out highlighting the warm friendship and happy celebration",
                        "voice_direction": "Jack is gentle and joyful, Jill delivers the heartwarming moral.",
                        "sound_effects": ["warm_chime", "happy_ending_fanfare"]
                    },
                    {
                        "scene_number": 5,
                        "duration_seconds": 30,
                        "location": "Inside the cozy hollow tree nursery",
                        "action": "Three tiny baby raccoons peek out from behind their mother, chirping with excitement.",
                        "narration": "Look! The mother raccoon was just trying to feed her hungry little babies!",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Aww, look at the baby raccoons! They are so tiny and cute!",
                                "translated_text": "अरे वाह, छोटे रैकून के बच्चों को देखो! वे कितने छोटे और प्यारे हैं!",
                                "emotion": "amazed",
                                "sound_effect": "baby_chirp"
                            },
                            {
                                "character": "Jill",
                                "text": "She was taking food for her family! Good thing we brought plenty to share.",
                                "translated_text": "वह अपने परिवार के लिए खाना ले जा रही थी! अच्छा हुआ कि हम बाँटने के लिए बहुत सारा खाना लाए हैं।",
                                "emotion": "caring",
                                "sound_effect": "heartwarming_chime"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack and Jill smiling warmly at three tiny fluffy baby raccoons sitting inside a moss-lined tree nest. Glowing golden forest light, ultra-detailed 8k Pixar aesthetic.",
                        "video_prompt": "Slow pan across the happy baby raccoons eating berries",
                        "voice_direction": "Jack is filled with wonder, Jill speaks with gentle affection.",
                        "sound_effects": ["gentle_lullaby", "happy_squeak"]
                    },
                    {
                        "scene_number": 6,
                        "duration_seconds": 30,
                        "location": "Tree hollow entrance overlooking the enchanted forest",
                        "action": "Jack unpacks sandwiches, grapes, and nuts on a wooden bark table.",
                        "narration": "Jack and Jill set up a special mini forest feast for all their woodland friends.",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Let's make a grand feast table! Grapes for the babies, and crunchy nuts for everyone!",
                                "translated_text": "चलो एक शानदार दावत की मेज बनाते हैं! बच्चों के लिए अंगूर और सभी के लिए कुरकुरे मेवे!",
                                "emotion": "enthusiastic",
                                "sound_effect": "table_set"
                            },
                            {
                                "character": "Jill",
                                "text": "Teamwork turns a lost picnic into the best forest party ever!",
                                "translated_text": "टीमवर्क एक खोई हुई पिकनिक को अब तक की सबसे बेहतरीन जंगल पार्टी में बदल देता है!",
                                "emotion": "cheerful",
                                "sound_effect": "sparkle_chime"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack arranging fresh fruits on a smooth wooden log while Jill pours sweet juice into tiny acorn cups. Forest birds perched nearby, vibrant Pixar 3D aesthetic.",
                        "video_prompt": "Dynamic push-in showing the colorful forest feast",
                        "voice_direction": "Jack is full of energy, Jill laughs with joy.",
                        "sound_effects": ["forest_party", "cheerful_whistle"]
                    },
                    {
                        "scene_number": 7,
                        "duration_seconds": 30,
                        "location": "The sunny forest meadow outside the hollow tree",
                        "action": "The raccoons, squirrels, and birds gather together around Jack and Jill.",
                        "narration": "The forest clearing fills with happy woodland creatures enjoying the feast together.",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Look, Jill! Even the colorful forest birds and squirrels came to join us!",
                                "translated_text": "देखो, जिल! रंग-बिरंगे जंगल के पक्षी और गिलहरियाँ भी हमारे साथ शामिल होने आए हैं!",
                                "emotion": "delighted",
                                "sound_effect": "flutter_wings"
                            },
                            {
                                "character": "Jill",
                                "text": "When you are kind to nature, nature becomes your friend!",
                                "translated_text": "जब आप प्रकृति के प्रति दयालु होते हैं, तो प्रकृति आपकी दोस्त बन जाती है!",
                                "emotion": "wise",
                                "sound_effect": "nature_harmony"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack and Jill surrounded by friendly forest animals in a lush sunlit meadow with wildflowers. Warm golden lighting, 8k resolution, cinematic atmosphere.",
                        "video_prompt": "Wide 360-degree sweeping pan capturing the entire joyful animal celebration",
                        "voice_direction": "Jack speaks with excitement, Jill delivers an inspiring message.",
                        "sound_effects": ["animal_chatter", "upbeat_music"]
                    },
                    {
                        "scene_number": 8,
                        "duration_seconds": 30,
                        "location": "The sunny forest glade under warm golden hour sunlight",
                        "action": "Jack and Jill stand proudly holding hands with their animal friends.",
                        "narration": "Jack and Jill learned that sharing what we have brings the greatest happiness of all.",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "I will always remember this amazing adventure with our forest friends!",
                                "translated_text": "मैं अपने जंगल के दोस्तों के साथ इस अद्भुत रोमांच को हमेशा याद रखूँगा!",
                                "emotion": "grateful",
                                "sound_effect": "triumph_fanfare"
                            },
                            {
                                "character": "Jill",
                                "text": "And sharing taught us that kindness is the most magical treasure in the world!",
                                "translated_text": "और बाँटने से हमें सिखाया कि दयालुता दुनिया का सबसे जादुई खजाना है!",
                                "emotion": "loving",
                                "sound_effect": "warm_glow"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack and Jill smiling with warm glowing hearts under the sunset sky, waving happily. Beautiful volumetric lighting, cinematic 8k finish.",
                        "video_prompt": "Slow dramatic dolly back capturing the sunset glow over the forest",
                        "voice_direction": "Jack is heartfelt, Jill speaks with warmth and love.",
                        "sound_effects": ["warm_outro_fanfare", "sunset_birds"]
                    },
                    {
                        "scene_number": 9,
                        "duration_seconds": 30,
                        "location": "The forest edge trail heading back home",
                        "action": "Jack and Jill wave goodbye to the raccoon family waving back from the tree.",
                        "narration": "As the sun sets, Jack and Jill head home with full bellies and happy hearts.",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Goodbye, little friends! We will visit you again soon with more apples!",
                                "translated_text": "अलविदा, छोटे दोस्तों! हम जल्द ही और सेब लेकर आपसे मिलने फिर आएंगे!",
                                "emotion": "happy",
                                "sound_effect": "wave_goodbye"
                            },
                            {
                                "character": "Jill",
                                "text": "See you soon! What an unforgettable day of discovery!",
                                "translated_text": "जल्द मिलते हैं! खोज और रोमांच का कितना अविस्मरणीय दिन था!",
                                "emotion": "cheerful",
                                "sound_effect": "happy_steps"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack and Jill walking along a cozy forest path toward the warm sunset glow, looking back and waving at the friendly raccoons. Highly detailed 3D Pixar render.",
                        "video_prompt": "Gentle tracking shot following Jack and Jill as they head home",
                        "voice_direction": "Both speak with cheerful energy and warmth.",
                        "sound_effects": ["evening_crickets", "gentle_steps"]
                    },
                    {
                        "scene_number": 10,
                        "duration_seconds": 30,
                        "location": "Interactive Kids Studio with colorful question banner",
                        "action": "Jack and Jill point to the screen with big cheerful smiles, inviting the audience to answer the daily quiz.",
                        "narration": "Now it's time for our Gigmo Giggles Daily Adventure Quiz! Are you ready?",
                        "dialogue": [
                            {
                                "character": "Jack",
                                "text": "Hey friends at home! Can you tell us: What did we share with the little raccoon?",
                                "translated_text": "अरे घर पर बैठे दोस्तों! क्या आप हमें बता सकते हैं: हमने छोटे रैकून के साथ क्या साझा किया?",
                                "emotion": "playful",
                                "sound_effect": "quiz_pop"
                            },
                            {
                                "character": "Jill",
                                "text": "Tell us your answer in the comments below, and subscribe for tomorrow's 3D adventure!",
                                "translated_text": "नीचे कमेंट्स में अपना उत्तर बताएं, और कल के 3D एडवेंचर के लिए सब्सक्राइब करें!",
                                "emotion": "excited",
                                "sound_effect": "bell_chime"
                            }
                        ],
                        "image_prompt": "A high-quality 3D animated cartoon scene, Pixar Disney style, Unreal Engine 5 render. Jack and Jill pointing directly at the camera with big beaming smiles in a colorful studio setting with floating glowing star badges. Vibrant 8k Pixar quality.",
                        "video_prompt": "Fun interactive zoom-in on Jack and Jill with festive confetti sparkles",
                        "voice_direction": "Both speak enthusiastically to the viewer at home.",
                        "sound_effects": ["quiz_fanfare", "applause"]
                    }
                ],
                "quiz": [
                    {
                        "question": "What did Jack and Jill share with the little raccoon?",
                        "options": [
                            "A) Fresh red apples and delicious fruits",
                            "B) A giant heavy rock",
                            "C) An old bicycle"
                        ],
                        "correct_answer": "A) Fresh red apples and delicious fruits",
                        "explanation": "Jack and Jill kindly shared their delicious red apples and fresh treats with the raccoon family!"
                    }
                ],
                "youtube": {
                    "title": "The Shared Adventure: Forest Picnic 🧺 | Jack and Jill 5-Minute Kids Story",
                    "description": "Join Jack and Jill on an unforgettable 5-minute 3D animated forest adventure! Learn the power of sharing, kindness to animals, and teamwork in this beautiful Pixar-style kids show episode.\n\n⏱️ Chapters:\n0:00 Scene 1: Forest Picnic\n0:30 Scene 2: The Cheeky Raccoon\n1:00 Scene 3: Tracking Paw Prints\n1:30 Scene 4: The Tree Hollow\n2:00 Scene 5: Baby Raccoons\n2:30 Scene 6: Setting the Feast\n3:00 Scene 7: Animal Party\n3:30 Scene 8: The Lesson of Sharing\n4:00 Scene 9: Heading Home\n4:30 Scene 10: Interactive Quiz",
                    "tags": ["kids stories", "jack and jill", "sharing is caring", "cartoon for kids", "forest adventure", "5 minute kids story", "3D animation"],
                    "hashtags": ["#GigmoGiggles", "#KidsAnimation", "#Storytime", "#JackAndJill"],
                    "category": "Education",
                    "target_audience": "Children (Made for Kids)"
                },
                "thumbnail": {
                    "prompt": "Jack and Jill sharing a red apple with an adorable raccoon inside a cozy glowing tree hollow, 3D Pixar style",
                    "overlay_text": "THE SHARED ADVENTURE"
                },
                "shorts": []
            }