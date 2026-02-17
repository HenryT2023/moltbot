"""
Step C: Storyboard Generation.
Assigns photos to acts based on template keywords and scene analysis,
calculates durations, and generates Ken Burns motion parameters.
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import config

logger = logging.getLogger("p2m.storyboard")


def _load_template(template_id: str) -> Dict[str, Any]:
    """Load a template JSON file."""
    template_path = config.TEMPLATES_DIR / f"{template_id}.json"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _match_asset_to_act(
    asset: Dict[str, Any], acts: List[Dict[str, Any]]
) -> str:
    """Match an asset to the best-fitting act based on tags vs act keywords."""
    analysis = asset.get("analysis") or {}
    tags = set(t.lower() for t in analysis.get("tags", []))
    scene_type = (analysis.get("scene_type") or "").lower()

    best_act_id = acts[-1]["id"]  # default to last act
    best_score = 0

    for act in acts:
        keywords = set(k.lower() for k in act.get("keywords", []))
        # Score = number of matching tags + scene_type partial match
        score = len(tags & keywords)
        # Bonus if scene_type contains any keyword
        for kw in keywords:
            if kw in scene_type:
                score += 2
        if score > best_score:
            best_score = score
            best_act_id = act["id"]

    return best_act_id


def _assign_photos_to_acts(
    assets: List[Dict[str, Any]],
    acts: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Assign photos to acts. Ensure every act gets at least one photo."""
    act_assets: Dict[str, List[Dict[str, Any]]] = {a["id"]: [] for a in acts}

    # First pass: match by tags/scene
    for asset in assets:
        act_id = _match_asset_to_act(asset, acts)
        act_assets[act_id].append(asset)

    # Second pass: redistribute if any act is empty
    # Take from the largest act
    for act in acts:
        if not act_assets[act["id"]]:
            # Find the act with most photos
            donor_id = max(act_assets, key=lambda k: len(act_assets[k]))
            if len(act_assets[donor_id]) > 1:
                moved = act_assets[donor_id].pop()
                act_assets[act["id"]].append(moved)

    # If still empty (very few photos), use time-based fallback
    total = sum(len(v) for v in act_assets.values())
    empty_acts = [a["id"] for a in acts if not act_assets[a["id"]]]
    if empty_acts and total > 0:
        # Flatten and distribute uniformly
        all_assets_sorted = sorted(
            assets,
            key=lambda a: (a.get("exif") or {}).get("datetime") or "9999",
        )
        act_assets = {a["id"]: [] for a in acts}
        n = len(all_assets_sorted)
        for i, asset in enumerate(all_assets_sorted):
            act_idx = min(i * len(acts) // n, len(acts) - 1)
            act_assets[acts[act_idx]["id"]].append(asset)

    return act_assets


def _sort_within_act(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort assets within an act by EXIF datetime."""
    return sorted(
        assets,
        key=lambda a: (a.get("exif") or {}).get("datetime") or "9999",
    )


def _generate_ken_burns(
    asset_id: str, duration: float, index: int
) -> Dict[str, Any]:
    """Generate Ken Burns motion parameters for a single photo."""
    intensity = config.KEN_BURNS_INTENSITY
    patterns = [
        # zoom in (center focus)
        {"type": "ken_burns", "start_rect": [0, 0, 100, 100],
         "end_rect": [int(intensity*100), int(intensity*100),
                      int(100-intensity*100), int(100-intensity*100)]},
        # zoom out
        {"type": "ken_burns",
         "start_rect": [int(intensity*100), int(intensity*100),
                        int(100-intensity*100), int(100-intensity*100)],
         "end_rect": [0, 0, 100, 100]},
        # pan left to right
        {"type": "ken_burns", "start_rect": [0, 5, 85, 95],
         "end_rect": [15, 5, 100, 95]},
        # pan right to left
        {"type": "ken_burns", "start_rect": [15, 5, 100, 95],
         "end_rect": [0, 5, 85, 95]},
    ]
    pattern = patterns[index % len(patterns)]
    return {
        "asset_id": asset_id,
        "type": pattern["type"],
        "start_rect": pattern["start_rect"],
        "end_rect": pattern["end_rect"],
        "duration": duration,
    }


def run_storyboard(
    workspace_dir: str,
    template_id: str = None,
    target_duration_sec: float = None,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Generate storyboard from analysis.json + template.

    Returns storyboard dict. Also writes workspace_dir/storyboard.json.
    """
    workspace = Path(workspace_dir)
    template_id = template_id or config.DEFAULT_TEMPLATE
    target_duration = target_duration_sec or config.DEFAULT_DURATION_SEC

    # Load analysis
    analysis_path = workspace / "analysis.json"
    with open(analysis_path, "r", encoding="utf-8") as f:
        assets = json.load(f)

    # Load template
    template = _load_template(template_id)
    acts = template["acts"]

    if progress_callback:
        progress_callback(10, "Assigning photos to acts")

    # Assign photos to acts
    act_assets = _assign_photos_to_acts(assets, acts)

    # Build segments
    segments = []
    seg_idx = 0

    for act in acts:
        act_id = act["id"]
        act_photos = _sort_within_act(act_assets[act_id])
        if not act_photos:
            continue

        # Calculate act duration based on weight
        act_duration = target_duration * act["weight"]
        # Account for transitions
        transition_dur = template.get("style", {}).get(
            "transition_duration", config.TRANSITION_DURATION_SEC
        )

        # Calculate per-photo duration
        n_photos = len(act_photos)
        raw_per_photo = act_duration / n_photos
        per_photo = max(
            config.MIN_PHOTO_DISPLAY_SEC,
            min(config.MAX_PHOTO_DISPLAY_SEC, raw_per_photo),
        )

        # Adjust act duration to fit
        actual_act_duration = per_photo * n_photos

        # Build motions
        motions = []
        for i, photo in enumerate(act_photos):
            motion = _generate_ken_burns(photo["id"], per_photo, seg_idx + i)
            motions.append(motion)

        segment = {
            "id": f"seg_{seg_idx:02d}",
            "act_id": act_id,
            "act_name_zh": act.get("name_zh", act.get("name", "")),
            "asset_ids": [p["id"] for p in act_photos],
            "duration_sec": round(actual_act_duration, 2),
            "narration_zh": "",  # filled by scripter
            "motion": motions,
            "transition_in": act.get("transition", "crossfade"),
            "transition_out": "crossfade",
            "transition_duration": transition_dur,
        }
        segments.append(segment)
        seg_idx += 1

    if progress_callback:
        progress_callback(90, f"Generated {len(segments)} segments")

    # Build storyboard
    storyboard = {
        "version": "1.0",
        "template_id": template_id,
        "target_duration_sec": target_duration,
        "actual_duration_sec": round(sum(s["duration_sec"] for s in segments), 2),
        "total_photos": len(assets),
        "segments": segments,
    }

    # Write storyboard.json
    storyboard_path = workspace / "storyboard.json"
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(100, "Storyboard complete")

    logger.info(
        f"Storyboard: {len(segments)} segments, "
        f"{storyboard['actual_duration_sec']}s total"
    )
    return storyboard
