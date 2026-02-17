"""
Step B: Content Understanding via Gemini Vision API.
Sends each image to Gemini for captioning and tag extraction,
then clusters images by scene type for act assignment.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai

import config

logger = logging.getLogger("p2m.analyzer")

# Scene type keywords mapped to act keywords for clustering
SCENE_CATEGORIES = [
    "couple", "portrait", "wedding", "ceremony", "family", "child", "baby",
    "travel", "landmark", "outdoor", "food", "celebration", "daily", "selfie",
    "group", "nature", "city", "beach", "mountain", "pet", "sport", "work",
]

CAPTION_PROMPT = """Look at this photo and provide:
1. A one-sentence Chinese caption describing the scene (natural, like telling a friend)
2. A list of 3-8 English tags from this set: couple, portrait, wedding, ceremony, family, child, baby, travel, landmark, outdoor, food, celebration, daily, selfie, group, nature, city, beach, mountain, pet, sport, work
3. A scene_type: one of [couple_dating, wedding_ceremony, family_life, travel_outdoor, daily_life, celebration, portrait]

Respond in this exact JSON format (no markdown):
{"caption_zh": "...", "tags": ["...", "..."], "scene_type": "..."}"""


def _analyze_single_image_sync(
    client: genai.Client,
    model: str,
    image_path: str,
) -> Dict[str, Any]:
    """Analyze a single image with Gemini Vision API (synchronous)."""
    try:
        img_bytes = Path(image_path).read_bytes()

        response = client.models.generate_content(
            model=model,
            contents=[
                genai.types.Content(
                    parts=[
                        genai.types.Part(
                            inline_data=genai.types.Blob(
                                mime_type="image/jpeg",
                                data=img_bytes,
                            )
                        ),
                        genai.types.Part(text=CAPTION_PROMPT),
                    ]
                )
            ],
        )

        text = response.text.strip()
        # Strip markdown code fence if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        result = json.loads(text)
        return {
            "caption_zh": result.get("caption_zh", ""),
            "tags": result.get("tags", []),
            "scene_type": result.get("scene_type", "daily_life"),
        }
    except Exception as e:
        logger.warning(f"Gemini Vision failed for {image_path}: {e}")
        return {
            "caption_zh": "",
            "tags": [],
            "scene_type": "daily_life",
        }


def _cluster_by_scene_type(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Assign cluster_id based on scene_type grouping."""
    scene_to_cluster: Dict[str, int] = {}
    next_cluster = 0

    for asset in assets:
        analysis = asset.get("analysis") or {}
        scene = analysis.get("scene_type", "daily_life")
        if scene not in scene_to_cluster:
            scene_to_cluster[scene] = next_cluster
            next_cluster += 1
        analysis["cluster_id"] = scene_to_cluster[scene]
        asset["analysis"] = analysis

    return assets


def _fallback_analysis(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fallback: no captioning, just sort by EXIF time and assign uniform clusters."""
    # Sort by datetime
    def sort_key(a: Dict[str, Any]) -> str:
        exif = a.get("exif") or {}
        return exif.get("datetime") or "9999"

    assets.sort(key=sort_key)

    # Uniform distribution across 6 clusters (one per act)
    n = len(assets)
    for i, asset in enumerate(assets):
        cluster_id = min(i * 6 // n, 5)
        asset["analysis"] = {
            "caption_zh": "",
            "tags": [],
            "scene_type": "daily_life",
            "cluster_id": cluster_id,
        }

    return assets


def run_analyze(
    workspace_dir: str,
    progress_callback: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """
    Analyze all assets using Gemini Vision API.

    Reads workspace_dir/assets.json, updates with analysis, writes analysis.json.
    """
    workspace = Path(workspace_dir)
    assets_path = workspace / "assets.json"

    with open(assets_path, "r", encoding="utf-8") as f:
        assets = json.load(f)

    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, using fallback analysis")
        assets = _fallback_analysis(assets)
        _save_analysis(workspace, assets)
        return assets

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    model = config.GEMINI_VISION_MODEL

    # Use ThreadPoolExecutor for concurrent synchronous API calls
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        with ThreadPoolExecutor(max_workers=config.GEMINI_VISION_CONCURRENCY) as executor:
            future_to_idx = {}
            for idx, asset in enumerate(assets):
                future = executor.submit(
                    _analyze_single_image_sync, client, model, asset["normalized_path"]
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                assets[idx]["analysis"] = future.result()
                if progress_callback:
                    done = sum(1 for a in assets if a.get("analysis"))
                    pct = int(done / len(assets) * 100)
                    progress_callback(pct, f"Analyzed {done}/{len(assets)}")
    except Exception as e:
        logger.error(f"Gemini Vision batch analysis failed: {e}, using fallback")
        assets = _fallback_analysis(assets)
        _save_analysis(workspace, assets)
        return assets

    # Check if we got enough valid captions
    valid_count = sum(1 for a in assets if a.get("analysis", {}).get("caption_zh"))
    if valid_count < len(assets) * 0.3:
        logger.warning(
            f"Only {valid_count}/{len(assets)} images got captions, using fallback"
        )
        assets = _fallback_analysis(assets)
    else:
        assets = _cluster_by_scene_type(assets)

    _save_analysis(workspace, assets)
    return assets


def _save_analysis(workspace: Path, assets: List[Dict[str, Any]]) -> None:
    """Save analysis results."""
    analysis_path = workspace / "analysis.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(assets, f, ensure_ascii=False, indent=2)
    logger.info(f"Analysis saved to {analysis_path}")
