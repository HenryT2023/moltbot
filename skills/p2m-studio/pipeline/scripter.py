"""
Step D: Script & VO Generation.
Uses LLM to generate Chinese narration per act, then edge-tts to synthesize
audio, and derives subtitle timestamps from audio duration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai

import config

logger = logging.getLogger("p2m.scripter")


def _build_narration_prompt(
    segment: Dict[str, Any],
    template: Dict[str, Any],
    assets: List[Dict[str, Any]],
) -> str:
    """Build LLM prompt for narration generation."""
    # Find the act in template
    act_id = segment["act_id"]
    act_config = None
    for act in template.get("acts", []):
        if act["id"] == act_id:
            act_config = act
            break

    narration_hint = ""
    if act_config:
        narration_hint = act_config.get("narration_prompt", "")

    # Collect captions for photos in this segment
    asset_ids = set(segment.get("asset_ids", []))
    captions = []
    for asset in assets:
        if asset["id"] in asset_ids:
            analysis = asset.get("analysis") or {}
            cap = analysis.get("caption_zh", "")
            if cap:
                captions.append(cap)

    captions_text = "\n".join(f"- {c}" for c in captions) if captions else "(no captions)"

    act_name = segment.get("act_name_zh", "")
    duration = segment.get("duration_sec", 30)

    prompt = f"""You are writing narration for a memorial movie segment.

Segment: "{act_name}" (duration: {duration:.0f} seconds)

Photos in this segment describe:
{captions_text}

Style guidance: {narration_hint}

Requirements:
1. Write 2-4 short sentences in Chinese
2. Tone: mature, restrained, not sappy or cliche
3. Total spoken duration should fit within {duration:.0f} seconds (roughly 3-4 characters per second)
4. Each sentence should be a standalone subtitle line

Respond with ONLY a JSON array of strings (no markdown):
["sentence 1", "sentence 2", "sentence 3"]"""

    return prompt


def _generate_narration_llm(
    client: genai.Client,
    prompt: str,
) -> List[str]:
    """Call Gemini to generate narration sentences."""
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown code fence if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        sentences = json.loads(text)
        if isinstance(sentences, list) and all(isinstance(s, str) for s in sentences):
            return sentences
    except Exception as e:
        logger.warning(f"LLM narration generation failed: {e}")

    return []


async def _synthesize_sentence(
    text: str,
    output_path: Path,
    voice: str,
    rate: str,
    pitch: str,
) -> float:
    """Synthesize a single sentence with edge-tts. Returns duration in seconds."""
    import edge_tts

    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(str(output_path))
            duration = _get_audio_duration(output_path)
            return duration
        except Exception as e:
            logger.warning(f"TTS attempt {attempt+1} failed for '{text[:20]}...': {e}")
            if attempt < 2:
                import asyncio
                await asyncio.sleep(1)

    # All retries failed - estimate duration from text length
    logger.warning(f"TTS failed after 3 attempts, creating silent placeholder")
    _create_silent_audio(output_path, len(text) / 3.5)
    return len(text) / 3.5  # ~3.5 chars/sec for Chinese


def _create_silent_audio(output_path: Path, duration_sec: float) -> None:
    """Create a silent audio file as TTS fallback."""
    import subprocess
    try:
        subprocess.run(
            [
                config.FFMPEG_BIN, "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
                "-t", str(duration_sec),
                "-acodec", "libmp3lame", "-q:a", "9",
                str(output_path),
            ],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio file duration in seconds using ffprobe."""
    import subprocess
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
        return 5.0


def run_script(
    workspace_dir: str,
    template_id: str = None,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Generate narration script, synthesize VO audio, and create subtitle data.

    Reads storyboard.json + analysis.json + template.
    Writes script.json, vo/*.mp3, subtitles.json.
    """
    workspace = Path(workspace_dir)
    template_id = template_id or config.DEFAULT_TEMPLATE

    # Load storyboard
    with open(workspace / "storyboard.json", "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    # Load analysis (for captions)
    with open(workspace / "analysis.json", "r", encoding="utf-8") as f:
        assets = json.load(f)

    # Load template
    template_path = config.TEMPLATES_DIR / f"{template_id}.json"
    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    # Create VO output dir
    vo_dir = workspace / "vo"
    vo_dir.mkdir(exist_ok=True)

    # Get style settings
    style = template.get("style", {})
    voice = style.get("vo_voice", config.TTS_VOICE)
    rate = style.get("vo_rate", config.TTS_RATE)
    pitch = style.get("vo_pitch", config.TTS_PITCH)

    # Setup LLM client
    client = None
    if config.GEMINI_API_KEY:
        client = genai.Client(api_key=config.GEMINI_API_KEY)

    segments = storyboard["segments"]
    script_data = []
    subtitle_entries = []
    current_time = 0.0

    for seg_idx, segment in enumerate(segments):
        if progress_callback:
            pct = int(seg_idx / len(segments) * 80)
            progress_callback(pct, f"Scripting act: {segment['act_name_zh']}")

        # Generate narration text
        sentences = []
        if client:
            prompt = _build_narration_prompt(segment, template, assets)
            sentences = _generate_narration_llm(client, prompt)

        if not sentences:
            # Fallback: generic narration
            act_name = segment.get("act_name_zh", "")
            sentences = [f"{act_name}，是我们故事的一部分。"]

        # Synthesize VO for each sentence
        seg_vo_files = []
        seg_subtitles = []
        # VO starts after a small gap from segment start
        vo_start = current_time + 1.5

        for s_idx, sentence in enumerate(sentences):
            mp3_path = vo_dir / f"seg_{seg_idx:02d}_{s_idx:02d}.mp3"
            loop = asyncio.new_event_loop()
            try:
                duration = loop.run_until_complete(
                    _synthesize_sentence(sentence, mp3_path, voice, rate, pitch)
                )
            finally:
                loop.close()
            seg_vo_files.append({
                "file": str(mp3_path),
                "start_sec": round(vo_start, 2),
                "end_sec": round(vo_start + duration, 2),
                "duration_sec": round(duration, 2),
            })
            seg_subtitles.append({
                "text": sentence,
                "start_sec": round(vo_start, 2),
                "end_sec": round(vo_start + duration, 2),
            })
            vo_start += duration + 0.5  # gap between sentences

        # Update segment narration
        segment["narration_zh"] = " ".join(sentences)

        script_entry = {
            "segment_id": segment["id"],
            "act_name_zh": segment["act_name_zh"],
            "sentences": sentences,
            "vo_files": seg_vo_files,
        }
        script_data.append(script_entry)
        subtitle_entries.extend(seg_subtitles)

        current_time += segment["duration_sec"]

    # Write script.json
    script_out = {
        "version": "1.0",
        "segments": script_data,
    }
    with open(workspace / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_out, f, ensure_ascii=False, indent=2)

    # Write subtitles.json
    subtitle_style = {
        "font": style.get("subtitle_font", "Noto Sans SC"),
        "size": style.get("subtitle_size", 42),
        "color": style.get("subtitle_color", "#FFFFFF"),
        "shadow": style.get("subtitle_shadow", True),
    }
    subtitles_out = {
        "version": "1.0",
        "style": subtitle_style,
        "entries": subtitle_entries,
    }
    with open(workspace / "subtitles.json", "w", encoding="utf-8") as f:
        json.dump(subtitles_out, f, ensure_ascii=False, indent=2)

    # Update storyboard with narration
    with open(workspace / "storyboard.json", "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(100, f"Script done: {len(subtitle_entries)} subtitle lines")

    logger.info(
        f"Script generated: {len(script_data)} segments, "
        f"{len(subtitle_entries)} subtitle entries"
    )
    return script_out
