"""Modular Video Generator using FFmpeg with Ken Burns motion simulation."""

import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import check_ffmpeg_available, save_json, save_text, setup_logger

logger = setup_logger("VideoGenerator")


class VideoGenerator:
    """
    Assembles still cartoon frames, dialogue audio, background music,
    and Ken Burns camera animations into high-definition MP4 videos.
    """

    def __init__(self, fps: int = 24, resolution_16_9: tuple = (1920, 1080), resolution_9_16: tuple = (1080, 1920)):
        self.fps = fps
        self.width_16_9, self.height_16_9 = resolution_16_9
        self.width_9_16, self.height_9_16 = resolution_9_16
        self.ffmpeg_available = check_ffmpeg_available()
        if not self.ffmpeg_available:
            logger.warning("FFmpeg is not installed or not in PATH. Will operate in manifest fallback mode.")

    def build_scene_clip(
        self,
        image_path: Path,
        audio_path: Path,
        output_scene_path: Path,
        duration_sec: float,
        motion_type: str = "zoom_in"
    ) -> bool:
        """
        Render an animated scene clip with Ken Burns motion using FFmpeg.
        """
        if not self.ffmpeg_available or not image_path.exists() or not audio_path.exists():
            return False

        output_scene_path.parent.mkdir(parents=True, exist_ok=True)
        total_frames = int(duration_sec * self.fps)

        # Build Ken Burns zoompan filter
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
            # Gentle scale pulse
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
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
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
        Assemble all scenes into a final episode.mp4 (16:9) and shorts clip.
        If FFmpeg is not available, creates video_manifest.json with all specifications.
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

            # Determine motion
            v_prompt = scene.get("video_prompt", "").lower()
            if "zoom-out" in v_prompt or "zoom out" in v_prompt:
                motion = "zoom_out"
            elif "pan" in v_prompt:
                motion = "pan_horizontal"
            else:
                motion = "zoom_in"

            success = False
            if self.ffmpeg_available and img_path.exists() and audio_path.exists():
                success = self.build_scene_clip(img_path, audio_path, clip_path, duration, motion_type=motion)
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

        # If all individual scene clips were rendered, concatenate them
        assembled = False
        if self.ffmpeg_available and len(rendered_clips) == len(scenes):
            concat_list_file = output_video_dir / "concat_list.txt"
            concat_lines = [f"file '{clip.resolve().as_posix()}'" for clip in rendered_clips]
            save_text(concat_list_file, "\n".join(concat_lines))

            concat_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list_file),
                "-c", "copy",
                str(final_video_path)
            ]
            try:
                res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                assembled = (res.returncode == 0 and final_video_path.exists())
            except Exception as e:
                logger.warning(f"FFmpeg concat failed: {e}")

        # Save video_manifest.json
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
