import json
import subprocess
from pathlib import Path

def main():
    prog_file = Path("data/chronova_progress.json")
    if not prog_file.exists():
        print("No progress file found.")
        return
        
    data = json.loads(prog_file.read_text(encoding="utf-8"))
    results = data.get("results", {})
    completed = [(k, v) for k, v in results.items() if v.get("status") == "COMPLETED"]
    
    print(f"Total Completed Videos: {len(completed)}\n")
    for idx, (k, v) in enumerate(completed, 1):
        vid_id = v.get("id")
        title = v.get("title")
        pub_title = v.get("publish_title", "")
        final_video_path = Path(v.get("final_video", ""))
        
        dur_str = "N/A"
        size_mb = 0.0
        if final_video_path.exists():
            size_mb = round(final_video_path.stat().st_size / (1024 * 1024), 1)
            try:
                res = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(final_video_path)],
                    capture_output=True, text=True
                )
                dur_float = float(json.loads(res.stdout)["format"]["duration"])
                dur_str = f"{dur_float:.2f}s"
            except Exception:
                pass
                
        preview_url = f"http://localhost:8090/{k}/output/clip_001_craft/final.mp4"
        print(f"--- Video {idx} ---")
        print(f"ID:          {vid_id}")
        print(f"Original:    {title}")
        if pub_title and pub_title != title:
            print(f"Craft Title: {pub_title}")
        print(f"Duration:    {dur_str} (Target: 74.0s)")
        print(f"File Size:   {size_mb} MB")
        print(f"Preview URL: {preview_url}")
        print(f"File Path:   {final_video_path.resolve()}\n")

if __name__ == "__main__":
    main()
