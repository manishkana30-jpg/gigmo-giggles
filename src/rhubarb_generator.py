"""Wrapper for Rhubarb Lip Sync to generate visemes from audio."""

import os
import json
import subprocess
from pathlib import Path
from src.utils import setup_logger

logger = setup_logger("RhubarbGenerator")


class RhubarbGenerator:
    """Generates mouth shape visemes from audio using Rhubarb Lip Sync."""

    def __init__(self, rhubarb_path: str = "rhubarb"):
        self.rhubarb_path = rhubarb_path

    def check_available(self) -> bool:
        """Check if Rhubarb is installed and accessible."""
        try:
            res = subprocess.run([self.rhubarb_path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            return res.returncode == 0
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Rhubarb check failed: {e}")
            return False

    def generate_visemes(self, audio_path: Path, output_json_path: Path) -> bool:
        """
        Run Rhubarb on the given audio file and output visemes to JSON.
        Returns True if successful, False otherwise.
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False

        output_json_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.rhubarb_path,
            "-f", "json",
            "-o", str(output_json_path),
            str(audio_path)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if res.returncode == 0 and output_json_path.exists():
                logger.info(f"Generated visemes for {audio_path.name}")
                return True
            else:
                logger.warning(f"Rhubarb failed with exit code {res.returncode}: {res.stderr.decode('utf-8', errors='ignore')}")
                return False
        except Exception as e:
            logger.error(f"Failed to execute Rhubarb: {e}")
            return False
