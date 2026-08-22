"""Modular Video Generator using Gemini Omni Flash Video and FFmpeg."""

import os
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import check_ffmpeg_available, save_json, save_text, setup_logger

logger = setup_logger("VideoGenerator")

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class VideoGenerator:
    """
    Assembles still cartoon frames, dialogue audio, background music,
    and Ken Burns/Gemini animations into high-definition MP4 videos.
    """

    def __init__(self, fps: int = 24, resolution_16_9: tuple = (1920, 1080), resolution_9_16: tuple = (1080, 1920)):
        self.fps = fps
        self.width_16_9, self.height_16_9 = resolution_16_9
        self.width_9_16, self.height_9_16 = resolution_9_16
        self.ffmpeg_available = check_ffmpeg_available()
        if not self.ffmpeg_available:
            logger.warning("FFmpeg is not installed or not in PATH. Will operate in manifest fallback mode.")

    def download_video_file(self, file_uri: str, output_path: Path, api_key: str):
        separator = "&" if "?" in file_uri else "?"
        download_url = f"{file_uri}{separator}alt=media"
        req = urllib.request.Request(download_url)
        req.add_header("x-goog-api-key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=480) as resp:
                with open(output_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Error downloading video file: {e.code} - {e.read().decode()}")

    def generate_gemini_video(self, image_path: Path, prompt: str, output_path: Path, duration_sec: int) -> bool:
        """Use Gemini Omni Flash API to generate video from an image."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or not GENAI_AVAILABLE:
            return False
            
        try:
            client = genai.Client(api_key=api_key)
            # Upload image
            logger.info(f"Uploading {image_path.name} to Gemini Files API...")
            config = types.UploadFileConfig(mime_type="image/png")
            uploaded_file = client.files.upload(file=str(image_path), config=config)
            
            # Wait for active
            while True:
                f_info = client.files.get(name=uploaded_file.name)
                state_str = f_info.state.name if hasattr(f_info.state, "name") else str(f_info.state)
                if state_str == "ACTIVE":
                    break
                elif state_str == "FAILED":
                    logger.error("File processing failed on backend.")
                    return False
                time.sleep(2)
                
            import re
            
            # Ensure duration is between 3 and 10 for Gemini Omni Flash
            dur = max(3, min(10, int(duration_sec)))
            
            interaction = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"Generating video for prompt: '{prompt}'")
                    interaction = client.interactions.create(
                        model="gemini-omni-flash-preview",
                        input=[
                            {"type": "image", "uri": uploaded_file.uri, "mime_type": "image/png"},
                            {"type": "text", "text": prompt + ". Make it a beautiful, highly detailed 3D cartoon animation suitable for kids."}
                        ],
                        response_format={
                            "type": "video",
                            "aspect_ratio": "16:9",
                            "duration": f"{dur}s"
                        }
                    )
                    break # Success!
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "too_many_requests" in err_str.lower() or "Quota exceeded" in err_str:
                        if attempt < max_retries - 1:
                            # Try to extract seconds to wait
                            sleep_time = 65
                            match = re.search(r"retry in ([\d\.]+)s", err_str)
                            if match:
                                sleep_time = min(float(match.group(1)) + 5, 120)
                            
                            logger.warning(f"Rate limited (429) by Gemini API. Retrying in {sleep_time:.1f}s... (Attempt {attempt+1}/{max_retries})")
                            time.sleep(sleep_time)
                            continue
                    logger.error(f"Gemini video generation failed: {e}")
                    return False

            if not interaction or not getattr(interaction, "output_video", None) or not getattr(interaction.output_video, "uri", None):
                logger.error("No video returned from Gemini.")
                return False
                
            logger.info("Downloading generated video...")
            self.download_video_file(interaction.output_video.uri, output_path, api_key)
            return True

    def build_scene_clip(
        self,
        image_path: Path,
        audio_path: Path,
        output_scene_path: Path,
        duration_sec: float,
        motion_type: str = "zoom_in",
        video_prompt: str = ""
    ) -> bool:
        """
        Render an animated scene clip. Tries Gemini API first, falls back to Ken Burns.
        """
        if not self.ffmpeg_available or not image_path.exists() or not audio_path.exists():
            return False

        output_scene_path.parent.mkdir(parents=True, exist_ok=True)
        
        raw_video_path = output_scene_path.with_name(f"raw_{output_scene_path.name}")
        
        # Try Gemini API first
        gemini_success = False
        if os.environ.get("GEMINI_API_KEY"):
            gemini_success = self.generate_gemini_video(image_path, video_prompt or f"A {motion_type} camera motion.", raw_video_path, int(duration_sec))
            
        total_frames = int(duration_sec * self.fps)

        if gemini_success and raw_video_path.exists():
            # Combine Gemini Video with Audio using FFmpeg
            # We scale the Gemini video to 1920x1080 and pad/trim to match exact audio duration
            vf_filter = f"scale={self.width_16_9}:{self.height_16_9}:force_original_aspect_ratio=increase,crop={self.width_16_9}:{self.height_16_9}"
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", str(raw_video_path),
                "-i", str(audio_path),
                "-vf", vf_filter,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", 
                "-t", str(duration_sec),
                "-c:a", "aac", "-b:a", "192k",
                str(output_scene_path)
            ]
        else:
            # Fallback to Ken Burns zoompan filter
            logger.info("Falling back to FFmpeg Ken Burns effect.")
            if motion_type == "zoom_in":
                vf_filter = (
                    f"zoompan=z='min(zoom+0.0015,1.15)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"s={self.width_16_9}x{self.height_16_9}:fps={self.fps},"
                    f"fade=t=in:st=0:d=0.5,fade=t=out:st={max(0, duration_sec - 0.5)}:d=0.5"
                )
            elif motion_type == "zoom_out":
                vf_filter = (
                    f"zoompan=z='if(lte(zoom,1.0),1.15,max(1.001,zoom-0.0015))':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"s={self.width_16_9}x{self.height_16_9}:fps={self.fps},"
                    f"fade=t=in:st=0:d=0.5,fade=t=out:st={max(0, duration_sec - 0.5)}:d=0.5"
                )
            elif motion_type == "pan_horizontal":
                vf_filter = (
                    f"zoompan=z='1.1':x='if(lte(on,1),(iw-iw/zoom)/2,x+1)':y='(ih-ih/zoom)/2':d={total_frames}:"
                    f"s={self.width_16_9}x{self.height_16_9}:fps={self.fps},"
                    f"fade=t=in:st=0:d=0.5,fade=t=out:st={max(0, duration_sec - 0.5)}:d=0.5"
                )
            else:
                vf_filter = (
                    f"scale={self.width_16_9}:{self.height_16_9},"
                    f"fade=t=in:st=0:d=0.5,fade=t=out:st={max(0, duration_sec - 0.5)}:d=0.5"
                )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", str(duration_sec), "-i", str(image_path),
                "-i", str(audio_path),
                "-vf", vf_filter,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest",
                "-c:a", "aac", "-b:a", "192k",
                str(output_scene_path)
            ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            # Cleanup raw video
            if raw_video_path.exists():
                raw_video_path.unlink()
            return res.returncode == 0 and output_scene_path.exists()
        except Exception as e:
            logger.warning(f"Failed to render scene {output_scene_path.name} via FFmpeg: {e}")
            return False

    def assemble_episode_video(
        self,
        episode_data: Dict[str, Any],
        images_dir: Path,
        audio_dir: Path,
        output_video_dir: Path
    ) -> Dict[str, Any]:
        """
        Assemble all scenes into a final episode.mp4 (16:9).
        """
        output_video_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        rendered_clips = []
        scene_manifests = []

        temp_clips_dir = output_video_dir / "temp_scenes"
        temp_clips_dir.mkdir(parents=True, exist_ok=True)

        for scene in scenes:
            num = scene.get("scene_number", 1)
            duration = float(scene.get("duration_seconds", 15))
            img_path = images_dir / f"scene_{num:02d}.png"
            audio_path = audio_dir / f"scene_{num:02d}_audio.wav"
            clip_path = temp_clips_dir / f"scene_{num:02d}.mp4"
            v_prompt = scene.get("video_prompt", "").lower()

            if "zoom-out" in v_prompt or "zoom out" in v_prompt:
                motion = "zoom_out"
            elif "pan" in v_prompt:
                motion = "pan_horizontal"
            else:
                motion = "zoom_in"

            success = False
            if self.ffmpeg_available and img_path.exists() and audio_path.exists():
                success = self.build_scene_clip(img_path, audio_path, clip_path, duration, motion_type=motion, video_prompt=v_prompt)
                if success:
                    rendered_clips.append(clip_path)

            scene_manifests.append({
                "scene_number": num,
                "duration_seconds": duration,
                "image_file": str(img_path),
                "audio_file": str(audio_path),
                "motion": motion,
                "rendered": success
            })

        final_video_path = output_video_dir / "episode.mp4"
        manifest_path = output_video_dir / "video_manifest.json"

        assembled = False
        if self.ffmpeg_available and len(rendered_clips) == len(scenes):
            concat_list_file = output_video_dir / "concat_list.txt"
            concat_lines = [f"file '{clip.resolve().as_posix()}'" for clip in rendered_clips]
            save_text(concat_list_file, "\n".join(concat_lines))

            # Mix concatenated video with background music
            bg_music = audio_dir / "background_music.wav"
            if bg_music.exists():
                # Mix video audio (voiceover) with lowered background music
                concat_cmd = [
                    "ffmpeg", "-y", 
                    "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
                    "-i", str(bg_music),
                    "-filter_complex", "[1:a]volume=0.2[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                    "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    str(final_video_path)
                ]
            else:
                concat_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_file),
                    "-c", "copy",
                    str(final_video_path)
                ]
                
            try:
                res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
                assembled = (res.returncode == 0 and final_video_path.exists())
            except Exception as e:
                logger.warning(f"FFmpeg concat failed: {e}")

        manifest_data = {
            "episode_id": episode_data.get("episode_id"),
            "ffmpeg_available": self.ffmpeg_available,
            "video_file": str(final_video_path) if assembled else None,
            "resolution": f"{self.width_16_9}x{self.height_16_9}",
            "fps": self.fps,
            "assembled": assembled,
            "scenes": scene_manifests
        }
        save_json(manifest_path, manifest_data)
        logger.info(f"Video assembly status: {'Success' if assembled else 'Manifest Ready'} at {output_video_dir}")

        return manifest_data
