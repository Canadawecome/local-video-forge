import json
import subprocess
import sys
from pathlib import Path

def main():
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist",
        "--dump-single-json",
        "https://www.youtube.com/@chronovaengineering/videos"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    entries = data.get("entries", [])
    
    queue = []
    print(f"Total videos discovered: {len(entries)}")
    for i, e in enumerate(entries, 1):
        vid_id = e.get("id")
        title = e.get("title", "")
        dur = e.get("duration", 0)
        url = f"https://www.youtube.com/watch?v={vid_id}"
        queue.append({
            "id": vid_id,
            "title": title,
            "url": url,
            "duration_sec": dur,
            "duration_min": round(dur / 60.0, 1) if dur else 0.0,
        })
        print(f"{i}. [{vid_id}] ({dur}s) {title}")
        
    out_file = Path("data/chronova_queue.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved queue to {out_file}")

if __name__ == "__main__":
    main()
