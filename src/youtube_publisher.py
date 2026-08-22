"""YouTube API Publishing Interface."""

import os
from pathlib import Path
from typing import Dict, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.utils import setup_logger

logger = setup_logger("YouTubePublisher")


class YouTubePublisher:
    """
    Interface for uploading videos to the YouTube Data API v3.
    """

    def __init__(self, enabled: bool = False, privacy_status: str = "private"):
        self.enabled = enabled
        self.privacy_status = privacy_status

    def publish(self, video_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        In Manual Creator Mode, we do not upload to YouTube automatically because
        the pipeline only generates raw assets for DaVinci Resolve, not a final .mp4.
        """
        logger.info("Pipeline is in Manual Creator Mode. Skipping auto-publishing.")
        logger.info("You must render the video in DaVinci Resolve and upload it manually to YouTube.")

        return {
            "status": "skipped",
            "reason": "Manual Creator Mode active. Final MP4 must be rendered in DaVinci Resolve.",
            "video_file": None
        }
