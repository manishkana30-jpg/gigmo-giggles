"""Topic selection, history tracking, and dynamic replenishment."""

import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import load_json, save_json, get_project_root, setup_logger

logger = setup_logger("TopicManager")


class TopicManager:
    """Manages educational topics and ensures no repeats until all are used."""

    def __init__(
        self,
        topics_file: Optional[Path] = None,
        history_file: Optional[Path] = None,
        gemini_creator: Optional[Any] = None
    ):
        root = get_project_root()
        self.topics_file = topics_file or (root / "config" / "topics.json")
        self.history_file = history_file or (root / "config" / "topic_history.json")
        self.gemini_creator = gemini_creator
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Ensure topics and history files exist."""
        if not self.topics_file.exists():
            default_topics = [
                {
                    "id": "topic_001",
                    "title": "Why Does Rain Happen?",
                    "category": "Earth Science",
                    "learning_objective": "Understand the water cycle: evaporation, clouds, and rain.",
                    "target_age": "6-9",
                    "keywords": ["rain", "clouds", "water cycle"]
                }
            ]
            save_json(self.topics_file, default_topics)

        if not self.history_file.exists():
            save_json(self.history_file, {"used_topics": []})

    def get_all_topics(self) -> List[Dict[str, Any]]:
        """Load all configured topics."""
        return load_json(self.topics_file)

    def get_history(self) -> Dict[str, Any]:
        """Load topic history."""
        return load_json(self.history_file)

    def get_used_topic_ids(self) -> List[str]:
        """Return list of used topic IDs."""
        history = self.get_history()
        return [entry["id"] for entry in history.get("used_topics", []) if "id" in entry]

    def select_next_topic(self, forced_topic_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Select an unused topic. If all topics are used, replenish with Gemini.
        If forced_topic_title is provided, match or construct a topic object for it.
        """
        all_topics = self.get_all_topics()

        # Handle manually forced topic
        if forced_topic_title:
            for t in all_topics:
                if t.get("title", "").lower() == forced_topic_title.lower():
                    logger.info(f"Using forced topic from catalog: {t['title']}")
                    return t
            # Create custom topic entry
            custom_id = f"custom_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}"
            return {
                "id": custom_id,
                "title": forced_topic_title,
                "category": "General Education",
                "learning_objective": f"Learn all about {forced_topic_title} with fun character explanations.",
                "target_age": "6-9",
                "keywords": [forced_topic_title.lower()]
            }

        used_ids = set(self.get_used_topic_ids())
        unused_topics = [t for t in all_topics if t.get("id") not in used_ids]

        if not unused_topics:
            logger.info("All available topics have been used! Replenishing with new topics...")
            new_topics = self._replenish_topics()
            if new_topics:
                all_topics.extend(new_topics)
                save_json(self.topics_file, all_topics)
                unused_topics = new_topics
            else:
                # If replenishment is offline or failed, cycle by resetting history
                logger.warning("Could not generate new online topics. Resetting history cycle.")
                self.reset_history()
                unused_topics = all_topics

        selected = unused_topics[0]
        logger.info(f"Selected next topic: '{selected.get('title')}' (ID: {selected.get('id')})")
        return selected

    def mark_topic_as_used(self, topic: Dict[str, Any], episode_id: str) -> None:
        """Mark a topic as used in topic_history.json."""
        history = self.get_history()
        entry = {
            "id": topic.get("id", "unknown"),
            "title": topic.get("title", "Untitled"),
            "episode_id": episode_id,
            "used_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        history.setdefault("used_topics", []).append(entry)
        save_json(self.history_file, history)
        logger.info(f"Marked topic '{entry['title']}' as used for episode '{episode_id}'.")

    def reset_history(self) -> None:
        """Clear topic history to restart cycle."""
        save_json(self.history_file, {"used_topics": []})
        logger.info("Topic history reset.")

    def _replenish_topics(self) -> List[Dict[str, Any]]:
        """Ask Gemini or fallback mechanism for 20 new educational topics."""
        if self.gemini_creator and hasattr(self.gemini_creator, "generate_new_topics"):
            try:
                topics = self.gemini_creator.generate_new_topics(count=20)
                if topics and isinstance(topics, list):
                    return topics
            except Exception as e:
                logger.error(f"Failed to generate new topics via Gemini: {e}")

        # Fallback procedural generation
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        fallback_ideas = [
            ("How Do Magnets Work?", "Physics", "Magnetic attraction and poles"),
            ("Why Do We Sneeze?", "Biology", "Body defense mechanisms and tickly noses"),
            ("How Bridges Stay Up", "Engineering", "Pillars, arches, and weight distribution"),
            ("The Secret Life of Bees", "Ecology", "Pollination and making delicious honey"),
            ("Why Does Ice Float?", "Chemistry", "Water density and freezing properties"),
            ("How Airplanes Fly", "Physics", "Lift, drag, thrust, and wing design"),
            ("The Story of Fossils", "Paleontology", "How dinosaur bones turned to stone"),
            ("Why Do Leaves Turn Yellow in Autumn?", "Botany", "Chlorophyll and seasonal change"),
            ("How Do Volcanoes Erupt?", "Earth Science", "Magma pressure and tectonic plates"),
            ("The Magic of Rainbows", "Optics", "Sunlight refraction through raindrops")
        ]
        replenished = []
        for idx, (title, category, obj) in enumerate(fallback_ideas, start=1):
            replenished.append({
                "id": f"topic_replenished_{timestamp}_{idx:03d}",
                "title": title,
                "category": category,
                "learning_objective": obj,
                "target_age": "6-9",
                "keywords": [w.lower() for w in title.replace("?", "").split()]
            })
        return replenished
