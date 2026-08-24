"""Main orchestrator and pipeline execution entry point for Gigmo Giggles."""

import os
import sys
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load local environment variables from .env if present
load_dotenv()

from src.utils import get_project_root, save_json, save_text, ensure_dir, setup_logger
from src.topic_manager import TopicManager
from src.gemini_creator import GeminiCreativeDirector
from src.script_generator import ScriptGenerator
from src.storyboard_generator import StoryboardGenerator
from src.image_generator import ImageGenerator
from src.voice_generator import VoiceGenerator
from src.video_generator import VideoGenerator
from src.subtitle_generator import SubtitleGenerator
from src.thumbnail_generator import ThumbnailGenerator
from src.youtube_metadata import YouTubeMetadataGenerator
from src.youtube_publisher import YouTubePublisher
from src.validator import QualityGateValidator, SafetyValidator


def run_pipeline(
    forced_topic: Optional[str] = None,
    date_str: Optional[str] = None,
    mock_mode: bool = False,
    custom_output_dir: Optional[Path] = None,
    force_publish: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Execute the complete Gigmo Giggles daily episode generation pipeline.
    Maintains run_status.json at every step and fails gracefully if an issue arises.
    """
    root = get_project_root()
    if date_str is None:
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    base_episodes_dir = custom_output_dir or (root / "episodes" / date_str)
    ensure_dir(base_episodes_dir)

    log_file = base_episodes_dir / "pipeline.log"
    logger = setup_logger("GigmoPipeline", log_file=log_file)
    logger.info(f"=== Starting Gigmo Giggles Daily Episode Pipeline [{date_str}] ===")

    # Initialize run status tracker
    status_file = base_episodes_dir / "run_status.json"
    status_tracker: Dict[str, Any] = {
        "status": "in_progress",
        "date": date_str,
        "completed": [],
        "failed": None,
        "error": None,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "finished_at": None
    }
    save_json(status_file, status_tracker)

    def mark_step_completed(step_name: str):
        status_tracker["completed"].append(step_name)
        save_json(status_file, status_tracker)
        logger.info(f"✔ Step completed: {step_name}")

    def mark_step_failed(step_name: str, error_msg: str):
        status_tracker["status"] = "partial" if status_tracker["completed"] else "failed"
        status_tracker["failed"] = step_name
        status_tracker["error"] = error_msg
        status_tracker["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(status_file, status_tracker)
        logger.error(f"✖ Step '{step_name}' failed: {error_msg}")

    try:
        # Step 1: Topic Selection
        logger.info("--- 1. Topic Selection ---")
        gemini_director = GeminiCreativeDirector()
        topic_mgr = TopicManager(gemini_creator=gemini_director)
        selected_topic = topic_mgr.select_next_topic(forced_topic_title=forced_topic)
        mark_step_completed("topic")

        # Step 2: Gemini Creative Director (Script, Storyboard, Dialogue, JSON)
        logger.info("--- 2. Creative Director Generation ---")
        episode_data = gemini_director.create_episode(
            topic=selected_topic,
            date_str=date_str,
            mock=mock_mode
        )
        # Save raw episode.json
        save_json(base_episodes_dir / "episode.json", episode_data)
        mark_step_completed("creative_direction")

        # Step 3: Screenplay Markdown Generation
        logger.info("--- 3. Screenplay Script Markdown ---")
        ScriptGenerator.save_script(episode_data, base_episodes_dir / "script.md")
        mark_step_completed("script")

        # Step 4: Storyboard Generation
        logger.info("--- 4. Storyboard Sequence ---")
        StoryboardGenerator.save_storyboard(episode_data, base_episodes_dir / "storyboard.json")
        mark_step_completed("storyboard")

        # Step 5: Image Generation (Cartoon Scene Frames)
        logger.info("--- 5. Scene Image Generation ---")
        img_gen = ImageGenerator()
        img_gen.generate_all_scenes(episode_data, base_episodes_dir / "images")
        mark_step_completed("images")

        # Step 6: Voice Generation (Character Dialogue TTS & Manifest)
        logger.info("--- 6. Voice & Sound Effects Generation ---")
        voice_gen = VoiceGenerator()
        voice_gen.generate_all_scene_audio(episode_data, base_episodes_dir / "audio")
        mark_step_completed("audio")

        # Step 7: Subtitle Generation (SRT & VTT)
        logger.info("--- 7. Subtitle Generation (SRT & VTT) ---")
        SubtitleGenerator.generate_subtitles(episode_data, base_episodes_dir / "subtitles")
        mark_step_completed("subtitles")

        # Step 8: Video Assembly (Ken Burns Animation)
        logger.info("--- 8. Video Assembly ---")
        video_gen = VideoGenerator()
        video_gen.assemble_episode_video(
            episode_data=episode_data,
            images_dir=base_episodes_dir / "images",
            audio_dir=base_episodes_dir / "audio",
            output_video_dir=base_episodes_dir / "video"
        )
        mark_step_completed("video")

        # Step 9: YouTube Thumbnail Generation
        logger.info("--- 9. Thumbnail Generation ---")
        ThumbnailGenerator.generate_thumbnail(episode_data, base_episodes_dir / "thumbnail")
        mark_step_completed("thumbnail")

        # Step 10: YouTube Metadata & Chapters
        logger.info("--- 10. YouTube SEO & Metadata ---")
        YouTubeMetadataGenerator.save_metadata(episode_data, base_episodes_dir / "youtube_metadata.json")
        mark_step_completed("metadata")

        # Step 11: Quality Gate Verification
        logger.info("--- 11. Quality Gate Verification ---")
        passed, quality_issues = QualityGateValidator.check_quality_gate(base_episodes_dir, episode_data)
        if not passed:
            raise ValueError(f"Quality gate check failed. Publication halted. Issues: {quality_issues}")
        mark_step_completed("quality_gate")

        # Step 12: YouTube Publisher check
        logger.info("--- 12. YouTube Publishing ---")
        import json
        settings_path = root / "config" / "settings.json"
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        publish_enabled = settings.get("auto_upload_youtube", False)
        if force_publish is not None:
            publish_enabled = force_publish
        else:
            env_publish = os.environ.get("PUBLISH_TO_YOUTUBE", "").lower()
            if env_publish in ("true", "1", "yes"):
                publish_enabled = True
            elif env_publish in ("false", "0", "no"):
                publish_enabled = False

        publisher = YouTubePublisher(
            enabled=publish_enabled,
            privacy_status=settings.get("youtube_privacy_status", "private")
        )
        
        # Verify MP4 exists before attempting upload
        video_file = base_episodes_dir / "video" / "episode.mp4"
        if not video_file.exists() or video_file.stat().st_size == 0:
            raise FileNotFoundError(f"Generated video not found or empty: {video_file}")

        # Load YouTube metadata
        youtube_metadata = episode_data.get("youtube", {})
        if not youtube_metadata and (base_episodes_dir / "youtube_metadata.json").exists():
            with open(base_episodes_dir / "youtube_metadata.json", 'r', encoding='utf-8') as f:
                youtube_metadata = json.load(f)

        publish_result = publisher.publish(video_file, youtube_metadata)
        if publish_result.get("status") == "failed":
            raise RuntimeError(f"YouTube upload failed: {publish_result.get('error') or publish_result.get('reason')}")
        elif publish_result.get("status") == "success":
            logger.info(f"YouTube upload succeeded: {publish_result.get('url')}")
        mark_step_completed("youtube_publish")

        # Step 13: Mark Topic as Used in Catalog
        topic_mgr.mark_topic_as_used(selected_topic, episode_data.get("episode_id", date_str))

        # Final Success Marking
        status_tracker["status"] = "success"
        status_tracker["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(status_file, status_tracker)
        logger.info("🎉 Gigmo Giggles Daily Episode generation completed successfully!")
        return status_tracker

    except Exception as e:
        import traceback
        err_details = traceback.format_exc()
        current_step = status_tracker["completed"][-1] if status_tracker["completed"] else "initialization"
        mark_step_failed(current_step, f"{str(e)}\n{err_details}")
        logger.error(f"Pipeline encountered critical exception: {e}")
        return status_tracker


def main():
    """CLI Parser and execution wrapper."""
    parser = argparse.ArgumentParser(description="Gigmo Giggles - Automated Kids YouTube Episode Creator")
    parser.add_argument("--topic", type=str, default=None, help="Force a specific educational topic title")
    parser.add_argument("--date", type=str, default=None, help="Episode date identifier (YYYY-MM-DD)")
    parser.add_argument("--mock", action="store_true", help="Force offline mock generation mode")
    parser.add_argument("--publish", action="store_true", dest="publish", default=None, help="Force publish to YouTube")
    parser.add_argument("--no-publish", action="store_false", dest="publish", help="Disable publishing to YouTube")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory")

    args = parser.parse_args()

    custom_out = Path(args.output_dir) if args.output_dir else None
    result = run_pipeline(
        forced_topic=args.topic,
        date_str=args.date,
        mock_mode=args.mock,
        custom_output_dir=custom_out,
        force_publish=args.publish
    )

    if result.get("status") == "success":
        sys.exit(0)
    else:
        logger = setup_logger("GigmoPipeline")
        logger.error(f"Pipeline concluded with non-success status: {result.get('status')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
