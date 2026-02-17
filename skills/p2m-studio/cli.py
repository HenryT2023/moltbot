"""
P2M Studio CLI entry point.
Usage:
    python -m p2m_studio.cli generate --input ./photos --template marriage_5min_restrained
    python -m p2m_studio.cli resume --workspace ./workspace --from-step storyboard
    python -m p2m_studio.cli preview --workspace ./workspace
    python -m p2m_studio.cli templates
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from . import config
from .pipeline import importer, analyzer, storyboard, scripter, music, renderer
from .pipeline import video_gen, beat_sync, composer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("p2m.cli")

STEPS = ["import", "analyze", "storyboard", "script", "music", "render"]
STEPS_V2 = ["import", "analyze", "video_gen", "beat_sync", "compose"]


# Machine-readable protocol for moltbot integration
_moltbot_mode = False


def _proto(tag: str, value: str = "") -> None:
    """Emit a machine-readable protocol line (only in --moltbot mode)."""
    if _moltbot_mode:
        print(f"{tag}:{value}", flush=True)


def _progress(step_name: str):
    """Create a progress callback for a pipeline step."""
    def callback(pct: int, msg: str):
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[{step_name:12s}] {bar} {pct:3d}%  {msg}", end="", flush=True)
        _proto("PROGRESS", f"{pct}:{msg}")
        if pct >= 100:
            print()
    return callback


def cmd_generate(args: argparse.Namespace) -> None:
    """Run full generation pipeline."""
    global _moltbot_mode
    _moltbot_mode = getattr(args, 'moltbot', False)

    input_dir = args.input
    template_id = args.template or config.DEFAULT_TEMPLATE
    duration = args.duration or config.DEFAULT_DURATION_SEC
    output_dir = args.output or "./output"

    if not Path(input_dir).exists():
        _proto("ERROR", f"Input directory not found: {input_dir}")
        print(f"Error: Input directory not found: {input_dir}")
        sys.exit(1)

    # Create workspace
    workspace = Path(args.workspace) if args.workspace else Path(output_dir) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    print(f"P2M Studio - Generating movie")
    print(f"  Input:    {input_dir}")
    print(f"  Template: {template_id}")
    print(f"  Duration: {duration}s")
    print(f"  Output:   {output_dir}")
    print(f"  Workspace: {workspace}")
    print()

    t0 = time.time()

    # Step A: Import
    step_start = time.time()
    assets = importer.run_import(input_dir, str(workspace), _progress("Import"))
    print(f"  → {len(assets)} photos imported ({time.time()-step_start:.1f}s)")

    # Step B: Analyze
    step_start = time.time()
    assets = analyzer.run_analyze(str(workspace), _progress("Analyze"))
    print(f"  → Analysis complete ({time.time()-step_start:.1f}s)")

    # Step C: Storyboard
    step_start = time.time()
    sb = storyboard.run_storyboard(str(workspace), template_id, duration, _progress("Storyboard"))
    print(f"  → {len(sb['segments'])} segments, {sb['actual_duration_sec']}s ({time.time()-step_start:.1f}s)")

    # Step D: Script & VO
    step_start = time.time()
    script = scripter.run_script(str(workspace), template_id, _progress("Script"))
    n_subs = sum(len(s.get("sentences", [])) for s in script.get("segments", []))
    print(f"  → {n_subs} narration sentences ({time.time()-step_start:.1f}s)")

    # Step E: Music
    step_start = time.time()
    music_path = music.run_music(str(workspace), template_id, args.music, _progress("Music"))
    if music_path:
        print(f"  → Music ready ({time.time()-step_start:.1f}s)")
    else:
        print(f"  → No music (skipped)")

    # Step F: Render
    step_start = time.time()
    results = renderer.run_render(str(workspace), template_id, "both", _progress("Render"))
    print(f"  → Render complete ({time.time()-step_start:.1f}s)")

    total_time = time.time() - t0
    print()
    print(f"{'='*50}")
    if results.get("preview"):
        print(f"  Preview:   {results['preview']}")
        _proto("MEDIA", results['preview'])
    if results.get("final"):
        print(f"  Output:    {results['final']}")
        _proto("MEDIA", results['final'])
    if results.get("srt"):
        print(f"  Subtitles: {results['srt']}")
    print(f"  Workspace: {workspace}")
    print(f"  Total time: {total_time:.1f}s")
    print(f"{'='*50}")
    _proto("DONE", results.get('final', results.get('preview', '')))


def cmd_generate_v2(args: argparse.Namespace) -> None:
    """Run V2 pipeline: AI video generation + beat-synced music."""
    global _moltbot_mode
    _moltbot_mode = getattr(args, 'moltbot', False)

    input_dir = args.input
    output_dir = args.output or "./output"
    music_file = args.music

    if not Path(input_dir).exists():
        _proto("ERROR", f"Input directory not found: {input_dir}")
        print(f"Error: Input directory not found: {input_dir}")
        sys.exit(1)

    if music_file and not Path(music_file).exists():
        print(f"Error: Music file not found: {music_file}")
        sys.exit(1)

    workspace = Path(args.workspace) if args.workspace else Path(output_dir) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    print(f"P2M Studio V2 - AI Video Mode")
    print(f"  Input:     {input_dir}")
    print(f"  Music:     {music_file or '(none)'}")
    print(f"  Output:    {output_dir}")
    print(f"  Workspace: {workspace}")
    print()

    t0 = time.time()

    # Step 1: Import photos
    step_start = time.time()
    assets = importer.run_import(input_dir, str(workspace), _progress("Import"))
    print(f"  → {len(assets)} photos imported ({time.time()-step_start:.1f}s)")

    # Step 2: Analyze photos (Gemini Vision → motion prompts)
    step_start = time.time()
    assets = analyzer.run_analyze(str(workspace), _progress("Analyze"))
    print(f"  → Analysis complete ({time.time()-step_start:.1f}s)")

    # Step 3: AI Video Generation (fal.ai → MiniMax Hailuo)
    step_start = time.time()
    clips = video_gen.run_video_gen(str(workspace), _progress("VideoGen"))
    print(f"  → {len(clips)} video clips generated ({time.time()-step_start:.1f}s)")

    # Step 4: Beat Detection & Sync (only if music provided)
    if music_file:
        step_start = time.time()
        timeline = beat_sync.run_beat_sync(str(workspace), music_file, _progress("BeatSync"))
        n_beats = timeline.get("num_beats", 0)
        print(f"  → {n_beats} beats detected, clips aligned ({time.time()-step_start:.1f}s)")

    # Step 5: Compose final video
    step_start = time.time()
    title_text = getattr(args, 'title', None)
    ending_text = getattr(args, 'ending', None)
    final_path = composer.run_compose(
        str(workspace), music_file if music_file else None, "final.mp4",
        _progress("Compose"), title_text=title_text, ending_text=ending_text,
    )
    print(f"  → Composition complete ({time.time()-step_start:.1f}s)")

    total_time = time.time() - t0
    print()
    print(f"{'='*50}")
    print(f"  Output:    {final_path}")
    print(f"  Workspace: {workspace}")
    print(f"  Total time: {total_time:.1f}s")
    print(f"{'='*50}")
    _proto("MEDIA", final_path)
    _proto("DONE", final_path)


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume pipeline from a specific step."""
    workspace = args.workspace
    from_step = args.from_step
    template_id = args.template or config.DEFAULT_TEMPLATE

    if not Path(workspace).exists():
        print(f"Error: Workspace not found: {workspace}")
        sys.exit(1)

    step_idx = STEPS.index(from_step) if from_step in STEPS else 0
    print(f"Resuming from step: {from_step} (step {step_idx + 1}/{len(STEPS)})")

    if step_idx <= 2:  # storyboard
        duration = args.duration or config.DEFAULT_DURATION_SEC
        storyboard.run_storyboard(workspace, template_id, duration, _progress("Storyboard"))

    if step_idx <= 3:  # script
        scripter.run_script(workspace, template_id, _progress("Script"))

    if step_idx <= 4:  # music
        music.run_music(workspace, template_id, None, _progress("Music"))

    if step_idx <= 5:  # render
        results = renderer.run_render(workspace, template_id, "both", _progress("Render"))
        print(f"\nResults: {json.dumps(results, indent=2)}")


def cmd_preview(args: argparse.Namespace) -> None:
    """Render preview only."""
    workspace = args.workspace
    template_id = args.template or config.DEFAULT_TEMPLATE

    if not Path(workspace).exists():
        print(f"Error: Workspace not found: {workspace}")
        sys.exit(1)

    results = renderer.run_render(workspace, template_id, "preview", _progress("Preview"))
    if results.get("preview"):
        print(f"\nPreview: {results['preview']}")
    else:
        print("\nPreview render failed")


def cmd_templates(args: argparse.Namespace) -> None:
    """List available templates."""
    templates_dir = config.TEMPLATES_DIR
    if not templates_dir.exists():
        print("No templates directory found")
        return

    print("Available templates:")
    for f in sorted(templates_dir.glob("*.json")):
        with open(f, "r", encoding="utf-8") as fp:
            t = json.load(fp)
        name_zh = t.get("name_zh", t.get("name", f.stem))
        duration = t.get("target_duration_sec", "?")
        n_acts = len(t.get("acts", []))
        print(f"  {f.stem:40s} {name_zh} ({duration}s, {n_acts} acts)")


def main():
    parser = argparse.ArgumentParser(
        description="P2M Studio - Photo-to-Movie Pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # generate
    gen = subparsers.add_parser("generate", help="Generate movie from photos")
    gen.add_argument("--input", "-i", required=True, help="Input photo directory")
    gen.add_argument("--template", "-t", default=None, help="Template ID")
    gen.add_argument("--duration", "-d", type=float, default=None, help="Target duration (sec)")
    gen.add_argument("--output", "-o", default="./output", help="Output directory")
    gen.add_argument("--workspace", "-w", default=None, help="Workspace directory")
    gen.add_argument("--music", "-m", default=None, help="Custom music file path")
    gen.add_argument("--mode", choices=["ken-burns", "ai-video"], default="ai-video",
                     help="Mode: ai-video (V2, default) or ken-burns (V1)")
    gen.add_argument("--title", default=None, help="Title card text (use \\n for line breaks)")
    gen.add_argument("--ending", default=None, help="Ending card text (use \\n for line breaks)")
    gen.add_argument("--moltbot", action="store_true", help="Machine-readable output for moltbot")

    # resume
    res = subparsers.add_parser("resume", help="Resume from a step")
    res.add_argument("--workspace", "-w", required=True, help="Workspace directory")
    res.add_argument("--from-step", required=True, choices=STEPS, help="Step to resume from")
    res.add_argument("--template", "-t", default=None, help="Template ID")
    res.add_argument("--duration", "-d", type=float, default=None, help="Target duration")

    # preview
    prev = subparsers.add_parser("preview", help="Render preview only")
    prev.add_argument("--workspace", "-w", required=True, help="Workspace directory")
    prev.add_argument("--template", "-t", default=None, help="Template ID")

    # templates
    subparsers.add_parser("templates", help="List available templates")

    args = parser.parse_args()

    if args.command == "generate":
        mode = getattr(args, 'mode', 'ai-video')
        if mode == "ai-video":
            cmd_generate_v2(args)
        else:
            cmd_generate(args)
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "preview":
        cmd_preview(args)
    elif args.command == "templates":
        cmd_templates(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
