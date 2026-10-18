"""Command-line interface for Local Video Forge v2.6.
Allows running individual pipeline stages or complete end-to-end processing.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

from config import Config
from pipeline import PipelineOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cli")

def main():
    parser = argparse.ArgumentParser(description="Local Video Forge v2.6 — GPT-5.6 Sol Only")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run (end-to-end)
    run_parser = subparsers.add_parser("run", help="Run full pipeline for a YouTube URL or local video")
    run_parser.add_argument("url", help="YouTube source URL")
    run_parser.add_argument("--source-id", default=None, help="Custom source ID")
    run_parser.add_argument("--subtitles", default=None, help="Path to local German .srt file")
    run_parser.add_argument("--clips", nargs="*", default=None, help="Paths to local MP4 clips to import")
    run_parser.add_argument("--opus-project-id", default=None, help="Existing OpusClip project ID to download clips from")
    run_parser.add_argument("--max-spend", type=float, default=10.0, help="Max spend guard in USD")
    run_parser.add_argument("--time-range", nargs=2, type=float, default=None, metavar=("START", "END"), help="Targeted start and end time in seconds (e.g. --time-range 60 180) to only process that window and save OpusClip credits")
    run_parser.add_argument("--video-range", nargs=2, type=float, default=None, metavar=("START", "END"), help="Alias for --time-range")
    run_parser.add_argument("--opus-model", default="ClipAnything", help="OpusClip model (default: ClipAnything, optimized for craft/low-speech videos)")

    # Command: scout
    scout_parser = subparsers.add_parser("scout", help="Run source ingest & GPT-5.6 Sol text scout")
    scout_parser.add_argument("url", help="YouTube URL")
    scout_parser.add_argument("--source-id", default="src_cli", help="Source ID")
    scout_parser.add_argument("--subtitles", default=None, help="Path to German .srt file")

    # Command: restoration-cut (SPEC v4.1 Single 75-150s Director)
    cut_parser = subparsers.add_parser("restoration-cut", help="Run SPEC v4.1 Restoration Cut & Edit Director (single 75-150s cut)")
    cut_parser.add_argument("video", help="Path to local source video MP4")
    cut_parser.add_argument("--output-dir", default=None, help="Output directory for visual cut and handoff deliverables")
    cut_parser.add_argument("--source-id", default=None, help="Custom source ID")
    cut_parser.add_argument("--runtime", choices=["compact", "standard", "extended"], default="standard", help="Runtime pacing preference (compact: 75-90s, standard: 90-120s, extended: 120-150s)")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Launch FastAPI web dashboard")
    serve_parser.add_argument("--host", default=Config.HOST, help="Host to bind")
    serve_parser.add_argument("--port", type=int, default=Config.PORT, help="Port to bind")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    orchestrator = PipelineOrchestrator()

    if args.command == "run":
        logger.info(f"Starting end-to-end pipeline for: {args.url}")
        manifest = orchestrator.run_full_pipeline(
            youtube_url=args.url,
            source_id=args.source_id,
            local_srt_path=args.subtitles,
            local_clip_paths=args.clips,
            opus_project_id=args.opus_project_id,
            max_spend_usd=args.max_spend,
            time_range=args.time_range,
            video_range=args.video_range,
            opus_model=args.opus_model,
        )
        print("\n" + "="*60)
        print("PIPELINE COMPLETE!")
        print(f"Discovered Clips: {manifest.counts.discovered}")
        print(f"Accepted Clips:   {manifest.counts.accepted}")
        print(f"Scripted Clips:   {manifest.counts.script_pass}")
        print(f"Voiced Clips:     {manifest.counts.voice_pass}")
        print(f"Final Rendered:   {manifest.counts.final_pass}")
        print("="*60 + "\n")

    elif args.command == "scout":
        logger.info(f"Running source scout for: {args.url}")
        plan = orchestrator.scout.execute_scout(
            source_id=args.source_id,
            youtube_url=args.url,
            local_srt_path=args.subtitles,
        )
        print(json.dumps(plan.model_dump(), indent=2, ensure_ascii=False))

    elif args.command == "restoration-cut":
        from modules.restoration_cut_director import RestorationCutDirector
        director = RestorationCutDirector()
        src_video = Path(args.video)
        out_dir = Path(args.output_dir) if args.output_dir else Config.DATA_DIR / "sources" / (args.source_id or f"src_{int(time.time())}") / "restoration_cut"
        logger.info(f"Running SPEC v4.1 Restoration Cut Director for {src_video}...")
        res = director.execute_cut_directing(
            source_video=src_video,
            output_dir=out_dir,
            source_id=args.source_id,
            runtime_preference=args.runtime,
        )
        print("\n" + "="*60)
        print(f"RESTORATION CUT DIRECTOR v4.1 COMPLETE: Status={res.status}")
        print(f"Selected Duration: {res.runtime_decision.target_duration_ms / 1000.0:.2f}s (mode: {res.runtime_decision.mode})")
        print(f"Preserved Stages:  {', '.join(res.runtime_decision.preserved_key_stages)}")
        print(f"Edits Generated:   {len(res.edits)}")
        print(f"Deliverables in:   {out_dir}")
        print("="*60 + "\n")

    elif args.command == "serve":
        import uvicorn
        logger.info(f"Starting Web Dashboard at http://{args.host}:{args.port}")
        uvicorn.run("server:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
