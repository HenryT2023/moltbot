"""
P2M Studio configuration.
Reads from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from pathlib import Path


# -- Project paths --
PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
MUSIC_DIR = PROJECT_ROOT / "music"

# -- AI Video (fal.ai → MiniMax Hailuo) --
FAL_KEY = os.environ.get("FAL_KEY", "")
FAL_MODEL = os.environ.get("P2M_FAL_MODEL", "hailuo-02")
FAL_CONCURRENCY = int(os.environ.get("P2M_FAL_CONCURRENCY", "3"))
FAL_POLL_INTERVAL = int(os.environ.get("P2M_FAL_POLL_INTERVAL", "8"))
FAL_TIMEOUT = int(os.environ.get("P2M_FAL_TIMEOUT", "300"))

# -- LLM --
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("P2M_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VISION_MODEL = os.environ.get("P2M_GEMINI_VISION_MODEL", "gemini-2.5-flash")

# -- TTS (edge-tts) --
TTS_VOICE = os.environ.get("P2M_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
TTS_RATE = os.environ.get("P2M_TTS_RATE", "-5%")
TTS_PITCH = os.environ.get("P2M_TTS_PITCH", "+0Hz")

# -- FFmpeg --
def _find_bin(name: str) -> str:
    """Find binary in common paths."""
    env_val = os.environ.get(f"P2M_{name.upper()}_BIN")
    if env_val:
        return env_val
    for p in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]:
        full = os.path.join(p, name)
        if os.path.isfile(full):
            return full
    return name  # fallback to PATH lookup

FFMPEG_BIN = _find_bin("ffmpeg")
FFPROBE_BIN = _find_bin("ffprobe")

# -- Render defaults --
RENDER_FPS = 30
RENDER_PREVIEW_WIDTH = 1280
RENDER_PREVIEW_HEIGHT = 720
RENDER_FINAL_WIDTH = 1920
RENDER_FINAL_HEIGHT = 1080
RENDER_PREVIEW_CRF = 28
RENDER_FINAL_CRF = 20

# -- Pipeline defaults --
DEFAULT_TEMPLATE = "marriage_5min_restrained"
DEFAULT_DURATION_SEC = 300
MIN_PHOTO_DISPLAY_SEC = 3.0
MAX_PHOTO_DISPLAY_SEC = 8.0
KEN_BURNS_INTENSITY = 0.15
TRANSITION_DURATION_SEC = 0.8

# -- Analyzer --
GEMINI_VISION_CONCURRENCY = 5
GEMINI_VISION_TIMEOUT = 30

# -- Dedup --
DEDUP_HASH_THRESHOLD = 6  # hamming distance; 0=exact match, higher=more tolerant

# -- Music --
MUSIC_DUCK_VOLUME = 0.1
MUSIC_DUCK_FADE_MS = 500
MUSIC_DEFAULT_VOLUME = 0.3
