"""Export Downloader for Local Video Forge.
Organizes all completed 74s clean-audio shorts into a single, user-friendly download directory,
and generates a 1-click HTML download portal hosted at http://localhost:8090/downloads/.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from config import Config

import os

logger = logging.getLogger("export_downloader")

DESKTOP_DIR = Path(os.environ.get("USERPROFILE", "C:/Users/ADMIN")) / "Desktop" / "Chronova_Shorts"
DOWNLOAD_DIR = Config.DATA_DIR.parent / "downloads" / "chronova_shorts"
HTTP_DOWNLOAD_DIR = Config.DATA_DIR / "sources" / "downloads" / "chronova_shorts"
HTML_PORTAL_PATH = Config.DATA_DIR / "sources" / "downloads" / "index.html"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\s-]', '', name).strip()
    name = re.sub(r'[\s]+', '_', name)
    return name[:60]


def export_all_completed() -> list[dict[str, Any]]:
    """Scans all sources and exports approved 74s final videos to the download directories."""
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    HTTP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PORTAL_PATH.parent.mkdir(parents=True, exist_ok=True)

    queue_file = Config.DATA_DIR / "chronova_queue.json"
    queue: list[dict[str, Any]] = []
    if queue_file.exists():
        try:
            queue = json.loads(queue_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    exported: list[dict[str, Any]] = []

    for idx, item in enumerate(queue, 1):
        vid_id = item["id"]
        source_id = f"src_{vid_id}"
        clip_folder = Config.DATA_DIR / "sources" / source_id / "output" / "clip_001_craft"
        final_mp4 = clip_folder / "final.mp4"
        demucs_flag = clip_folder / "audio" / "demucs_done.flag"
        script_file = clip_folder / "script_en.md"

        if not final_mp4.exists() or final_mp4.stat().st_size < 5_000_000:
            continue

        # Prefer Sol craftsman title from script_en.md if available
        title = item.get("title", vid_id)
        if script_file.exists():
            try:
                first_line = script_file.read_text(encoding="utf-8").splitlines()[0]
                if first_line.startswith("#"):
                    title = first_line.replace("#", "").strip()
            except Exception:
                pass

        safe_name = f"{idx:02d}_{sanitize_filename(title)}.mp4"
        dest_local = DOWNLOAD_DIR / safe_name
        dest_http = HTTP_DOWNLOAD_DIR / safe_name
        dest_desktop = DESKTOP_DIR / safe_name

        # Copy if destination doesn't exist or is smaller/older
        if not dest_local.exists() or dest_local.stat().st_mtime < final_mp4.stat().st_mtime:
            shutil.copy2(final_mp4, dest_local)
            logger.info(f"Exported to local download: {dest_local.name}")

        if not dest_http.exists() or dest_http.stat().st_mtime < final_mp4.stat().st_mtime:
            shutil.copy2(final_mp4, dest_http)
            logger.info(f"Exported to HTTP portal: {dest_http.name}")

        if not dest_desktop.exists() or dest_desktop.stat().st_mtime < final_mp4.stat().st_mtime:
            shutil.copy2(final_mp4, dest_desktop)
            logger.info(f"Exported to Desktop: {dest_desktop.name}")

        exported.append({
            "index": idx,
            "id": vid_id,
            "title": title,
            "filename": safe_name,
            "file_size_mb": round(final_mp4.stat().st_size / (1024 * 1024), 2),
            "http_url": f"http://localhost:8090/downloads/chronova_shorts/{safe_name}",
            "local_path": str(dest_local),
            "demucs_clean": demucs_flag.exists(),
        })

    _generate_html_portal(exported, len(queue))
    logger.info(f"Exported {len(exported)}/{len(queue)} completed videos.")
    return exported


def _generate_html_portal(videos: list[dict[str, Any]], total_queue: int) -> None:
    """Generates a responsive, modern HTML portal for browser download and playback."""
    cards_html = []
    for v in videos:
        badge = '<span style="background:#10b981;color:white;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600;">Clean ASMR + Ducking</span>' if v['demucs_clean'] else '<span style="background:#f59e0b;color:white;padding:2px 8px;border-radius:12px;font-size:12px;">Standard</span>'
        cards_html.append(f"""
        <div class="video-card">
            <div class="card-header">
                <span class="video-index">#{v['index']:02d}</span>
                <span class="video-size">{v['file_size_mb']} MB</span>
            </div>
            <div class="video-container">
                <video controls preload="metadata" poster="">
                    <source src="/downloads/chronova_shorts/{v['filename']}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
            </div>
            <div class="card-body">
                <h3 title="{v['title']}">{v['title']}</h3>
                <div style="margin: 8px 0;">{badge}</div>
                <div class="actions">
                    <a href="/downloads/chronova_shorts/{v['filename']}" download="{v['filename']}" class="btn-download">
                        &#x2B07; Tải Video (.mp4)
                    </a>
                </div>
            </div>
        </div>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chronova Engineering - 41 Clean ASMR Shorts Portal</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --accent-hover: #0284c7;
            --success: #10b981;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            margin: 0;
            padding: 24px;
        }}
        .header {{
            max-width: 1200px;
            margin: 0 auto 32px auto;
            border-bottom: 1px solid #334155;
            padding-bottom: 20px;
        }}
        h1 {{
            font-size: 28px;
            margin: 0 0 8px 0;
            color: var(--accent);
        }}
        .subtitle {{
            color: var(--text-secondary);
            font-size: 15px;
            margin: 0;
        }}
        .stats-bar {{
            display: flex;
            gap: 16px;
            margin-top: 16px;
        }}
        .stat-badge {{
            background: #334155;
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
        }}
        .stat-badge strong {{
            color: var(--accent);
        }}
        .grid {{
            max-width: 1200px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 24px;
        }}
        .video-card {{
            background: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            display: flex;
            flex-direction: column;
            border: 1px solid #334155;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .video-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
            border-color: #475569;
        }}
        .card-header {{
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #172033;
        }}
        .video-index {{
            font-weight: 700;
            color: var(--accent);
            font-size: 16px;
        }}
        .video-size {{
            font-size: 13px;
            color: var(--text-secondary);
        }}
        .video-container {{
            width: 100%;
            background: #000;
            aspect-ratio: 9/16;
            max-height: 480px;
        }}
        video {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        .card-body {{
            padding: 16px;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        h3 {{
            font-size: 15px;
            font-weight: 600;
            margin: 0 0 8px 0;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        .actions {{
            margin-top: 12px;
        }}
        .btn-download {{
            display: block;
            text-align: center;
            background: var(--accent);
            color: #0f172a;
            text-decoration: none;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.15s;
        }}
        .btn-download:hover {{
            background: var(--accent-hover);
            color: #fff;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Chronova Engineering - Portal Tải Video Shorts</h1>
        <p class="subtitle">Định dạng chuẩn: 1080x1920 (9:16) Portrait | Thời lượng: 74.00s | Sạch 100% voice người nói | Sidechain Ducking -12dB | Thuyết minh thợ thủ công Sol 5.6 & Adam</p>
        <div class="stats-bar">
            <div class="stat-badge">Đã hoàn thành: <strong>{len(videos)}/{total_queue}</strong></div>
            <div class="stat-badge">Chất lượng: <strong>Full HD 1080x1920</strong></div>
            <div class="stat-badge">Thư mục tải về máy: <code>local-video-forge/downloads/chronova_shorts/</code></div>
        </div>
    </div>

    <div class="grid">
        {"".join(cards_html)}
    </div>
</body>
</html>
"""
    HTML_PORTAL_PATH.write_text(html_content, encoding="utf-8")
