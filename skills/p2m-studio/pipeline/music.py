"""
Step E: Music & Mix.
Loads background music (builtin CC0 or user-provided), trims/loops to
target duration, and applies ducking during VO segments.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import config

logger = logging.getLogger("p2m.music")


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [
                config.FFPROBE_BIN, "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _find_music_file(template: Dict[str, Any], user_music: Optional[str] = None) -> Optional[Path]:
    """Find the music file to use."""
    if user_music:
        p = Path(user_music)
        if p.exists():
            return p

    music_config = template.get("music", {})
    default_track = music_config.get("default_track", "")

    if default_track.startswith("builtin/"):
        track_name = default_track.replace("builtin/", "")
        builtin_path = config.MUSIC_DIR / track_name
        if builtin_path.exists():
            return builtin_path

    # Try any file in music dir
    if config.MUSIC_DIR.exists():
        for f in config.MUSIC_DIR.iterdir():
            if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"):
                return f

    return None


def _loop_or_trim_music(
    music_path: Path, target_duration: float, output_path: Path
) -> bool:
    """Loop or trim music to match target duration using ffmpeg."""
    music_duration = _get_audio_duration(music_path)
    if music_duration <= 0:
        return False

    try:
        if music_duration >= target_duration:
            # Trim with fade out
            fade_start = target_duration - 3.0
            subprocess.run(
                [
                    config.FFMPEG_BIN, "-y",
                    "-i", str(music_path),
                    "-t", str(target_duration),
                    "-af", f"afade=t=in:d=2,afade=t=out:st={fade_start}:d=3",
                    "-acodec", "libmp3lame", "-q:a", "2",
                    str(output_path),
                ],
                capture_output=True, timeout=60,
            )
        else:
            # Loop to fill duration, then trim
            loops_needed = int(target_duration / music_duration) + 1
            fade_start = target_duration - 3.0
            subprocess.run(
                [
                    config.FFMPEG_BIN, "-y",
                    "-stream_loop", str(loops_needed),
                    "-i", str(music_path),
                    "-t", str(target_duration),
                    "-af", f"afade=t=in:d=2,afade=t=out:st={fade_start}:d=3",
                    "-acodec", "libmp3lame", "-q:a", "2",
                    str(output_path),
                ],
                capture_output=True, timeout=60,
            )
        return output_path.exists()
    except Exception as e:
        logger.error(f"Music loop/trim failed: {e}")
        return False


def _apply_ducking(
    music_path: Path,
    script_data: Dict[str, Any],
    duck_volume: float,
    duck_fade_ms: int,
    default_volume: float,
    output_path: Path,
) -> bool:
    """Apply volume ducking during VO segments using ffmpeg."""
    # Collect all VO time ranges
    vo_ranges = []
    for seg in script_data.get("segments", []):
        for vo in seg.get("vo_files", []):
            vo_ranges.append((vo["start_sec"], vo["end_sec"]))

    if not vo_ranges:
        # No VO, just set volume
        try:
            subprocess.run(
                [
                    config.FFMPEG_BIN, "-y",
                    "-i", str(music_path),
                    "-af", f"volume={default_volume}",
                    "-acodec", "libmp3lame", "-q:a", "2",
                    str(output_path),
                ],
                capture_output=True, timeout=60,
            )
            return output_path.exists()
        except Exception:
            return False

    # Build volume filter with ducking
    fade_sec = duck_fade_ms / 1000.0
    volume_parts = [f"volume={default_volume}"]

    for start, end in vo_ranges:
        # Fade down before VO, fade up after
        duck_start = max(0, start - fade_sec)
        duck_end = end + fade_sec
        # Use volume expression for ducking
        volume_parts.append(
            f"volume=enable='between(t,{duck_start},{duck_end})':"
            f"volume={duck_volume / default_volume}"
        )

    # Simpler approach: use a single volume filter with key-framed expression
    # Build a complex expression that ducks during VO
    conditions = []
    for start, end in vo_ranges:
        conditions.append(f"between(t,{start},{end})")

    if conditions:
        duck_expr = "+".join(conditions)
        # When any VO is active, use duck_volume; otherwise default_volume
        af_filter = (
            f"volume='{default_volume} * (1 - ({duck_expr})) + "
            f"{duck_volume} * ({duck_expr})':eval=frame"
        )
    else:
        af_filter = f"volume={default_volume}"

    try:
        subprocess.run(
            [
                config.FFMPEG_BIN, "-y",
                "-i", str(music_path),
                "-af", af_filter,
                "-acodec", "libmp3lame", "-q:a", "2",
                str(output_path),
            ],
            capture_output=True, timeout=120,
        )
        return output_path.exists()
    except Exception as e:
        logger.error(f"Ducking failed: {e}")
        return False


def run_music(
    workspace_dir: str,
    template_id: str = None,
    user_music: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> Optional[str]:
    """
    Prepare background music: find/load, loop/trim, apply ducking.

    Returns path to processed music file, or None if no music available.
    """
    workspace = Path(workspace_dir)
    template_id = template_id or config.DEFAULT_TEMPLATE

    # Load template
    template_path = config.TEMPLATES_DIR / f"{template_id}.json"
    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    # Load storyboard for duration
    with open(workspace / "storyboard.json", "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    # Load script for VO timing
    script_path = workspace / "script.json"
    script_data = {}
    if script_path.exists():
        with open(script_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)

    target_duration = storyboard.get("actual_duration_sec", config.DEFAULT_DURATION_SEC)

    if progress_callback:
        progress_callback(10, "Finding music file")

    # Find music
    music_file = _find_music_file(template, user_music)
    if not music_file:
        logger.warning("No music file found, skipping music step")
        if progress_callback:
            progress_callback(100, "No music available")
        return None

    logger.info(f"Using music: {music_file}")

    # Create music workspace
    music_dir = workspace / "music"
    music_dir.mkdir(exist_ok=True)

    if progress_callback:
        progress_callback(30, "Trimming/looping music")

    # Loop/trim to target duration
    trimmed_path = music_dir / "trimmed.mp3"
    if not _loop_or_trim_music(music_file, target_duration, trimmed_path):
        logger.warning("Music trim/loop failed")
        if progress_callback:
            progress_callback(100, "Music processing failed")
        return None

    if progress_callback:
        progress_callback(60, "Applying ducking")

    # Apply ducking
    music_config = template.get("music", {})
    duck_volume = music_config.get("duck_volume", config.MUSIC_DUCK_VOLUME)
    duck_fade_ms = music_config.get("duck_fade_ms", config.MUSIC_DUCK_FADE_MS)
    default_volume = config.MUSIC_DEFAULT_VOLUME

    mixed_path = music_dir / "mixed.mp3"
    if script_data and _apply_ducking(
        trimmed_path, script_data, duck_volume, duck_fade_ms, default_volume, mixed_path
    ):
        logger.info(f"Music with ducking saved to {mixed_path}")
        if progress_callback:
            progress_callback(100, "Music ready")
        return str(mixed_path)
    else:
        # Fallback: just use trimmed version with flat volume
        logger.info("Using trimmed music without ducking")
        if progress_callback:
            progress_callback(100, "Music ready (no ducking)")
        return str(trimmed_path)
