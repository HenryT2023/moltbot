"""
Step: Beat Detection & Video-to-Beat Alignment.
Uses librosa to detect music beats, then maps video clips to beat intervals
so transitions happen on the beat.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import config

logger = logging.getLogger("p2m.beat_sync")


def detect_beats(audio_path: str) -> List[float]:
    """
    Detect beat times in an audio file using librosa.
    Returns a sorted list of beat times in seconds.
    """
    import librosa

    y, sr = librosa.load(audio_path, sr=22050)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    logger.info(f"Detected {len(beat_times)} beats at ~{float(tempo):.0f} BPM")
    return beat_times


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds."""
    import librosa

    y, sr = librosa.load(audio_path, sr=22050)
    return float(len(y) / sr)


def align_clips_to_beats(
    num_clips: int,
    beat_times: List[float],
    clip_duration: float = 6.0,
    audio_duration: float = 0.0,
) -> List[Dict[str, float]]:
    """
    Assign each clip a start time and display duration aligned to beats.

    Strategy:
    - Divide beats into groups (one group per clip)
    - Each clip starts at the first beat of its group
    - Each clip's display duration = time to next clip's start
    - Clips may be trimmed or speed-adjusted to fit the beat interval

    Returns list of {"start": float, "duration": float, "speed": float}
    """
    if not beat_times or num_clips == 0:
        # Fallback: equal duration
        dur = clip_duration
        return [{"start": i * dur, "duration": dur, "speed": 1.0} for i in range(num_clips)]

    # Filter beats within audio duration
    if audio_duration > 0:
        beat_times = [b for b in beat_times if b < audio_duration]

    if len(beat_times) < 2:
        dur = audio_duration / num_clips if audio_duration > 0 else clip_duration
        return [{"start": i * dur, "duration": dur, "speed": 1.0} for i in range(num_clips)]

    # Distribute beats evenly across clips
    beats_per_clip = max(1, len(beat_times) // num_clips)
    timeline = []

    for i in range(num_clips):
        beat_idx = i * beats_per_clip
        if beat_idx >= len(beat_times):
            beat_idx = len(beat_times) - 1

        start = beat_times[beat_idx]

        # End is the next clip's start beat, or audio end
        next_beat_idx = (i + 1) * beats_per_clip
        if next_beat_idx >= len(beat_times) or i == num_clips - 1:
            end = audio_duration if audio_duration > 0 else start + clip_duration
        else:
            end = beat_times[next_beat_idx]

        duration = end - start
        # Avoid zero or negative duration
        if duration <= 0.5:
            duration = clip_duration

        # Calculate speed factor: how fast to play the 6s clip to fit this duration
        speed = clip_duration / duration if duration > 0 else 1.0
        # Clamp speed to reasonable range (0.5x to 2.0x)
        speed = max(0.5, min(2.0, speed))

        timeline.append({
            "start": round(start, 3),
            "duration": round(duration, 3),
            "speed": round(speed, 3),
        })

    return timeline


def run_beat_sync(
    workspace_dir: str,
    music_path: str,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Detect beats in music and create a beat-aligned timeline for video clips.

    Reads workspace_dir/clips.json, outputs beat_timeline.json.
    """
    workspace = Path(workspace_dir)

    # Load clips manifest
    clips_path = workspace / "clips.json"
    with open(clips_path, "r", encoding="utf-8") as f:
        clips = json.load(f)

    num_clips = len(clips)
    if num_clips == 0:
        raise ValueError("No clips found in clips.json")

    if progress_callback:
        progress_callback(20, "Detecting beats")

    # Detect beats
    beat_times = detect_beats(music_path)
    audio_duration = get_audio_duration(music_path)

    if progress_callback:
        progress_callback(60, "Aligning clips to beats")

    # Create beat-aligned timeline
    timeline = align_clips_to_beats(
        num_clips=num_clips,
        beat_times=beat_times,
        clip_duration=6.0,
        audio_duration=audio_duration,
    )

    # Merge clip info with timeline
    result = {
        "audio_path": music_path,
        "audio_duration": round(audio_duration, 3),
        "num_beats": len(beat_times),
        "beat_times": [round(b, 3) for b in beat_times],
        "clips": [],
    }

    for i, (clip, timing) in enumerate(zip(clips, timeline)):
        result["clips"].append({
            "index": i,
            "clip_path": clip["clip_path"],
            "image_path": clip.get("image_path", ""),
            "start": timing["start"],
            "duration": timing["duration"],
            "speed": timing["speed"],
        })

    # Save
    output_path = workspace / "beat_timeline.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(100, f"{num_clips} clips aligned to {len(beat_times)} beats")

    logger.info(f"Beat timeline saved: {output_path}")
    return result
