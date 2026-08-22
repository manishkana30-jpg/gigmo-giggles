"""Modular Video Generator using enhanced FFmpeg Ken Burns animations."""

import os
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.utils import check_ffmpeg_available, save_json, save_text, setup_logger

logger = setup_logger("VideoGenerator")


class VideoGenerator:
    """
    Assembles still cartoon frames, dialogue audio, background music,
    and enhanced Ken Burns animations into high-definition MP4 videos
    with smooth crossfade transitions between scenes.
    """

    def __init__(self, fps: int = 24, resolution_16_9: tuple = (1920, 1080), resolution_9_16: tuple = (1080, 1920)):
        self.fps = fps
        self.width_16_9, self.height_16_9 = resolution_16_9
        self.width_9_16, self.height_9_16 = resolution_9_16
        self.ffmpeg_available = check_ffmpeg_available()
        if not self.ffmpeg_available:
            logger.warning("FFmpeg is not installed or not in PATH. Will operate in manifest fallback mode.")

    def _get_motion_filter(self, motion_type: str, duration_sec: float, total_frames: int) -> str:
        """Generate enhanced Ken Burns filter with varied motion patterns."""
        w, h = self.width_16_9, self.height_16_9
        fps = self.fps
        fade_in = 0.5
        fade_out_start = max(0, duration_sec - 0.5)

        if motion_type == "zoom_in":
            # Smooth zoom from 1.0x to 1.20x centered
            vf = (
                f"zoompan=z='min(zoom+0.002,1.20)':d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        elif motion_type == "zoom_out":
            # Smooth zoom from 1.20x down to 1.0x centered
            vf = (
                f"zoompan=z='if(lte(zoom,1.001),1.20,max(1.001,zoom-0.002))':d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        elif motion_type == "pan_right":
            # Pan left to right with slight zoom
            vf = (
                f"zoompan=z='1.12':d={total_frames}:"
                f"x='if(lte(on,1),0,min(x+2,(iw-iw/zoom)))':y='(ih-ih/zoom)/2':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        elif motion_type == "pan_left":
            # Pan right to left
            vf = (
                f"zoompan=z='1.12':d={total_frames}:"
                f"x='if(lte(on,1),(iw-iw/zoom),max(0,x-2))':y='(ih-ih/zoom)/2':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        elif motion_type == "pan_up":
            # Pan bottom to top
            vf = (
                f"zoompan=z='1.12':d={total_frames}:"
                f"x='(iw-iw/zoom)/2':y='if(lte(on,1),(ih-ih/zoom),max(0,y-1.5))':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        elif motion_type == "zoom_in_left":
            # Zoom toward left third of image
            vf = (
                f"zoompan=z='min(zoom+0.002,1.25)':d={total_frames}:"
                f"x='iw/4-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        elif motion_type == "zoom_in_right":
            # Zoom toward right third of image
            vf = (
                f"zoompan=z='min(zoom+0.002,1.25)':d={total_frames}:"
                f"x='3*iw/4-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )
        else:
            # Default: gentle zoom in
            vf = (
                f"zoompan=z='min(zoom+0.0015,1.15)':d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps},"
                f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d=0.5"
            )

        return vf

    def _detect_motion_type(self, video_prompt: str, scene_num: int) -> str:
        """Parse video prompt to determine the best motion effect."""
        vp = video_prompt.lower()

        if "zoom out" in vp or "zoom-out" in vp or "reveal" in vp:
            return "zoom_out"
        elif "pan right" in vp or "pan left-to-right" in vp or "left to right" in vp:
            return "pan_right"
        elif "pan left" in vp or "right-to-left" in vp or "right to left" in vp:
            return "pan_left"
        elif "pan up" in vp or "tilt up" in vp or "bottom to top" in vp:
            return "pan_up"
        elif "zoom" in vp and "left" in vp:
            return "zoom_in_left"
        elif "zoom" in vp and "right" in vp:
            return "zoom_in_right"
        else:
            # Cycle through motions based on scene number for variety
            motions = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in_right", "pan_up", "zoom_in_left"]
            return motions[scene_num % len(motions)]

    def build_scene_clip(
        self,
        image_path: Path,
        audio_path: Path,
        output_scene_path: Path,
        duration_sec: float,
        motion_type: str = "zoom_in",
        video_prompt: str = ""
    ) -> bool:
        """Render an animated scene clip with enhanced Ken Burns effects."""
        if not self.ffmpeg_available or not image_path.exists():
            return False

        # Handle case where audio is missing
        if not audio_path.exists():
            # Check for mp3 variant
            mp3_variant = audio_path.with_suffix(".mp3")
            if mp3_variant.exists():
                audio_path = mp3_variant
            else:
                logger.warning(f"Audio file not found: {audio_path}")
                return False

        output_scene_path.parent.mkdir(parents=True, exist_ok=True)
        total_frames = int(duration_sec * self.fps)

        vf_filter = self._get_motion_filter(motion_type, duration_sec, total_frames)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(duration_sec), "-i", str(image_path),
            "-i", str(audio_path),
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-shortest",
            "-c:a", "aac", "-b:a", "192k",
            str(output_scene_path)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
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
        """Assemble all scenes into a final episode.mp4 (16:9) with transitions."""
        output_video_dir.mkdir(parents=True, exist_ok=True)
        scenes = episode_data.get("scenes", [])
        rendered_clips = []
        scene_manifests = []

        temp_clips_dir = output_video_dir / "temp_scenes"
        temp_clips_dir.mkdir(parents=True, exist_ok=True)

        from src.rhubarb_generator import RhubarbGenerator
        rhubarb_gen = RhubarbGenerator()

        for scene in scenes:
            num = scene.get("scene_number", 1)
            duration = float(scene.get("duration_seconds", 15))
            img_path = images_dir / f"scene_{num:02d}.png" # Not used in 3D but kept for manifest compatibility
            audio_path = audio_dir / f"scene_{num:02d}_audio.wav"
            clip_path = temp_clips_dir / f"scene_{num:02d}.mp4"
            visemes_path = temp_clips_dir / f"scene_{num:02d}_visemes.json"
            v_prompt = scene.get("video_prompt", "")

            motion = "3d_blender_lipsync"

            success = False
            if self.ffmpeg_available and audio_path.exists():
                # 1. Generate Visemes
                viseme_success = rhubarb_gen.generate_visemes(audio_path, visemes_path)
                
                # 2. Render 3D Animation with Blender
                if viseme_success:
                    cmd = [
                        "blender", "-b", "-P", "src/blender_animator.py",
                        "--",
                        "--audio", str(audio_path),
                        "--visemes", str(visemes_path),
                        "--output", str(clip_path),
                        "--fps", str(self.fps)
                    ]
                    try:
                        logger.info(f"Rendering 3D scene {num} in Blender...")
                        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
                        if res.returncode == 0 and clip_path.exists():
                            success = True
                            rendered_clips.append(clip_path)
                        else:
                            logger.error(f"Blender render failed for scene {num}:\n{res.stderr.decode('utf-8', errors='ignore')}")
                    except Exception as e:
                        logger.error(f"Failed to execute Blender for scene {num}: {e}")

            scene_manifests.append({
                "scene_number": num,
                "duration_seconds": duration,
                "audio_file": str(audio_path),
                "visemes_file": str(visemes_path) if success else None,
                "motion": motion,
                "rendered": success
            })

        final_video_path = output_video_dir / "episode.mp4"
        manifest_path = output_video_dir / "video_manifest.json"

        assembled = False
        if self.ffmpeg_available and len(rendered_clips) == len(scenes) and rendered_clips:
            concat_list_file = output_video_dir / "concat_list.txt"
            concat_lines = [f"file '{clip.resolve().as_posix()}'" for clip in rendered_clips]
            save_text(concat_list_file, "\n".join(concat_lines))

            # Mix concatenated video with background music
            bg_music = audio_dir / "background_music.wav"
            if bg_music.exists():
                concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
                    "-i", str(bg_music),
                    "-filter_complex", "[1:a]volume=0.18[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
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
