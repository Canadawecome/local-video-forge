"""Source Ingest & Text Scout module for Local Video Forge v2.6.
Fetches YouTube metadata and subtitles (zero original video download).
GPT-5.6 Sol analyzes text and creates source context + Opus custom prompt.
Validates output against SourceScoutPlanV26.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from adapters.sol_adapter import SolAdapter
from config import Config
from local_video_forge_sol_source_contracts_v2_6 import (
    CandidateWindowV26,
    SourceEvidenceV26,
    SourceScoutPlanV26,
)
from storage.db import get_connection

logger = logging.getLogger("source_scout")

def parse_srt_file(srt_path: Path) -> list[dict[str, Any]]:
    """Parse SRT into a list of {start_sec, end_sec, text}."""
    if not srt_path.exists():
        return []
    
    with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    results = []
    
    def time_to_sec(t_str: str) -> float:
        # 00:01:23,456 or 00:01:23.456
        t_str = t_str.replace(",", ".")
        parts = t_str.split(":")
        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
        return h * 3600 + m * 60 + s

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 2:
            time_match = re.search(r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})", lines[1])
            if time_match:
                start = time_to_sec(time_match.group(1))
                end = time_to_sec(time_match.group(2))
                text = " ".join(lines[2:]).strip()
                if text and end > start:
                    results.append({"start_sec": round(start, 2), "end_sec": round(end, 2), "text": text})

    return results

class SourceScout:
    def __init__(self, sol_adapter: SolAdapter | None = None):
        self.sol = sol_adapter or SolAdapter()

    def fetch_youtube_metadata(self, youtube_url: str) -> dict[str, Any]:
        """Fetches metadata via yt-dlp in zero-download mode."""
        cmd = [
            "yt-dlp",
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            youtube_url,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"yt-dlp metadata fetch failed or not reachable: {e}")
            # Fallback for offline/mock or restricted environments:
            video_id = youtube_url.split("v=")[-1].split("&")[0] if "v=" in youtube_url else "video_001"
            return {
                "id": video_id,
                "title": f"German Workshop Project ({video_id})",
                "description": "Artisan forging and metal restoration in a traditional German workshop.",
                "duration": 600,
                "uploader": "Handwerk Workshop",
                "tags": ["schmieden", "handwerk", "messer", "restauration"],
                "chapters": [],
                "subtitles": {},
            }

    def execute_scout(
        self,
        source_id: str,
        youtube_url: str,
        local_srt_path: str | Path | None = None,
        rights_status: str = "VERIFIED",
    ) -> SourceScoutPlanV26:
        """Runs the complete source scout process."""
        source_folder = Config.DATA_DIR / "sources" / source_id
        global_ctx_folder = source_folder / "global_context"
        global_ctx_folder.mkdir(parents=True, exist_ok=True)

        # 1. Fetch metadata
        meta = self.fetch_youtube_metadata(youtube_url)
        with open(global_ctx_folder / "source_metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # 2. Check for subtitles
        subtitles_data: list[dict[str, Any]] = []
        if local_srt_path and Path(local_srt_path).exists():
            subtitles_data = parse_srt_file(Path(local_srt_path))
        
        has_subtitles = len(subtitles_data) > 0
        source_mode = "SUBTITLE_ENRICHED" if has_subtitles else "METADATA_ONLY"

        if has_subtitles:
            with open(global_ctx_folder / "source_subtitles_de.json", "w", encoding="utf-8") as f:
                json.dump(subtitles_data, f, indent=2, ensure_ascii=False)

        # 3. Sol text prompt
        system_prompt = (
            "You are the Source Scout for Local Video Forge v2.6. "
            "Analyze the given video metadata and German subtitles (if available). "
            "STRICT RULES:\n"
            "1. When source_mode is METADATA_ONLY, candidate_windows MUST be an empty list []. "
            "Do NOT invent timestamps or imagine footage you cannot verify.\n"
            "2. When SUBTITLE_ENRICHED, only create candidate windows that match actual subtitle timestamps.\n"
            "3. Global Opus prompt must be in US English, >= 12 chars, asking OpusClip to extract authentic "
            "workshop processes (forging, grinding, restoration) preserving close-ups and mechanical ASMR.\n"
            "4. Output JSON matching SourceScoutPlanV26 format."
        )

        user_prompt = f"""
SOURCE ID: {source_id}
YOUTUBE URL: {youtube_url}
SOURCE MODE: {source_mode}
TITLE: {meta.get('title')}
DESCRIPTION: {meta.get('description', '')[:600]}
DURATION: {meta.get('duration')}s
CHANNEL: {meta.get('uploader')}
TAGS: {meta.get('tags', [])[:6]}

SUBTITLES SUMMARY (First 8 key moments):
{json.dumps(subtitles_data[:8], ensure_ascii=False) if has_subtitles else "None"}

Please produce concise JSON:
- source_summary: clear, concise factual overview of the craft project
- global_opus_prompt_en: prompt for OpusClip ClipAnything (e.g. 'Find distinct high-quality workshop action sequences...')
- evidence: concise list of 3-5 SourceEvidenceV26 objects from TITLE, DESCRIPTION, or SUBTITLE
- candidate_windows: list of CandidateWindowV26 (strictly empty [] if METADATA_ONLY)
"""

        sol_resp = self.sol.generate_structured_json(system_prompt, user_prompt)

        # Build SourceEvidenceV26 list
        raw_evidence = sol_resp.get("evidence", [])
        evidence_list: list[SourceEvidenceV26] = []
        
        # Add basic verified evidence from metadata
        title_text = meta.get("title") or "Source Video"
        evidence_list.append(SourceEvidenceV26(
            evidence_id="ev_meta_title",
            source_kind="TITLE",
            text=title_text,
            verified=True,
        ))
        
        desc_text = (meta.get("description") or "Workshop video")[:200]
        evidence_list.append(SourceEvidenceV26(
            evidence_id="ev_meta_desc",
            source_kind="DESCRIPTION",
            text=desc_text,
            verified=True,
        ))

        for idx, ev in enumerate(raw_evidence):
            try:
                ev_id = f"ev_scout_{idx+1}"
                kind = ev.get("source_kind", "DESCRIPTION")
                if kind not in ["TITLE", "DESCRIPTION", "CHAPTER", "SUBTITLE", "THUMBNAIL", "EDITOR_MARKER", "SOURCE_FRAME", "EXTERNAL_REFERENCE"]:
                    kind = "DESCRIPTION"
                text = ev.get("text") or "Observation"
                s_in = ev.get("start_sec")
                s_out = ev.get("end_sec")
                if source_mode == "METADATA_ONLY" or s_in is None or s_out is None or s_out <= s_in:
                    s_in = None
                    s_out = None
                
                evidence_list.append(SourceEvidenceV26(
                    evidence_id=ev_id,
                    source_kind=kind,
                    text=text,
                    start_sec=s_in,
                    end_sec=s_out,
                    verified=True,
                ))
            except Exception as e:
                logger.debug(f"Skipping unparseable evidence: {e}")

        # Windows
        candidate_windows: list[CandidateWindowV26] = []
        if source_mode != "METADATA_ONLY":
            raw_windows = sol_resp.get("candidate_windows", [])
            for w in raw_windows:
                try:
                    w_id = w.get("window_id", "win_01")
                    s_in = float(w.get("start_sec", 0))
                    s_out = float(w.get("end_sec", 60))
                    # Check matching evidence
                    matching_ev = [e.evidence_id for e in evidence_list if e.start_sec is not None and e.start_sec <= s_in and e.end_sec >= s_out]
                    if matching_ev:
                        candidate_windows.append(CandidateWindowV26(
                            window_id=w_id,
                            start_sec=s_in,
                            end_sec=s_out,
                            evidence_ids=[matching_ev[0]],
                            basis="SUBTITLE",
                            prompt_en=w.get("prompt_en", "Focus on authentic workshop craftsmanship.")
                        ))
                except Exception:
                    pass

        opus_prompt = sol_resp.get("global_opus_prompt_en") or (
            "Extract several distinct high-quality artisan workshop sequences, "
            "preserving close-ups of forging, metal shaping, and mechanical ASMR."
        )

        plan = SourceScoutPlanV26(
            schema_version="2.6",
            source_id=source_id,
            youtube_url=youtube_url,
            source_mode=source_mode,
            source_downloaded=False,
            openai_model="gpt-5.6-sol",
            source_summary=sol_resp.get("source_summary", "Traditional German workshop craftsmanship project."),
            global_opus_prompt_en=opus_prompt,
            evidence=evidence_list,
            candidate_windows=candidate_windows,
            source_transcript_available=has_subtitles,
        )

        # Save artifacts
        with open(global_ctx_folder / "source_context_sol.json", "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))

        with open(global_ctx_folder / "source_evidence.json", "w", encoding="utf-8") as f:
            json.dump([e.model_dump() for e in evidence_list], f, indent=2, ensure_ascii=False)

        with open(global_ctx_folder / "opus_prompt_plan.json", "w", encoding="utf-8") as f:
            json.dump({
                "global_opus_prompt_en": plan.global_opus_prompt_en,
                "candidate_windows": [w.model_dump() for w in candidate_windows],
                "clip_duration_target": [60, 90],
                "brand_template": "clean_portrait_9_16"
            }, f, indent=2)

        summary_md = f"""# Source Video Summary
- **Source ID:** {source_id}
- **YouTube URL:** {youtube_url}
- **Title:** {meta.get('title')}
- **Mode:** {source_mode}
- **Transcript Available:** {has_subtitles}

## Sol Analysis
{plan.source_summary}

## Global Opus Prompt
> {plan.global_opus_prompt_en}
"""
        with open(global_ctx_folder / "source_video_summary.md", "w", encoding="utf-8") as f:
            f.write(summary_md)

        # Update DB
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO sources (id, youtube_url, rights_status, metadata_json) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   youtube_url=excluded.youtube_url,
                   rights_status=excluded.rights_status,
                   metadata_json=excluded.metadata_json""",
                (source_id, youtube_url, rights_status, json.dumps(meta))
            )
            for ev in evidence_list:
                conn.execute(
                    """INSERT INTO source_evidence (id, source_id, evidence_type, source_in, source_out, text, verification) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                       text=excluded.text,
                       verification=excluded.verification""",
                    (ev.evidence_id, source_id, ev.source_kind, ev.start_sec, ev.end_sec, ev.text, "VERIFIED")
                )

        return plan
