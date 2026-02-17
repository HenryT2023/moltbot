"""
Step: Video Composition — Concatenate AI video clips with beat-synced
transitions and overlay background music using FFmpeg.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import config

logger = logging.getLogger("p2m.composer")


def _get_video_duration(video_path: str) -> float:
    """Get video duration via ffprobe."""
    try:
        result = subprocess.run(
            [
                config.FFPROBE_BIN, "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 6.0


def _speed_adjust_clip(
    input_path: str, speed: float, duration: float, output_path: str
) -> str:
    """
    Adjust clip playback speed and trim to exact duration.
    speed > 1.0 = faster, speed < 1.0 = slower.
    Returns output path.
    """
    if abs(speed - 1.0) < 0.05:
        # No speed adjustment needed, just trim
        subprocess.run(
            [
                config.FFMPEG_BIN, "-y",
                "-i", input_path,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-an",
                output_path,
            ],
            capture_output=True, timeout=60,
        )
    else:
        # Speed adjust using setpts filter
        pts_factor = 1.0 / speed
        subprocess.run(
            [
                config.FFMPEG_BIN, "-y",
                "-i", input_path,
                "-filter:v", f"setpts={pts_factor}*PTS",
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-an",
                output_path,
            ],
            capture_output=True, timeout=60,
        )
    return output_path


def _normalize_clip(input_path: str, output_path: str, width: int, height: int) -> str:
    """Normalize clip to target resolution and pixel format for concat."""
    subprocess.run(
        [
            config.FFMPEG_BIN, "-y",
            "-i", input_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", str(config.RENDER_FPS),
            "-an",
            output_path,
        ],
        capture_output=True, timeout=60,
    )
    return output_path


def _make_text_card(
    text: str, output_path: str, duration: float = 4.0,
    width: int = 1280, height: int = 720,
    fade_in: float = 1.5, fade_out: float = 1.5,
    is_ending: bool = False,
) -> str:
    """Generate a French cinema style title/ending card.

    Text format: lines separated by \\n.
    Lines starting with ~ are dedication lines (smaller, positioned lower).

    Opening: title centered with generous top margin (French film style).
    Ending: main line upper-center, dedication lines in lower third.
    """
    from PIL import Image, ImageDraw, ImageFont

    FONT_PATH = "/System/Library/Fonts/Palatino.ttc"
    FONT_FALLBACK = "/System/Library/Fonts/HelveticaNeue.ttc"
    # Palatino italic is index 1 in .ttc, regular is index 0
    TITLE_SIZE = 48
    DEDIC_SIZE = 28
    DEDIC_SPACING = 12

    try:
        font_title = ImageFont.truetype(FONT_PATH, TITLE_SIZE, index=1)  # italic
        font_dedic = ImageFont.truetype(FONT_PATH, DEDIC_SIZE, index=1)  # italic
    except Exception:
        try:
            font_title = ImageFont.truetype(FONT_PATH, TITLE_SIZE)
            font_dedic = ImageFont.truetype(FONT_PATH, DEDIC_SIZE)
        except Exception:
            font_title = ImageFont.truetype(FONT_FALLBACK, TITLE_SIZE)
            font_dedic = ImageFont.truetype(FONT_FALLBACK, DEDIC_SIZE)

    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    raw_lines = text.split("\\n") if "\\n" in text else [text]

    # Separate main lines and dedication lines (prefixed with ~)
    main_lines = []
    dedic_lines = []
    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("~"):
            dedic_lines.append(stripped[1:].strip())
        else:
            main_lines.append(stripped)

    color_main = (230, 225, 215)   # warm off-white
    color_dedic = (170, 165, 155)  # muted warm grey

    # Draw main text — centered vertically (or slightly above center for endings)
    if main_lines:
        main_total_h = 0
        for ml in main_lines:
            bbox = draw.textbbox((0, 0), ml, font=font_title)
            main_total_h += bbox[3] - bbox[1] + 20
        if is_ending and dedic_lines:
            y_main = int(height * 0.35) - main_total_h // 2
        else:
            y_main = (height - main_total_h) // 2
        for ml in main_lines:
            bbox = draw.textbbox((0, 0), ml, font=font_title)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            draw.text((x, y_main), ml, fill=color_main, font=font_title)
            y_main += bbox[3] - bbox[1] + 20

    # Draw dedication lines — lower third of frame
    if dedic_lines:
        y_ded = int(height * 0.68)
        for dl in dedic_lines:
            bbox = draw.textbbox((0, 0), dl, font=font_dedic)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            draw.text((x, y_ded), dl, fill=color_dedic, font=font_dedic)
            y_ded += bbox[3] - bbox[1] + DEDIC_SPACING

    png_path = output_path.replace(".mp4", ".png")
    img.save(png_path)

    result = subprocess.run(
        [
            config.FFMPEG_BIN, "-y",
            "-loop", "1", "-i", png_path,
            "-t", str(duration),
            "-vf", f"scale={width}:{height},format=yuv420p,fps={config.RENDER_FPS},"
                   f"fade=t=in:d={fade_in},fade=t=out:st={duration - fade_out}:d={fade_out}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            output_path,
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error(f"Title card failed: {result.stderr[-300:]}")
    Path(png_path).unlink(missing_ok=True)
    return output_path


def compose_video(
    timeline: Dict[str, Any],
    output_path: str,
    music_path: Optional[str] = None,
    width: int = 1280,
    height: int = 720,
    transition_frames: int = 15,
    progress_callback: Optional[Callable] = None,
    title_text: Optional[str] = None,
    ending_text: Optional[str] = None,
) -> str:
    """
    Compose final video from beat-aligned clip timeline + music.

    1. Speed-adjust each clip to fit its beat interval
    2. Normalize resolution
    3. Concatenate with crossfade transitions
    4. Overlay music track

    Returns path to final output video.
    """
    clips = timeline.get("clips", [])
    if not clips:
        raise ValueError("No clips in timeline")

    work_dir = Path(output_path).parent / "compose_work"
    work_dir.mkdir(exist_ok=True)

    total_steps = len(clips) + 2  # normalize + concat + mux
    done = 0

    # Step 1: Speed-adjust and normalize each clip
    normalized = []
    for clip_info in clips:
        clip_path = clip_info["clip_path"]
        if not clip_path or not Path(clip_path).exists():
            logger.warning(f"Skipping missing clip: {clip_path}")
            continue

        idx = clip_info["index"]
        speed = clip_info.get("speed", 1.0)
        duration = clip_info.get("duration", 6.0)

        # Speed adjust
        speed_path = str(work_dir / f"speed_{idx:04d}.mp4")
        _speed_adjust_clip(clip_path, speed, duration, speed_path)

        # Normalize resolution
        norm_path = str(work_dir / f"norm_{idx:04d}.mp4")
        _normalize_clip(speed_path, norm_path, width, height)
        normalized.append(norm_path)

        done += 1
        if progress_callback:
            pct = int(done / total_steps * 100)
            progress_callback(pct, f"Prepared {done}/{len(clips)} clips")

    if not normalized:
        raise ValueError("No valid clips after processing")

    # Insert title and ending cards
    if title_text:
        title_path = str(work_dir / "title_card.mp4")
        _make_text_card(title_text, title_path, duration=4.0, width=width, height=height)
        normalized.insert(0, title_path)
    if ending_text:
        ending_path = str(work_dir / "ending_card.mp4")
        _make_text_card(ending_text, ending_path, duration=5.0, width=width, height=height, is_ending=True)
        normalized.append(ending_path)

    # Step 2: Concatenate with crossfade transitions
    if progress_callback:
        progress_callback(int((done + 1) / total_steps * 100), "Concatenating clips")

    concat_path = str(work_dir / "concat.mp4")
    transition_sec = transition_frames / config.RENDER_FPS

    if len(normalized) == 1:
        # Single clip, just copy
        concat_path = normalized[0]
    elif len(normalized) <= 20:
        # Use xfade filter for crossfade transitions
        _concat_with_xfade(normalized, concat_path, transition_sec)
    else:
        # Too many clips for complex filter, use concat demuxer
        _concat_simple(normalized, concat_path)

    # Step 3: Mux with music
    if progress_callback:
        progress_callback(int((done + 2) / total_steps * 100), "Adding music")

    final_music = music_path or timeline.get("audio_path")
    if final_music and Path(final_music).exists():
        _mux_with_music(concat_path, final_music, output_path)
    else:
        # No music, just copy
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [config.FFMPEG_BIN, "-y", "-i", concat_path, "-c", "copy", output_path],
            capture_output=True, timeout=60,
        )

    if progress_callback:
        progress_callback(100, "Composition complete")

    logger.info(f"Final video: {output_path}")
    return output_path


def _concat_with_xfade(clips: List[str], output: str, transition_sec: float) -> None:
    """Concatenate clips with crossfade transitions using xfade filter."""
    if len(clips) < 2:
        return

    # Build complex filter graph
    inputs = []
    for c in clips:
        inputs.extend(["-i", c])

    # Chain xfade filters
    filter_parts = []
    current_offset = 0.0
    prev_label = "[0:v]"

    for i in range(1, len(clips)):
        clip_dur = _get_video_duration(clips[i - 1])
        current_offset += clip_dur - transition_sec

        if current_offset < 0:
            current_offset = 0

        out_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{prev_label}[{i}:v]xfade=transition=fade:duration={transition_sec}"
            f":offset={current_offset:.3f}{out_label}"
        )
        prev_label = out_label

    filter_complex = ";".join(filter_parts)

    cmd = [config.FFMPEG_BIN, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", str(config.RENDER_FPS),
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.warning(f"xfade failed, falling back to simple concat: {result.stderr[-200:]}")
        _concat_simple(clips, output)


def _concat_simple(clips: List[str], output: str) -> None:
    """Simple concat using concat demuxer (no transitions)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for c in clips:
            f.write(f"file '{c}'\n")
        list_path = f.name

    subprocess.run(
        [
            config.FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", str(config.RENDER_FPS),
            output,
        ],
        capture_output=True, timeout=300,
    )
    Path(list_path).unlink(missing_ok=True)


def _mux_with_music(video_path: str, music_path: str, output_path: str) -> None:
    """Mux video with music, trim music to video length."""
    video_dur = _get_video_duration(video_path)
    fade_start = max(0, video_dur - 3.0)

    subprocess.run(
        [
            config.FFMPEG_BIN, "-y",
            "-i", video_path,
            "-i", music_path,
            "-c:v", "copy",
            "-af", f"afade=t=in:d=2,afade=t=out:st={fade_start}:d=3,"
                   f"volume={config.MUSIC_DEFAULT_VOLUME}",
            "-t", str(video_dur),
            "-shortest",
            output_path,
        ],
        capture_output=True, timeout=300,
    )
    logger.info(f"Muxed video+music: {output_path} ({video_dur:.1f}s)")


def run_compose(
    workspace_dir: str,
    music_path: Optional[str] = None,
    output_name: str = "final.mp4",
    progress_callback: Optional[Callable] = None,
    title_text: Optional[str] = None,
    ending_text: Optional[str] = None,
) -> str:
    """
    Full composition pipeline: read beat_timeline.json → compose video.
    Returns path to final video.
    """
    workspace = Path(workspace_dir)
    output_path = str(workspace / output_name)

    timeline_path = workspace / "beat_timeline.json"
    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline = json.load(f)
    else:
        # No beat sync — build a simple timeline from clips.json
        clips_path = workspace / "clips.json"
        with open(clips_path, "r", encoding="utf-8") as f:
            clips_list = json.load(f)
        # Trim each clip to first 3s to avoid face distortion from long generation
        CLIP_TRIM_SEC = 3.0
        timeline = {
            "clips": [
                {
                    "index": c["index"],
                    "clip_path": c["clip_path"],
                    "speed": 1.0,
                    "duration": CLIP_TRIM_SEC,
                }
                for c in clips_list if c.get("clip_path")
            ],
        }

    actual_music = music_path or timeline.get("audio_path")

    return compose_video(
        timeline=timeline,
        output_path=output_path,
        music_path=actual_music,
        width=config.RENDER_PREVIEW_WIDTH,
        height=config.RENDER_PREVIEW_HEIGHT,
        progress_callback=progress_callback,
        title_text=title_text,
        ending_text=ending_text,
    )
