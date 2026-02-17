"""
Step: AI Video Generation via fal.ai (MiniMax Hailuo models).
Converts each photo into a 6-second video clip using Image-to-Video generation.

fal.ai REST API workflow:
1. Upload image → get public URL
2. Submit to queue → get request_id
3. Poll status until COMPLETED → get result with video URL
4. Download video
"""
from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from .. import config

logger = logging.getLogger("p2m.video_gen")

# fal.ai model endpoints
FAL_MODELS = {
    "hailuo-02": "fal-ai/minimax/hailuo-02/standard/image-to-video",
    "video-01": "fal-ai/minimax/video-01/image-to-video",
}

FAL_SYNC_URL = "https://fal.run"

# Motion prompt template — Wong Kar-wai cinematic style with subtle micro-expressions
MOTION_PROMPT_TEMPLATE = (
    "Wong Kar-wai cinematic style, shallow depth of field, warm color grading, "
    "dreamy soft focus. {facial}. {environment}. {camera}. "
    "Do not distort or morph facial features. Keep face structure intact."
)

# Default motion suggestions based on scene type — WKW aesthetic
DEFAULT_MOTIONS: Dict[str, Dict[str, str]] = {
    "couple_dating": {
        "facial": "Subtle blink, gentle warm smile",
        "environment": "Warm golden light spills across the scene, soft bokeh",
        "camera": "Slow dolly in, shallow depth of field",
    },
    "wedding_ceremony": {
        "facial": "Subtle blink, faint tender smile",
        "environment": "Dreamy warm haze, golden light flare",
        "camera": "Slow tracking shot, soft focus background",
    },
    "family_life": {
        "facial": "Subtle blink, warm content smile",
        "environment": "Warm afternoon light, gentle lens flare",
        "camera": "Slow pull back, shallow depth of field",
    },
    "travel_outdoor": {
        "facial": "Subtle blink, relaxed gaze",
        "environment": "Wind in foliage, warm diffused sunlight",
        "camera": "Slow lateral tracking, dreamy bokeh",
    },
    "daily_life": {
        "facial": "Subtle blink, natural expression",
        "environment": "Warm ambient light drifts softly",
        "camera": "Slow dolly in, soft dreamy focus",
    },
    "celebration": {
        "facial": "Subtle blink, joyful expression",
        "environment": "Warm festive glow, light streaks",
        "camera": "Slow crane up, golden color grading",
    },
    "portrait": {
        "facial": "Subtle blink, faint smile",
        "environment": "Soft neon-tinged bokeh shifts",
        "camera": "Very slow push in, shallow focus",
    },
}


class FalVideoGen:
    """fal.ai MiniMax Hailuo Image-to-Video API client (REST, no SDK needed)."""

    def __init__(self, api_key: str | None = None, model: str = "hailuo-02"):
        self.api_key = api_key or config.FAL_KEY
        if not self.api_key:
            raise ValueError("FAL_KEY not set")
        self.model_id = FAL_MODELS.get(model, model)
        self.headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _image_to_data_url(self, image_path: str) -> str:
        """Convert local image to base64 data URL."""
        img_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        suffix = Path(image_path).suffix.lower()
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "image/jpeg")
        return f"data:{mime};base64,{b64}"

    def generate_single(self, image_path: str, prompt: str, output_path: str) -> str:
        """
        Generate video from a single image via fal.ai synchronous endpoint.
        Blocks until video is ready, then downloads. Returns local video path.
        """
        image_data_url = self._image_to_data_url(image_path)

        payload = {
            "prompt": prompt,
            "image_url": image_data_url,
            "prompt_optimizer": False,
            "duration": "6",
        }

        url = f"{FAL_SYNC_URL}/{self.model_id}"
        logger.info(f"Generating video for {Path(image_path).name} ...")

        resp = self.session.post(url, json=payload, timeout=600)
        resp.raise_for_status()
        result = resp.json()

        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError(f"No video URL in fal.ai result: {result}")

        logger.info(f"Video ready: {video_url}")

        # Download
        video_resp = requests.get(video_url, timeout=120)
        video_resp.raise_for_status()

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(video_resp.content)

        size_mb = len(video_resp.content) / (1024 * 1024)
        logger.info(f"Downloaded {out.name} ({size_mb:.1f}MB)")
        return str(out)


def build_motion_prompt(analysis: Dict[str, Any]) -> str:
    """
    Build a motion prompt from Gemini's analysis of the photo.
    Uses scene_type to pick appropriate default motion.
    """
    scene_type = analysis.get("scene_type", "daily_life")
    defaults = DEFAULT_MOTIONS.get(scene_type, DEFAULT_MOTIONS["daily_life"])

    return MOTION_PROMPT_TEMPLATE.format(
        facial=defaults["facial"],
        environment=defaults["environment"],
        camera=defaults["camera"],
    )


def run_video_gen(
    workspace_dir: str,
    progress_callback: Optional[Callable] = None,
    max_concurrent: int = 3,
) -> List[Dict[str, Any]]:
    """
    Generate AI video clips for all assets in the workspace.

    Reads workspace_dir/analysis.json, generates video for each photo,
    saves clips to workspace_dir/clips/, writes clips.json manifest.
    """
    workspace = Path(workspace_dir)
    analysis_path = workspace / "analysis.json"

    with open(analysis_path, "r", encoding="utf-8") as f:
        assets = json.load(f)

    if not config.FAL_KEY:
        logger.error("FAL_KEY not set, cannot generate AI videos")
        raise ValueError("FAL_KEY not set")

    client = FalVideoGen()
    clips_dir = workspace / "clips"
    clips_dir.mkdir(exist_ok=True)

    total = len(assets)
    completed = 0

    def _generate_one(idx: int, asset: Dict[str, Any]) -> Dict[str, Any]:
        """Generate video for a single asset."""
        analysis = asset.get("analysis", {})
        prompt = build_motion_prompt(analysis)
        image_path = asset["normalized_path"]
        output_path = str(clips_dir / f"clip_{idx:04d}.mp4")

        logger.info(f"[{idx+1}/{total}] Generating video for {Path(image_path).name}")
        logger.debug(f"  Prompt: {prompt}")

        video_path = client.generate_single(
            image_path=image_path,
            prompt=prompt,
            output_path=output_path,
        )

        return {
            "index": idx,
            "image_path": image_path,
            "clip_path": video_path,
            "prompt": prompt,
            "scene_type": analysis.get("scene_type", "daily_life"),
        }

    clips = [None] * total

    # Concurrent generation with controlled parallelism
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_idx = {}
        for idx, asset in enumerate(assets):
            future = executor.submit(_generate_one, idx, asset)
            future_to_idx[future] = idx

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                clip_info = future.result()
                clips[idx] = clip_info
                completed += 1
                if progress_callback:
                    pct = int(completed / total * 100)
                    progress_callback(pct, f"Generated {completed}/{total} clips")
                logger.info(f"[{completed}/{total}] Clip {idx} done")
            except Exception as e:
                logger.error(f"Failed to generate clip {idx}: {e}")
                clips[idx] = {
                    "index": idx,
                    "image_path": assets[idx]["normalized_path"],
                    "clip_path": None,
                    "error": str(e),
                }
                completed += 1
                if progress_callback:
                    pct = int(completed / total * 100)
                    progress_callback(pct, f"Generated {completed}/{total} clips (1 error)")

    # Filter out failed clips
    valid_clips = [c for c in clips if c and c.get("clip_path")]

    # Save manifest
    manifest_path = workspace / "clips.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(valid_clips, f, ensure_ascii=False, indent=2)

    logger.info(f"Video generation complete: {len(valid_clips)}/{total} clips")
    return valid_clips
