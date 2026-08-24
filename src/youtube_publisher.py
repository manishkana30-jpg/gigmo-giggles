"""YouTube API Publishing Interface."""

import os
from pathlib import Path
from typing import Dict, Any
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.utils import setup_logger

logger = setup_logger("YouTubePublisher")


class YouTubePublisher:
    """Interface for uploading videos to the YouTube Data API v3."""

    def __init__(self, enabled: bool = False, privacy_status: str = "private"):
        self.enabled = enabled
        self.privacy_status = privacy_status

    def publish(self, video_path: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Publish video to YouTube."""
        if not self.enabled:
            logger.info("YouTube auto-publishing is currently disabled. Video generated locally for manual review.")
            return {
                "status": "skipped",
                "reason": "auto_upload_youtube is set to false in settings.json",
                "video_file": str(video_path)
            }

        client_id = os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            logger.error("YouTube API credentials missing. Check YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN.")
            return {
                "status": "failed",
                "reason": "missing credentials"
            }

        if not video_path.exists() or video_path.stat().st_size == 0:
            logger.error(f"Video file not found or empty: {video_path}")
            return {
                "status": "failed",
                "reason": f"Video file not found or empty: {video_path}"
            }

        try:
            creds = Credentials(
                None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )
            creds.refresh(Request())
            logger.info("YouTube OAuth2 token refreshed successfully.")

            youtube = build("youtube", "v3", credentials=creds)

            # Metadata parsing
            title = metadata.get("title", "Kids Educational Video")
            description = metadata.get("description", "A fun and educational video for kids!")
            tags = metadata.get("tags", ["kids", "educational", "learning"])

            logger.info(f"Uploading to YouTube: {title}")

            body = {
                "snippet": {
                    "title": title[:100],  # Title max length is 100
                    "description": description,
                    "tags": tags,
                    "categoryId": "27"  # Education
                },
                "status": {
                    "privacyStatus": self.privacy_status,
                    "selfDeclaredMadeForKids": True
                }
            }

            media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = request.execute()
            video_id = response.get("id")
            logger.info(f"Video uploaded successfully! Video ID: {video_id}")
            logger.info(f"URL: https://youtu.be/{video_id}")

            # Upload thumbnail (check both .png and .jpg)
            thumbnail_dir = video_path.parent.parent / "thumbnail"
            thumbnail_path = thumbnail_dir / "thumbnail.png"
            thumbnail_mime = "image/png"
            if not thumbnail_path.exists():
                thumbnail_path = thumbnail_dir / "thumbnail.jpg"
                thumbnail_mime = "image/jpeg"

            if thumbnail_path.exists():
                logger.info(f"Uploading custom thumbnail: {thumbnail_path.name}")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path), mimetype=thumbnail_mime)
                ).execute()
                logger.info("Thumbnail uploaded successfully.")

            return {
                "status": "success",
                "video_id": video_id,
                "url": f"https://youtu.be/{video_id}"
            }

        except Exception as e:
            logger.error(f"Error publishing to YouTube: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
