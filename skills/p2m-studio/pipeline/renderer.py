"""
Step F: Assemble & Render.
Generates timeline JSON, builds FFmpeg filter_complex command,
and renders preview (720p) + final (1080p) videos.
"""
from __future__ import annotations

import json
import logging
import subprocess
import shlex
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import config

logger = logging.getLogger("p2m.renderer")


def _generate_srt(subtitles_data: Dict[str, Any], output_path: Path) -> None:
    """Generate SRT subtitle file from subtitles.json."""
    entries = subtitles_data.get("entries", [])
    lines = []
    for i, entry in enumerate(entries, 1):
        start = _sec_to_srt_time(entry["start_sec"])
        end = _sec_to_srt_time(entry["end_sec"])
        text = entry["text"]
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _sec_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_ken_burns_filter(
    input_idx: int,
    motion: Dict[str, Any],
    width: int,
    height: int,
    fps: int,
) -> str:
    """Build zoompan filter for Ken Burns effect on a single image."""
    duration = motion.get("duration", 5.0)
    total_frames = int(duration * fps)
    start_rect = motion.get("start_rect", [0, 0, 100, 100])
    end_rect = motion.get("end_rect", [5, 5, 95, 95])

    # Convert percentage rects to actual zoom/pan values
    # zoompan works with zoom factor and x/y offsets
    # Start zoom: 100/(end-start) percentage -> zoom factor
    s_w = (start_rect[2] - start_rect[0]) / 100.0
    s_h = (start_rect[3] - start_rect[1]) / 100.0
    e_w = (end_rect[2] - end_rect[0]) / 100.0
    e_h = (end_rect[3] - end_rect[1]) / 100.0

    start_zoom = 1.0 / min(s_w, s_h)
    end_zoom = 1.0 / min(e_w, e_h)

    # x/y offsets (center of crop region)
    s_cx = (start_rect[0] + start_rect[2]) / 200.0
    s_cy = (start_rect[1] + start_rect[3]) / 200.0
    e_cx = (end_rect[0] + end_rect[2]) / 200.0
    e_cy = (end_rect[1] + end_rect[3]) / 200.0

    # Zoompan filter expression
    # z: interpolate from start_zoom to end_zoom
    # x, y: interpolate center position
    zoom_expr = f"'{start_zoom}+({end_zoom}-{start_zoom})*on/{total_frames}'"
    x_expr = f"'(iw-iw/zoom)/2+({e_cx}-{s_cx})*iw*(on/{total_frames})'"
    y_expr = f"'(ih-ih/zoom)/2+({e_cy}-{s_cy})*ih*(on/{total_frames})'"

    return (
        f"[{input_idx}:v]scale={width*2}:{height*2},"
        f"zoompan=z={zoom_expr}:x={x_expr}:y={y_expr}"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
        f"[v{input_idx}]"
    )


def _premix_vo_audio(
    workspace: Path,
    script_data: Dict[str, Any],
) -> Optional[Path]:
    """Pre-mix all VO audio files into a single track with proper timing."""
    vo_files = []
    for seg in script_data.get("segments", []):
        for vo in seg.get("vo_files", []):
            if Path(vo["file"]).exists():
                vo_files.append(vo)

    if not vo_files:
        return None

    premix_path = workspace / "vo" / "premixed.mp3"

    if len(vo_files) == 1:
        # Single VO file — just add delay
        vo = vo_files[0]
        delay_ms = int(vo["start_sec"] * 1000)
        try:
            subprocess.run(
                [
                    config.FFMPEG_BIN, "-y",
                    "-i", vo["file"],
                    "-af", f"adelay={delay_ms}|{delay_ms}",
                    "-acodec", "libmp3lame", "-q:a", "2",
                    str(premix_path),
                ],
                capture_output=True, timeout=30,
            )
            if premix_path.exists():
                return premix_path
        except Exception as e:
            logger.warning(f"VO premix failed: {e}")
        return None

    # Multiple VO files: use ffmpeg to delay each and mix
    # Batch in groups of 8 to avoid filter complexity limits
    batch_size = 8
    intermediate_files = []

    for batch_start in range(0, len(vo_files), batch_size):
        batch = vo_files[batch_start:batch_start + batch_size]
        batch_out = workspace / "vo" / f"batch_{batch_start}.mp3"

        cmd = [config.FFMPEG_BIN, "-y"]
        filter_parts = []
        for i, vo in enumerate(batch):
            cmd.extend(["-i", vo["file"]])
            delay_ms = int(vo["start_sec"] * 1000)
            filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")

        labels = "".join(f"[a{i}]" for i in range(len(batch)))
        filter_parts.append(f"{labels}amix=inputs={len(batch)}:dropout_transition=0:normalize=0[out]")
        filter_str = ";\n".join(filter_parts)

        cmd.extend(["-filter_complex", filter_str, "-map", "[out]"])
        cmd.extend(["-acodec", "libmp3lame", "-q:a", "2", str(batch_out)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and batch_out.exists():
                intermediate_files.append(batch_out)
            else:
                logger.warning(f"VO batch mix failed: {result.stderr[-200:]}")
        except Exception as e:
            logger.warning(f"VO batch mix error: {e}")

    if not intermediate_files:
        return None

    if len(intermediate_files) == 1:
        intermediate_files[0].rename(premix_path)
        return premix_path

    # Mix intermediate batches
    cmd = [config.FFMPEG_BIN, "-y"]
    filter_parts = []
    for i, f in enumerate(intermediate_files):
        cmd.extend(["-i", str(f)])
        filter_parts.append(f"[{i}:a]")

    labels = "".join(filter_parts)
    cmd.extend([
        "-filter_complex",
        f"{labels}amix=inputs={len(intermediate_files)}:dropout_transition=0:normalize=0[out]",
        "-map", "[out]",
        "-acodec", "libmp3lame", "-q:a", "2",
        str(premix_path),
    ])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and premix_path.exists():
            # Cleanup intermediates
            for f in intermediate_files:
                f.unlink(missing_ok=True)
            return premix_path
    except Exception as e:
        logger.warning(f"VO final mix error: {e}")

    return None


def _premix_all_audio(
    workspace: Path,
    script_data: Dict[str, Any],
    music_path: Optional[str],
) -> Optional[Path]:
    """Pre-mix VO + music into a single audio file for the final render."""
    vo_premix = _premix_vo_audio(workspace, script_data)
    has_music = music_path and Path(music_path).exists()

    if not vo_premix and not has_music:
        return None

    if vo_premix and not has_music:
        return vo_premix

    if not vo_premix and has_music:
        return Path(music_path)

    # Both exist: mix them
    final_audio = workspace / "audio_final.mp3"
    try:
        result = subprocess.run(
            [
                config.FFMPEG_BIN, "-y",
                "-i", str(vo_premix),
                "-i", music_path,
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:dropout_transition=0[out]",
                "-map", "[out]",
                "-acodec", "libmp3lame", "-q:a", "2",
                str(final_audio),
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and final_audio.exists():
            return final_audio
        logger.warning(f"Audio final mix failed: {result.stderr[-200:]}")
    except Exception as e:
        logger.warning(f"Audio final mix error: {e}")

    # Fallback: return whichever exists
    return vo_premix if vo_premix else Path(music_path)


def _render_video(
    workspace: Path,
    storyboard: Dict[str, Any],
    subtitles_path: Optional[Path],
    music_path: Optional[str],
    script_data: Dict[str, Any],
    width: int,
    height: int,
    crf: int,
    fps: int,
    output_path: Path,
    progress_callback: Optional[Callable] = None,
) -> bool:
    """Render video using FFmpeg with Ken Burns, transitions, subtitles, and audio."""

    segments = storyboard.get("segments", [])
    if not segments:
        logger.error("No segments to render")
        return False

    # Collect all image inputs and their durations
    all_images = []  # (image_path, duration, motion_params)
    for segment in segments:
        motions = segment.get("motion", [])
        for motion in motions:
            asset_id = motion["asset_id"]
            img_path = workspace / "assets" / f"{asset_id}.jpg"
            if img_path.exists():
                all_images.append((str(img_path), motion))

    if not all_images:
        logger.error("No images found for rendering")
        return False

    logger.info(f"Rendering {len(all_images)} images to {width}x{height}")

    # Build FFmpeg command with filter_complex
    # Strategy: use concat demuxer approach for simplicity and reliability
    # Each image -> zoompan -> crossfade chain

    input_args = []
    filter_parts = []
    concat_inputs = []

    for i, (img_path, motion) in enumerate(all_images):
        input_args.extend(["-loop", "1", "-t", str(motion["duration"]), "-i", img_path])
        # Scale and apply Ken Burns
        kb_filter = _build_ken_burns_filter(i, motion, width, height, fps)
        filter_parts.append(kb_filter)
        concat_inputs.append(f"[v{i}]")

    # Concatenate all video segments with crossfade
    if len(all_images) > 1:
        # Apply crossfade between consecutive segments
        xfade_duration = min(0.8, config.TRANSITION_DURATION_SEC)
        current_label = concat_inputs[0]

        for i in range(1, len(concat_inputs)):
            offset = sum(
                all_images[j][1]["duration"] for j in range(i)
            ) - xfade_duration * i
            offset = max(0, offset)
            out_label = f"[xf{i}]"
            filter_parts.append(
                f"{current_label}{concat_inputs[i]}"
                f"xfade=transition=fade:duration={xfade_duration}:offset={offset}"
                f"{out_label}"
            )
            current_label = out_label

        video_out_label = current_label
    else:
        video_out_label = concat_inputs[0]

    # Note: subtitles are burned in a second pass to avoid filter_complex escaping issues
    if video_out_label.startswith("[") and video_out_label.endswith("]"):
        final_video_label = video_out_label
    else:
        final_video_label = "[vout]"

    # Build filter_complex string
    filter_complex = ";".join(filter_parts)

    # Pre-mix ALL audio (VO + music) into one file
    final_audio = _premix_all_audio(workspace, script_data, music_path)

    audio_input_idx = len(all_images)
    audio_map = None
    if final_audio and final_audio.exists():
        input_args.extend(["-i", str(final_audio)])
        audio_map = f"{audio_input_idx}:a"

    # Build final ffmpeg command
    cmd = [config.FFMPEG_BIN, "-y"]
    cmd.extend(input_args)
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", final_video_label])
    if audio_map:
        cmd.extend(["-map", audio_map])
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ])
    if audio_map:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-shortest", str(output_path)])

    logger.info(f"FFmpeg command: {' '.join(cmd[:20])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min max
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {result.stderr[-500:]}")
            return _render_simple_fallback(
                workspace, all_images, music_path, width, height, crf, fps, output_path
            )
        # Second pass: burn subtitles if available
        if subtitles_path and subtitles_path.exists():
            _burn_subtitles(output_path, subtitles_path, width)
        return output_path.exists()
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg render timed out (30 min)")
        return False
    except Exception as e:
        logger.error(f"Render error: {e}")
        return _render_simple_fallback(
            workspace, all_images, music_path, width, height, crf, fps, output_path
        )


def _generate_ass(srt_path: Path, width: int) -> Path:
    """Generate ASS subtitle file from SRT with embedded styling (avoids force_style escaping)."""
    ass_path = srt_path.with_suffix(".ass")
    font_size = int(42 * width / 1920)

    # Parse SRT
    entries = []
    with open(srt_path, "r", encoding="utf-8") as f:
        blocks = f.read().strip().split("\n\n")
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                time_line = lines[1]
                text = " ".join(lines[2:])
                parts = time_line.split(" --> ")
                if len(parts) == 2:
                    entries.append((parts[0].strip(), parts[1].strip(), text))

    def _srt_to_ass_time(t: str) -> str:
        """Convert SRT time (HH:MM:SS,mmm) to ASS time (H:MM:SS.cc)."""
        t = t.replace(",", ".")
        parts = t.split(":")
        h, m = int(parts[0]), int(parts[1])
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        cs = int(s_parts[1][:2]) if len(s_parts) > 1 else 0
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write(f"PlayResX: {width}\n")
        f.write(f"PlayResY: {int(width * 9 / 16)}\n\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,Noto Sans SC,{font_size},"
                f"&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
                f"0,0,0,0,100,100,0,0,1,2,1,2,10,10,40,1\n\n")
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for start, end, text in entries:
            ass_start = _srt_to_ass_time(start)
            ass_end = _srt_to_ass_time(end)
            f.write(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{text}\n")

    logger.info(f"ASS subtitle generated: {ass_path}")
    return ass_path


def _has_subtitle_filter() -> bool:
    """Check if ffmpeg has subtitle/ass filter support (requires libass)."""
    try:
        result = subprocess.run(
            [config.FFMPEG_BIN, "-filters"],
            capture_output=True, text=True, timeout=5,
        )
        return "subtitles" in result.stdout or " ass " in result.stdout
    except Exception:
        return False


def _burn_subtitles(video_path: Path, srt_path: Path, width: int) -> None:
    """Burn subtitles into video (second pass). Uses ASS file with embedded styling."""
    if not _has_subtitle_filter():
        logger.info("Subtitle burn skipped: ffmpeg lacks libass. SRT file available for external use.")
        return

    ass_path = _generate_ass(srt_path, width)
    temp_path = video_path.parent / f"{video_path.stem}_sub_tmp.mp4"

    # Escape path for ffmpeg subtitles filter
    ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
    cmd = [
        config.FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-vf", f"ass={ass_escaped}",
        "-c:v", "libx264", "-crf", "20",
        "-c:a", "copy",
        str(temp_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0 and temp_path.exists():
            temp_path.replace(video_path)
            logger.info(f"Subtitles burned into {video_path.name}")
        else:
            logger.warning(f"Subtitle burn failed: {result.stderr[-200:]}")
            temp_path.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Subtitle burn error: {e}")
        temp_path.unlink(missing_ok=True)


def _render_simple_fallback(
    workspace: Path,
    all_images: List,
    music_path: Optional[str],
    width: int,
    height: int,
    crf: int,
    fps: int,
    output_path: Path,
) -> bool:
    """Simplified fallback render: no transitions, no subtitles, just concat images."""
    logger.info("Using simplified fallback render")

    # Create concat file
    concat_path = workspace / "concat.txt"
    with open(concat_path, "w") as f:
        for img_path, motion in all_images:
            duration = motion.get("duration", 5.0)
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {duration}\n")
        # Repeat last image to avoid ffmpeg concat issue
        if all_images:
            f.write(f"file '{all_images[-1][0]}'\n")

    cmd = [config.FFMPEG_BIN, "-y"]

    # All -i inputs must come first
    cmd.extend(["-f", "concat", "-safe", "0", "-i", str(concat_path)])
    if music_path and Path(music_path).exists():
        cmd.extend(["-i", music_path])

    # Output options
    cmd.extend([
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
    ])
    if music_path and Path(music_path).exists():
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-shortest", str(output_path)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            logger.error(f"Fallback render also failed: {result.stderr[-300:]}")
            return False
        return output_path.exists()
    except Exception as e:
        logger.error(f"Fallback render error: {e}")
        return False


def run_render(
    workspace_dir: str,
    template_id: str = None,
    mode: str = "both",
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Optional[str]]:
    """
    Render video from pipeline artifacts.

    Args:
        workspace_dir: Pipeline workspace.
        template_id: Template ID.
        mode: "preview", "final", or "both".
        progress_callback: Optional progress callback.

    Returns:
        {"preview": path_or_none, "final": path_or_none, "srt": path_or_none}
    """
    workspace = Path(workspace_dir)
    output_dir = workspace / "output"
    output_dir.mkdir(exist_ok=True)

    # Load artifacts
    with open(workspace / "storyboard.json", "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    script_data = {}
    script_path = workspace / "script.json"
    if script_path.exists():
        with open(script_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)

    subtitles_data = {}
    subtitles_json = workspace / "subtitles.json"
    if subtitles_json.exists():
        with open(subtitles_json, "r", encoding="utf-8") as f:
            subtitles_data = json.load(f)

    # Generate SRT
    srt_path = output_dir / "subtitles.srt"
    if subtitles_data:
        _generate_srt(subtitles_data, srt_path)
        logger.info(f"SRT generated: {srt_path}")

    # Find music
    music_dir = workspace / "music"
    music_path = None
    for name in ["mixed.mp3", "trimmed.mp3"]:
        mp = music_dir / name
        if mp.exists():
            music_path = str(mp)
            break

    results = {"preview": None, "final": None, "srt": str(srt_path) if srt_path.exists() else None}

    # Render preview
    if mode in ("preview", "both"):
        if progress_callback:
            progress_callback(10, "Rendering preview (720p)")

        preview_path = output_dir / "preview.mp4"
        ok = _render_video(
            workspace, storyboard,
            srt_path if srt_path.exists() else None,
            music_path, script_data,
            config.RENDER_PREVIEW_WIDTH, config.RENDER_PREVIEW_HEIGHT,
            config.RENDER_PREVIEW_CRF, config.RENDER_FPS,
            preview_path, progress_callback,
        )
        if ok:
            results["preview"] = str(preview_path)
            logger.info(f"Preview rendered: {preview_path}")

    # Render final
    if mode in ("final", "both"):
        if progress_callback:
            progress_callback(50, "Rendering final (1080p)")

        final_path = output_dir / "final.mp4"
        ok = _render_video(
            workspace, storyboard,
            srt_path if srt_path.exists() else None,
            music_path, script_data,
            config.RENDER_FINAL_WIDTH, config.RENDER_FINAL_HEIGHT,
            config.RENDER_FINAL_CRF, config.RENDER_FPS,
            final_path, progress_callback,
        )
        if ok:
            results["final"] = str(final_path)
            logger.info(f"Final rendered: {final_path}")

    if progress_callback:
        progress_callback(100, "Render complete")

    # Write timeline.json (metadata about what was rendered)
    timeline = {
        "version": "1.0",
        "storyboard": storyboard,
        "script": script_data,
        "subtitles": subtitles_data,
        "music_path": music_path,
        "outputs": results,
    }
    with open(workspace / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

    return results
