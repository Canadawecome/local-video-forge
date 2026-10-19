"""Batch Channel Runner for Local Video Forge Restoration Pipeline.
Processes an entire queue of YouTube restoration videos sequentially with error resilience,
progress persistence, and skip-existing support.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from config import Config
from pipeline import PipelineOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Config.DATA_DIR / "batch_channel.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("batch_runner")


def load_queue(queue_path: Path) -> list[dict[str, Any]]:
    if not queue_path.exists():
        raise FileNotFoundError(f"Queue file not found: {queue_path}")
    return json.loads(queue_path.read_text(encoding="utf-8"))


def save_progress(progress_path: Path, data: dict[str, Any]) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = progress_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(progress_path)


def run_batch(
    queue_path: str | Path = "data/ntrprojects_queue.json",
    runtime: str = "standard",
    max_videos: int | None = None,
    skip_completed: bool = True,
) -> dict[str, Any]:
    q_path = Path(queue_path)
    if not q_path.is_absolute():
        q_path = Config.DATA_DIR / queue_path if not q_path.exists() else q_path

    queue = load_queue(q_path)
    logger.info(f"Loaded {len(queue)} videos from queue: {q_path}")

    orchestrator = PipelineOrchestrator()
    progress_path = Config.DATA_DIR / "ntrprojects_progress.json"

    progress: dict[str, Any] = {
        "channel_url": "https://www.youtube.com/@NTRprojects",
        "total_queued": len(queue),
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "current_video": None,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": {},
    }

    if progress_path.exists():
        try:
            existing = json.loads(progress_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and "results" in existing:
                progress["results"] = existing["results"]
        except Exception as e:
            logger.warning(f"Could not load previous progress: {e}")

    processed_count = 0
    total = len(queue) if max_videos is None else min(len(queue), max_videos)

    for idx, item in enumerate(queue[:total], 1):
        vid_id = item["id"]
        source_id = f"src_{vid_id}"
        title = item.get("title", vid_id)
        url = item.get("url", f"https://www.youtube.com/watch?v={vid_id}")
        dur_min = item.get("duration_min", 0.0)

        final_mp4 = Config.DATA_DIR / "sources" / source_id / "output" / "clip_001_craft" / "final.mp4"
        reframe_plan_file = Config.DATA_DIR / "sources" / source_id / "restoration_cut" / "smart_reframe" / "layouts" / "reframe_plan.v1.json"

        # Check if already completed WITH Smart Reframe ASMR v1.0
        is_reframe_completed = final_mp4.exists() and final_mp4.stat().st_size > 5_000_000 and reframe_plan_file.exists()
        if skip_completed and is_reframe_completed:
            logger.info(f"[{idx}/{total}] SKIP ALREADY COMPLETED (Smart Reframe v1.0): {title} ({source_id}) -> {final_mp4}")
            progress["results"][source_id] = {
                "id": vid_id,
                "title": title,
                "url": url,
                "duration_min": dur_min,
                "status": "COMPLETED",
                "final_video": str(final_mp4),
                "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            progress["skipped"] += 1
            progress["completed"] += 1
            save_progress(progress_path, progress)
            continue

        logger.info("\n" + "="*70)
        logger.info(f"[{idx}/{total}] STARTING RESTORATION: {title} ({dur_min} min)")
        logger.info(f"URL: {url} | Source ID: {source_id}")
        logger.info("="*70)

        progress["current_video"] = {"index": idx, "total": total, "id": vid_id, "title": title, "url": url}
        progress["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_progress(progress_path, progress)

        t0 = time.time()
        try:
            manifest = orchestrator.run_restoration_pipeline(
                source=url,
                source_id=source_id,
                runtime_preference=runtime,
            )
            elapsed = time.time() - t0
            final_clip = manifest.discovered_clips[0]
            logger.info(f"[{idx}/{total}] SUCCESS in {elapsed:.1f}s: {title}")
            logger.info(f"Deliverable: {Config.DATA_DIR / 'sources' / source_id / final_clip.folder / 'final.mp4'}")

            progress["results"][source_id] = {
                "id": vid_id,
                "title": title,
                "url": url,
                "duration_min": dur_min,
                "status": "COMPLETED",
                "elapsed_sec": round(elapsed, 1),
                "final_video": str(Config.DATA_DIR / "sources" / source_id / final_clip.folder / "final.mp4"),
                "publish_title": final_clip.publish_pack.title_en if final_clip.publish_pack else title,
                "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            progress["completed"] += 1
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[{idx}/{total}] FAILED after {elapsed:.1f}s: {title} -> {e}")
            logger.error(traceback.format_exc())
            progress["results"][source_id] = {
                "id": vid_id,
                "title": title,
                "url": url,
                "duration_min": dur_min,
                "status": "FAILED",
                "error": str(e),
                "elapsed_sec": round(elapsed, 1),
                "failed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            progress["failed"] += 1

        progress["current_video"] = None
        progress["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_progress(progress_path, progress)
        processed_count += 1

    logger.info("\n" + "="*70)
    logger.info(f"BATCH CHANNEL RUN COMPLETE: Total: {total} | Completed: {progress['completed']} | Failed: {progress['failed']}")
    logger.info("="*70)
    return progress


def main():
    parser = argparse.ArgumentParser(description="Batch Runner for Restoration Video Processing")
    parser.add_argument("--queue", default="data/ntrprojects_queue.json", help="Path to JSON queue file")
    parser.add_argument("--runtime", default="standard", choices=["compact", "standard", "extended"], help="Target runtime preference")
    parser.add_argument("--max-videos", type=int, default=None, help="Max videos to process in this run")
    parser.add_argument("--skip-completed", action="store_true", default=True, help="Skip videos that already have final.mp4")
    args = parser.parse_args()

    run_batch(
        queue_path=args.queue,
        runtime=args.runtime,
        max_videos=args.max_videos,
        skip_completed=args.skip_completed,
    )


if __name__ == "__main__":
    main()
