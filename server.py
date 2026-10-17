"""FastAPI REST API Server for Local Video Forge v2.6.
Implements the REST API endpoints defined in Section 11 of the SPEC.
Hosts the web dashboard and handles asynchronous job execution.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import Config
from pipeline import PipelineOrchestrator
from storage.db import get_connection

logger = logging.getLogger("server")

app = FastAPI(
    title="Local Video Forge v2.6 API",
    description="One YouTube URL -> Multi Clips -> Multi Scripts -> Multi Voices (GPT-5.6 Sol Only)",
    version="2.6.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = PipelineOrchestrator()
pipeline_jobs: dict[str, dict[str, Any]] = {}

class SourceCreateReq(BaseModel):
    youtube_url: str
    rights_status: str = "VERIFIED"
    max_spend_usd: float = 10.0

class RunPipelineReq(BaseModel):
    youtube_url: str
    source_id: str | None = None
    local_srt_path: str | None = None
    local_clip_paths: list[str] | None = None
    rights_status: str = "VERIFIED"
    max_spend_usd: float = 10.0

@app.get("/api/v1/stats")
def get_stats():
    with get_connection() as conn:
        sources_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        batches_count = conn.execute("SELECT COUNT(*) FROM source_batches").fetchone()[0]
        clips_count = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        ready_count = conn.execute("SELECT COUNT(*) FROM clips WHERE status = 'PUBLISH_READY'").fetchone()[0]
    return {
        "engine": "Local Video Forge v2.6",
        "model": Config.OPENAI_MODEL,
        "base_url": Config.OPENAI_BASE_URL,
        "voice_id": Config.ELEVENLABS_VOICE_ID,
        "sources_count": sources_count,
        "batches_count": batches_count,
        "clips_count": clips_count,
        "publish_ready_count": ready_count,
    }

@app.post("/api/v1/sources")
def create_source(req: SourceCreateReq):
    source_id = f"src_{int(req.youtube_url.__hash__() % 1000000):06d}"
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sources (id, youtube_url, rights_status) VALUES (?, ?, ?)",
            (source_id, req.youtube_url, req.rights_status)
        )
    return {"source_id": source_id, "youtube_url": req.youtube_url, "rights_status": req.rights_status}

@app.post("/api/v1/sources/{source_id}/scout")
def run_source_scout(source_id: str, youtube_url: str, local_srt_path: str | None = None):
    try:
        plan = orchestrator.scout.execute_scout(source_id, youtube_url, local_srt_path)
        return plan.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/opus-batches/{batch_id}/clips")
def get_batch_clips(batch_id: str):
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT c.*, p.title_en as pub_title, p.description_en, p.hashtags_json
               FROM clips c
               LEFT JOIN clip_publications p ON c.id = p.clip_id
               WHERE c.batch_id = ?
               ORDER BY c.index_no ASC""",
            (batch_id,)
        ).fetchall()
    clips = []
    for r in rows:
        clips.append(dict(r))
    return {"batch_id": batch_id, "clips": clips}

@app.get("/api/v1/clips/{clip_uid}")
def get_clip_details(clip_uid: str):
    with get_connection() as conn:
        clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_uid,)).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        insp = conn.execute("SELECT * FROM clip_inspections WHERE clip_id = ?", (clip_uid,)).fetchone()
        script = conn.execute("SELECT * FROM clip_scripts WHERE clip_id = ?", (clip_uid,)).fetchone()
        tts = conn.execute("SELECT * FROM clip_tts WHERE clip_id = ?", (clip_uid,)).fetchone()
        render = conn.execute("SELECT * FROM clip_renders WHERE clip_id = ?", (clip_uid,)).fetchone()
        pub = conn.execute("SELECT * FROM clip_publications WHERE clip_id = ?", (clip_uid,)).fetchone()

    return {
        "clip": dict(clip),
        "inspection": dict(insp) if insp else None,
        "script": dict(script) if script else None,
        "tts": dict(tts) if tts else None,
        "render": dict(render) if render else None,
        "publication": dict(pub) if pub else None,
    }

@app.post("/api/v1/pipeline/run")
def start_pipeline(req: RunPipelineReq, bg_tasks: BackgroundTasks):
    job_id = f"job_{int(time.time() * 1000)}"
    pipeline_jobs[job_id] = {
        "status": "RUNNING",
        "stage": "INITIALIZING",
        "progress": 0.0,
        "message": "Starting pipeline...",
        "result": None,
        "error": None,
    }

    def _task():
        try:
            def on_progress(stage: str, pct: float, msg: str):
                pipeline_jobs[job_id]["stage"] = stage
                pipeline_jobs[job_id]["progress"] = round(pct, 2)
                pipeline_jobs[job_id]["message"] = msg

            manifest = orchestrator.run_full_pipeline(
                youtube_url=req.youtube_url,
                source_id=req.source_id,
                local_srt_path=req.local_srt_path,
                local_clip_paths=req.local_clip_paths,
                rights_status=req.rights_status,
                max_spend_usd=req.max_spend_usd,
                progress_callback=on_progress,
            )
            pipeline_jobs[job_id]["status"] = "COMPLETED"
            pipeline_jobs[job_id]["progress"] = 1.0
            pipeline_jobs[job_id]["result"] = manifest.model_dump()
        except Exception as e:
            logger.exception("Pipeline job failed")
            pipeline_jobs[job_id]["status"] = "FAILED"
            pipeline_jobs[job_id]["error"] = str(e)

    bg_tasks.add_task(_task)
    return {"job_id": job_id, "status": "SCHEDULED"}

@app.get("/api/v1/pipeline/jobs/{job_id}")
def get_pipeline_job(job_id: str):
    if job_id not in pipeline_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return pipeline_jobs[job_id]

# Static Dashboard & media files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount data directory so frontend can stream preview / final videos
app.mount("/media", StaticFiles(directory=str(Config.DATA_DIR)), name="media")

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_html = STATIC_DIR / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return HTMLResponse("<h1>Local Video Forge v2.6</h1><p>Dashboard is loading...</p>")
