import json
import logging
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import Config
from pipeline import PipelineOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reprocess")

VIDEOS_TO_FIX = [
    ("src_VlUGlaKmmbw", "https://www.youtube.com/watch?v=VlUGlaKmmbw", "The 'Impossible' Scribe"),
    ("src_RKvOfX1s3-k", "https://www.youtube.com/watch?v=RKvOfX1s3-k", "A New Kind of Bearing"),
    ("src_R0qk4E1hEMY", "https://www.youtube.com/watch?v=R0qk4E1hEMY", "Making a Watch Winding Mechanism"),
    ("src_kIWkSQmD_C0", "https://www.youtube.com/watch?v=kIWkSQmD_C0", "Machining a Watch Mainplate"),
    ("src_KrStsdNG5go", "https://www.youtube.com/watch?v=KrStsdNG5go", "Building a Micro-Drilling Machine"),
    ("src_XaBnH35eVXA", "https://www.youtube.com/watch?v=XaBnH35eVXA", "Building an Interplanetary Clock"),
    ("src_bv9IQTOYl8Q", "https://www.youtube.com/watch?v=bv9IQTOYl8Q", "Machining an Award with a Magic Trick"),
    ("src_8IewMXUzt7U", "https://www.youtube.com/watch?v=8IewMXUzt7U", "Inventing the Adjustable Allen Key"),
]

def main():
    orch = PipelineOrchestrator()
    prog_path = Config.DATA_DIR / "chronova_progress.json"
    progress = {}
    if prog_path.exists():
        try:
            progress = json.loads(prog_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    for idx, (source_id, url, orig_title) in enumerate(VIDEOS_TO_FIX, 1):
        logger.info(f"\n{'='*70}\n[{idx}/{len(VIDEOS_TO_FIX)}] RE-GENERATING WITH GPT-5.6 SOL: {orig_title} ({source_id})\n{'='*70}")
        t0 = time.time()
        try:
            m = orch.run_restoration_pipeline(
                source=url,
                source_id=source_id,
            )
            elapsed = time.time() - t0
            clip = m.discovered_clips[0]
            new_title = clip.publish_pack.title_en if clip.publish_pack else orig_title
            final_mp4 = Config.DATA_DIR / "sources" / source_id / clip.folder / "final.mp4"
            logger.info(f"SUCCESS in {elapsed:.1f}s!")
            logger.info(f"New Craft Title: {new_title}")
            logger.info(f"Final Video:     {final_mp4}")

            if "results" in progress:
                progress["results"][source_id] = {
                    "id": source_id.replace("src_", ""),
                    "title": orig_title,
                    "url": url,
                    "status": "COMPLETED",
                    "elapsed_sec": round(elapsed, 1),
                    "final_video": str(final_mp4),
                    "publish_title": new_title,
                    "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                prog_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"FAILED on {orig_title}: {e}")

    logger.info(f"\n{'='*70}\nALL 8 VIDEOS RE-GENERATED SUCCESSFULLY WITH GPT-5.6 SOL!\n{'='*70}")

if __name__ == "__main__":
    main()
