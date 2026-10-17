"""Batch runner for 5 German craftsman workshop videos from Opusclip/1.
YouTube source: https://www.youtube.com/watch?v=vL5MrypSvpE
Runs full pipeline: Sol Scout -> Barrier -> 5-clip Fan-Out -> ElevenLabs Voice -> FFmpeg Render -> Publication Pack.
"""
import sys
import logging
from pathlib import Path

from pipeline import PipelineOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def main():
    youtube_url = "https://www.youtube.com/watch?v=vL5MrypSvpE"
    subtitles = "/Volumes/KINGSTON/Reup Từ Đức/sub video/[German] Vom Schmiedefeuer zur Klinge Die Kunst des Messerschmieds  Was bleibt 16  Handwerk  BR [DownSub.com].srt"
    
    clips = [
        "/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1/Aus der Not geschmiedet_ Dieses Messer hat eine lebendige Klinge.mp4",
        "/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1/Handwerk, Freundschaft und Messer, die Generationen überdauern.mp4",
        "/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1/Huberts Messer schleift nur Tommy – mit Gefühl und Präzision.mp4",
        "/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1/Messer härten_ Ein falscher Moment – und die Klinge bricht.mp4",
        "/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1/Wie Schmieden ihm hilft, mit Depressionen zu leben.mp4",
    ]

    print(f"Starting Local Video Forge v2.6 for {len(clips)} clips from Opusclip/1...")
    orchestrator = PipelineOrchestrator()
    manifest = orchestrator.run_full_pipeline(
        youtube_url=youtube_url,
        source_id="source_knife_batch_5",
        local_srt_path=subtitles,
        local_clip_paths=clips,
    )

    print("\n" + "=" * 60)
    print("ALL 5 CLIPS PROCESSED SUCCESSFULLY!")
    print(f"Discovered: {manifest.counts.discovered}")
    print(f"Accepted:   {manifest.counts.accepted}")
    print(f"Scripted:   {manifest.counts.script_pass}")
    print(f"Voiced:     {manifest.counts.voice_pass}")
    print(f"Rendered:   {manifest.counts.final_pass}")
    print("=" * 60)

if __name__ == "__main__":
    main()
