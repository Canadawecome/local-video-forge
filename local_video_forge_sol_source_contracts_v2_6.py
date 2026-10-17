"""Local Video Forge v2.6: source text scout + per-clip sampled frames for GPT-5.6 Sol.

Strict, offline contracts; no inference, network, or media download in this module.
Use with existing v2.5 batch contracts and v2.2-v2.4 timeline/audio contracts.
GPT-5.6 Sol receives text/images, NOT YouTube videos, MP4, or raw audio.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SourceEvidenceV26(StrictModel):
    evidence_id: str = Field(min_length=1)
    source_kind: Literal[
        "TITLE", "DESCRIPTION", "CHAPTER", "SUBTITLE", "THUMBNAIL",
        "EDITOR_MARKER", "SOURCE_FRAME", "EXTERNAL_REFERENCE",
    ]
    text: str = Field(min_length=1)
    start_sec: float | None = Field(default=None, ge=0)
    end_sec: float | None = Field(default=None, gt=0)
    reference_uri: str | None = None
    frame_refs: list[str] = Field(default_factory=list)
    verified: bool = False

    @model_validator(mode="after")
    def chronology_and_provenance(self):
        if (self.start_sec is None) != (self.end_sec is None):
            raise ValueError("start_sec and end_sec must be supplied together")
        if self.start_sec is not None:
            if self.end_sec <= self.start_sec:
                raise ValueError("source evidence has invalid interval")
            if self.source_kind not in {"SUBTITLE", "EDITOR_MARKER", "SOURCE_FRAME", "CHAPTER"}:
                raise ValueError("unverified source timestamps: unsupported evidence kind")
        if self.source_kind == "SOURCE_FRAME" and not self.frame_refs:
            raise ValueError("visual evidence requires actual source frame refs")
        return self

class CandidateWindowV26(StrictModel):
    window_id: str = Field(min_length=1)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    evidence_ids: list[str] = Field(min_length=1)
    basis: Literal["SUBTITLE", "EDITOR_MARKER", "SOURCE_FRAME", "CHAPTER"]
    prompt_en: str = Field(min_length=12)

    @model_validator(mode="after")
    def ordered_window(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("window end must exceed start")
        return self

class SourceScoutPlanV26(StrictModel):
    schema_version: Literal["2.6"] = "2.6"
    source_id: str = Field(min_length=1)
    youtube_url: str = Field(pattern=r"^https://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)")
    source_mode: Literal["METADATA_ONLY", "SUBTITLE_ENRICHED", "AUTHORIZED_SOURCE_FRAMES"]
    source_downloaded: bool = False
    openai_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    source_summary: str
    global_opus_prompt_en: str = Field(min_length=12)
    evidence: list[SourceEvidenceV26] = Field(default_factory=list)
    candidate_windows: list[CandidateWindowV26] = Field(default_factory=list)
    source_transcript_available: bool = False

    @model_validator(mode="after")
    def validate_context_scope(self):
        if self.source_mode == "METADATA_ONLY":
            if self.candidate_windows:
                raise ValueError("metadata-only cannot invent source-range windows")
            if self.source_transcript_available:
                raise ValueError("metadata-only cannot contain source transcript")
        if self.source_mode != "AUTHORIZED_SOURCE_FRAMES" and self.source_downloaded:
            raise ValueError("zero-download scout cannot claim source video downloaded")
        if self.source_mode == "AUTHORIZED_SOURCE_FRAMES" and not self.source_downloaded:
            raise ValueError("source frame mode needs user-authorized original video frames")
        index = {e.evidence_id: e for e in self.evidence}
        if len(index) != len(self.evidence):
            raise ValueError("duplicate evidence IDs")
        ids = set()
        for w in self.candidate_windows:
            if w.window_id in ids:
                raise ValueError("duplicate window IDs")
            ids.add(w.window_id)
            for evidence_id in w.evidence_ids:
                e = index.get(evidence_id)
                if e is None or e.source_kind != w.basis or e.start_sec is None:
                    raise ValueError("window requires timestamped source evidence of same basis")
                if w.start_sec < e.start_sec - 0.001 or w.end_sec > e.end_sec + 0.001:
                    raise ValueError("window exceeds its verified evidence interval")
        return self

class FrameEvidenceV26(StrictModel):
    clip_time_sec: float = Field(ge=0)
    image_path: str = Field(min_length=5)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_method: Literal["UNIFORM", "SCENE_DETECTION", "ACTION_BURST"]

    @model_validator(mode="after")
    def ensure_local_jpeg(self):
        from pathlib import PurePosixPath
        p = PurePosixPath(self.image_path)
        if p.is_absolute() or ".." in p.parts or p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("frame path must be safe relative image path")
        return self

class SpeechSegmentV26(StrictModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    text_de: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Literal[
        "FASTER_WHISPER", "WHISPER_API", "HUMAN_VERIFIED",
        "OPUS_CLIP_SRT", "OPUS_CLIP_TIMED_JSON", "OPUS_PROJECT_MAP",
        "opus_clip_srt", "opus_clip_timed_json", "opus_project_verified_map"
    ]

    @model_validator(mode="after")
    def order(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("invalid speech segment interval")
        return self

class ClipEvidenceBundleV26(StrictModel):
    schema_version: Literal["2.6"] = "2.6"
    clip_uid: str = Field(min_length=1)
    clip_duration_sec: float = Field(gt=0)
    video_path: str = Field(min_length=5)
    image_frames: list[FrameEvidenceV26] = Field(min_length=1)
    audio_transcript: list[SpeechSegmentV26] = Field(default_factory=list)
    source_fact_refs: list[str] = Field(default_factory=list)
    visual_inspection_ready: bool = True

    @model_validator(mode="after")
    def bound_clip_events(self):
        prev = -1.0
        for f in self.image_frames:
            if f.clip_time_sec > self.clip_duration_sec:
                raise ValueError("frame timestamp exceeds clip duration")
            if f.clip_time_sec <= prev:
                raise ValueError("frames must be strictly chronological and unique")
            prev = f.clip_time_sec
        for s in self.audio_transcript:
            if s.end_sec > self.clip_duration_sec + 0.05:
                raise ValueError("speech exceeds clip duration")
        if not self.visual_inspection_ready:
            raise ValueError("cannot build script-evidence bundle before video inspection")
        return self

class SolRequestContentV26(StrictModel):
    """Validate requested OpenAI multimodal item types before making API calls.
    Media URL and local file bytes are assembled by caller, not inside this schema.
    """
    type: Literal["input_text", "input_image"]
    text: str | None = None
    image_url: str | None = None

    @model_validator(mode="after")
    def legal_content(self):
        if self.type == "input_text" and not self.text:
            raise ValueError("input_text needs text")
        if self.type == "input_image" and not self.image_url:
            raise ValueError("input_image needs image_url")
        return self
