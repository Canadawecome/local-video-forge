"""SQLite Database storage for Local Video Forge v2.6.
Implements the exact schemas specified in Section 3.3 of the SPEC.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Config

DB_FILE = Config.DATA_DIR / "local_video_forge.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db() -> None:
    Config.ensure_dirs()
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            youtube_url TEXT NOT NULL,
            rights_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS source_evidence (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            evidence_type TEXT NOT NULL,
            source_in REAL,
            source_out REAL,
            text TEXT NOT NULL,
            verification TEXT DEFAULT 'UNVERIFIED'
        );

        CREATE TABLE IF NOT EXISTS source_batches (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            config_hash TEXT,
            barrier_state TEXT NOT NULL DEFAULT 'CREATED',
            clip_selection_policy TEXT NOT NULL DEFAULT 'ALL_USABLE',
            max_spend_usd REAL DEFAULT 10.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS opus_projects (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES source_batches(id) ON DELETE CASCADE,
            provider_project_id TEXT,
            window_id TEXT,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            request_hash TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            last_error TEXT
        );

        CREATE TABLE IF NOT EXISTS clips (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES source_batches(id) ON DELETE CASCADE,
            opus_project_id TEXT,
            opus_clip_id TEXT NOT NULL,
            index_no INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'DISCOVERED',
            source_asset_path TEXT,
            source_asset_sha256 TEXT,
            duration_sec REAL DEFAULT 0,
            opus_metadata_json TEXT,
            output_folder TEXT,
            title_en TEXT,
            narration_mode TEXT DEFAULT 'ORIGINAL_COMMENTARY',
            revision INTEGER DEFAULT 1,
            UNIQUE(batch_id, opus_clip_id)
        );

        CREATE TABLE IF NOT EXISTS clip_inspections (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            inspector_json TEXT,
            transcript_path TEXT,
            fact_refs_json TEXT
        );

        CREATE TABLE IF NOT EXISTS clip_scripts (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1,
            script_text TEXT,
            tts_text TEXT,
            story_angle TEXT,
            evidence_json TEXT,
            approved_at TIMESTAMP,
            script_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS clip_tts (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            script_revision INTEGER NOT NULL,
            voice_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            settings_hash TEXT,
            audio_path TEXT,
            alignment_path TEXT,
            provider_request_id TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING'
        );

        CREATE TABLE IF NOT EXISTS clip_renders (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            script_revision INTEGER NOT NULL,
            ffmpeg_plan_hash TEXT,
            preview_path TEXT,
            final_path TEXT,
            media_probe_json TEXT,
            qc_status TEXT DEFAULT 'PENDING'
        );

        CREATE TABLE IF NOT EXISTS clip_publications (
            id TEXT PRIMARY KEY,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1,
            title_en TEXT,
            description_en TEXT,
            hashtags_json TEXT,
            source_credit TEXT,
            policy_status TEXT DEFAULT 'PENDING'
        );

        CREATE TABLE IF NOT EXISTS clip_job_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            stage TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            input_hash TEXT,
            status TEXT NOT NULL,
            error_code TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS provider_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL REFERENCES source_batches(id) ON DELETE CASCADE,
            clip_id_nullable TEXT,
            stage TEXT NOT NULL,
            estimated_usd REAL DEFAULT 0,
            actual_usd REAL DEFAULT 0,
            unit TEXT
        );
        """)

init_db()
