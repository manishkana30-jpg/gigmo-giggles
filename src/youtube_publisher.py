"""Future YouTube API Publishing Interface (Disabled in Version 1)."""

from pathlib import Path
from typing import Dict, Any
from src.utils import setup_logger

logger = setup_logger("YouTubePublisher")


class YouTubePublisher:
    """
    Interface for uploading videos to the YouTube Data API v3.
    Intentionally disabled in v1 to allow content curation and validation.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def publish(self, video_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publish video to YouTube (Future feature).
        Currently logs and returns mock pending status.
        """
        if not self.enabled:
            logger.info("YouTube auto-publishing is currently disabled in v1. Video generated locally for manual review.")
            return {
                "status": "skipped",
                "reason": "auto_upload_youtube is set to false in settings.json",
                "video_file": str(video_path)
            }

        raise NotImplementedError(
            "YouTube API publishing is disabled in v1. Verify episode quality before enabling live publishing."
        )
