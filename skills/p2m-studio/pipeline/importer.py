"""
Step A: Import & Normalize photos.
Reads photos from a directory, extracts EXIF, fixes orientation,
normalizes resolution, deduplicates, and outputs assets.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageOps
from PIL.ExifTags import TAGS, GPSTAGS

from .. import config

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

logger = logging.getLogger("p2m.importer")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
TARGET_LONG_EDGE = 1920


def _extract_exif(img: Image.Image) -> Dict[str, Any]:
    """Extract EXIF data from a PIL Image."""
    exif_data: Dict[str, Any] = {
        "datetime": None,
        "gps": None,
        "camera": None,
        "orientation": 1,
    }
    try:
        raw_exif = img.getexif()
        if not raw_exif:
            return exif_data
    except Exception:
        return exif_data

    # Basic EXIF fields
    for tag_id, value in raw_exif.items():
        tag_name = TAGS.get(tag_id, str(tag_id))
        if tag_name == "DateTime" or tag_name == "DateTimeOriginal":
            try:
                exif_data["datetime"] = datetime.strptime(
                    str(value), "%Y:%m:%d %H:%M:%S"
                ).isoformat()
            except (ValueError, TypeError):
                pass
        elif tag_name == "Orientation":
            exif_data["orientation"] = int(value)
        elif tag_name == "Model":
            exif_data["camera"] = str(value).strip()

    # DateTimeOriginal from IFD
    try:
        ifd = raw_exif.get_ifd(0x8769)  # ExifIFD
        if ifd:
            dt_original = ifd.get(36867)  # DateTimeOriginal tag
            if dt_original and not exif_data["datetime"]:
                exif_data["datetime"] = datetime.strptime(
                    str(dt_original), "%Y:%m:%d %H:%M:%S"
                ).isoformat()
    except Exception:
        pass

    # GPS
    try:
        gps_ifd = raw_exif.get_ifd(0x8825)  # GPSInfo
        if gps_ifd:
            lat = _convert_gps_coord(
                gps_ifd.get(2), gps_ifd.get(1)  # GPSLatitude  # GPSLatitudeRef
            )
            lon = _convert_gps_coord(
                gps_ifd.get(4), gps_ifd.get(3)  # GPSLongitude  # GPSLongitudeRef
            )
            if lat is not None and lon is not None:
                exif_data["gps"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
    except Exception:
        pass

    return exif_data


def _convert_gps_coord(
    coord: Any, ref: Optional[str]
) -> Optional[float]:
    """Convert GPS coordinate from EXIF format to decimal degrees."""
    if coord is None or ref is None:
        return None
    try:
        degrees = float(coord[0])
        minutes = float(coord[1])
        seconds = float(coord[2])
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except (TypeError, IndexError, ValueError):
        return None


def _normalize_image(img: Image.Image) -> Image.Image:
    """Fix orientation and scale to target long edge."""
    # Fix orientation based on EXIF
    img = ImageOps.exif_transpose(img)

    # Convert to RGB if needed (RGBA, P, etc.)
    if img.mode not in ("RGB",):
        img = img.convert("RGB")

    # Scale long edge to TARGET_LONG_EDGE
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > TARGET_LONG_EDGE:
        scale = TARGET_LONG_EDGE / long_edge
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def _compute_phash(img: Image.Image) -> Optional[Any]:
    """Compute perceptual hash for deduplication. Returns imagehash object."""
    if not IMAGEHASH_AVAILABLE:
        return None
    try:
        return imagehash.phash(img)
    except Exception:
        return None


def _file_mtime_iso(path: Path) -> str:
    """Get file modification time as ISO string."""
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts).isoformat()


def run_import(
    input_dir: str,
    workspace_dir: str,
    progress_callback: Any = None,
) -> List[Dict[str, Any]]:
    """
    Import and normalize photos from input_dir into workspace_dir/assets/.

    Args:
        input_dir: Directory containing source photos.
        workspace_dir: Pipeline workspace directory.
        progress_callback: Optional callable(pct: int, msg: str).

    Returns:
        List of Asset dicts. Also writes workspace_dir/assets.json.
    """
    input_path = Path(input_dir)
    workspace = Path(workspace_dir)
    assets_dir = workspace / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Collect photo files
    photo_files: List[Path] = []
    for f in sorted(input_path.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            photo_files.append(f)

    if not photo_files:
        raise ValueError(f"No supported photos found in {input_dir}")

    logger.info(f"Found {len(photo_files)} photos in {input_dir}")

    assets: List[Dict[str, Any]] = []
    seen_hashes: List = []  # stores imagehash objects for hamming distance comparison
    skipped_dupes = 0

    for idx, photo_path in enumerate(photo_files):
        pct = int((idx / len(photo_files)) * 100)
        if progress_callback:
            progress_callback(pct, f"Importing {photo_path.name}")

        try:
            img = Image.open(photo_path)
        except Exception as e:
            logger.warning(f"Cannot open {photo_path.name}: {e}, skipping")
            continue

        # Extract EXIF before any transforms
        exif = _extract_exif(img)

        # Fallback datetime from file mtime
        if not exif["datetime"]:
            exif["datetime"] = _file_mtime_iso(photo_path)

        # Dedup via perceptual hash (hamming distance threshold)
        phash = _compute_phash(img)
        if phash is not None and IMAGEHASH_AVAILABLE:
            is_dup = False
            for existing_hash in seen_hashes:
                if (phash - existing_hash) <= config.DEDUP_HASH_THRESHOLD:
                    is_dup = True
                    break
            if is_dup:
                logger.info(f"Duplicate detected: {photo_path.name}, skipping")
                skipped_dupes += 1
                continue
            seen_hashes.append(phash)

        # Normalize
        img = _normalize_image(img)

        # Save normalized
        asset_id = f"asset_{idx:04d}"
        out_filename = f"{asset_id}.jpg"
        out_path = assets_dir / out_filename
        img.save(out_path, "JPEG", quality=92)

        w, h = img.size
        asset = {
            "id": asset_id,
            "original_path": str(photo_path),
            "normalized_path": str(out_path),
            "width": w,
            "height": h,
            "exif": exif,
            "analysis": None,  # filled by analyzer step
        }
        assets.append(asset)

        img.close()

    if progress_callback:
        progress_callback(100, f"Imported {len(assets)} photos ({skipped_dupes} dupes skipped)")

    logger.info(f"Imported {len(assets)} photos, skipped {skipped_dupes} duplicates")

    # Write assets.json
    assets_json_path = workspace / "assets.json"
    with open(assets_json_path, "w", encoding="utf-8") as f:
        json.dump(assets, f, ensure_ascii=False, indent=2)

    return assets
