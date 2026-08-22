"""Script generator exporting structured episodes to readable Markdown scripts."""

from pathlib import Path
from typing import Dict, Any
from src.utils import save_text, setup_logger

logger = setup_logger("ScriptGenerator")


class ScriptGenerator:
    """Renders human-readable markdown screenplay scripts for production and review."""

    @classmethod
    def generate_markdown(cls, episode_data: Dict[str, Any]) -> str:
        """Format an episode dict into a clean, complete Markdown screenplay."""
        lines = []

        # Title & Metadata
        title = episode_data.get("title", "Untitled Episode")
        episode_id = episode_data.get("episode_id", "unknown-episode")
        topic = episode_data.get("topic", "")
        objective = episode_data.get("learning_objective", "")
        age = episode_data.get("target_age", "6-9")

        lines.append(f"# 🎬 Gigmo Giggles Screenplay: {title}")
        lines.append(f"**Episode ID:** `{episode_id}`  ")
        lines.append(f"**Topic:** {topic}  ")
        lines.append(f"**Target Age:** {age}  ")
        lines.append(f"**Learning Objective:** {objective}\n")

        # Cast List
        lines.append("## 👥 Characters")
        for char in episode_data.get("characters", []):
            lines.append(f"- **{char.get('name')}**: {char.get('role', 'Cast Member')}")
        lines.append("\n---\n")

        # Scene-by-scene script
        # OBS Teleprompter Script
        lines.append("## 🎙️ OBS Teleprompter Script (Read this while recording!)\n")
        lines.append("> *TIP: Copy this section into your OBS Teleprompter or Notepad and read it aloud.*")
        lines.append("> *Leave pauses where it says [PAUSE]*\n")

        for scene in episode_data.get("scenes", []):
            num = scene.get("scene_number", 1)
            duration = scene.get("duration_seconds", 15)
            
            lines.append(f"### --- SCENE {num} ({duration} seconds) ---")
            
            narration = scene.get("narration", "")
            if narration:
                lines.append(f"**NARRATOR:**")
                lines.append(f"{narration}\n")

            for dial in scene.get("dialogue", []):
                char = dial.get("character", "Speaker")
                text = dial.get("text", "")
                emotion = dial.get("emotion", "neutral")
                
                lines.append(f"**{char.upper()} ({emotion}):**")
                lines.append(f"{text}\n")
            
            lines.append("*[PAUSE FOR NEXT SCENE]*\n")
            lines.append("---\n")

        # Interactive Quiz
        quiz_items = episode_data.get("quiz", [])
        if quiz_items:
            lines.append("## 🧠 Interactive Kid Quiz\n")
            for idx, q in enumerate(quiz_items, start=1):
                lines.append(f"**Question {idx}:** {q.get('question')}")
                for opt in q.get("options", []):
                    lines.append(f"- {opt}")
                lines.append(f"\n**Correct Answer:** `{q.get('correct_answer')}`")
                lines.append(f"**Explanation:** {q.get('explanation')}\n")

        # Shorts Ideas
        shorts = episode_data.get("shorts", [])
        if shorts:
            lines.append("## 📱 YouTube Shorts Concepts\n")
            for s in shorts:
                lines.append(f"- **{s.get('title')}** ({s.get('duration_seconds', 30)}s)")
                lines.append(f"  *Hook:* \"{s.get('hook')}\" *(Based on Scene {s.get('scene_reference', 1)})*\n")

        return "\n".join(lines)

    @classmethod
    def save_script(cls, episode_data: Dict[str, Any], output_path: Path) -> Path:
        """Render and save script markdown to the target path."""
        md_content = cls.generate_markdown(episode_data)
        save_text(output_path, md_content)
        logger.info(f"Saved episode screenplay to {output_path}")
        return output_path
