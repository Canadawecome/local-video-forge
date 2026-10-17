"""Local Video Forge v2.5 — canonical batch/child-clip data contracts.

Requires pydantic>=2. This module models orchestration identities, manifests and
per-clip publication readiness. It does NOT call any providers or build media.
Use alongside (not instead of) the v2.2-v2.4 shot/audio/evidence contracts.
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class OpusProjectState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


TERMINAL_OPUS_PROJECT_STATES = {
    OpusProjectState.SUCCEEDED, OpusProjectState.FAILED,
    OpusProjectState.TIMED_OUT, OpusProjectState.CANCELLED,
}


class ClipState(str, Enum):
    DISCOVERED = "DISCOVERED"
    ASSET_DOWNLOADED = "ASSET_DOWNLOADED"
    PREFLIGHT_QC_PASS = "PREFLIGHT_QC_PASS"
    INSPECTED = "INSPECTED"
    SCRIPT_DRAFTED = "SCRIPT_DRAFTED"
    SCRIPT_APPROVED = "SCRIPT_APPROVED"
    TTS_DONE = "TTS_DONE"
    AUDIO_QC_PASS = "AUDIO_QC_PASS"
    PREVIEW_READY = "PREVIEW_READY"
    FINAL_READY = "FINAL_READY"
    FINAL_QC_PASS = "FINAL_QC_PASS"
    PUBLISH_READY = "PUBLISH_READY"
    REJECTED_QC = "REJECTED_QC"
    REJECTED_RIGHTS = "REJECTED_RIGHTS"
    REJECTED_EDITORIAL = "REJECTED_EDITORIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    TTS_FAILED = "TTS_FAILED"
    RENDER_FAILED = "RENDER_FAILED"
    FINAL_QC_FAILED = "FINAL_QC_FAILED"
    CANCELLED = "CANCELLED"


class RightsState(str, Enum):
    VERIFIED = "VERIFIED"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


class NarrationMode(str, Enum):
    SELECTIVE_DUBBING = "SELECTIVE_DUBBING"
    ORIGINAL_COMMENTARY = "ORIGINAL_COMMENTARY"
    ASMR_ONLY = "ASMR_ONLY"


class BatchState(str, Enum):
    CREATED = "CREATED"
    PREFLIGHT_PASS = "PREFLIGHT_PASS"
    SCOUT_DONE = "SCOUT_DONE"
    OPUS_SUBMITTED = "OPUS_SUBMITTED"
    OPUS_RUNNING = "OPUS_RUNNING"
    OPUS_BATCH_COMPLETE = "OPUS_BATCH_COMPLETE"
    CLIPS_ENUMERATED = "CLIPS_ENUMERATED"
    CHILD_JOBS_ACTIVE = "CHILD_JOBS_ACTIVE"
    BATCH_COMPLETE = "BATCH_COMPLETE"
    BATCH_PARTIAL = "BATCH_PARTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


CLOSED_BATCH_STATES = {
    BatchState.OPUS_BATCH_COMPLETE, BatchState.CLIPS_ENUMERATED,
    BatchState.CHILD_JOBS_ACTIVE, BatchState.BATCH_COMPLETE,
    BatchState.BATCH_PARTIAL,
}


StrNotBlank = Annotated[str, Field(min_length=1)]


def checked_relative_path(value: str) -> str:
    """Validate a path for storage under a server-defined sandbox root."""
    if not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("Path must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if any(part in {"..", "."} for part in value.split("/")) or path.is_absolute():
        raise ValueError("Path traversal / dot paths forbidden")
    if value.endswith("/") or not path.parts:
        raise ValueError("Path cannot end in slash")
    return value


class OpusProjectRecord(StrictModel):
    project_id: StrNotBlank
    status: OpusProjectState
    candidate_window_id: str | None = None
    request_hash: str | None = None


class ClipScriptRecord(StrictModel):
    clip_uid: StrNotBlank
    revision: int = Field(ge=1)
    story_angle: StrNotBlank
    title_en: StrNotBlank
    script_path: str
    tts_text_path: str
    evidence_refs: list[str] = Field(min_length=1)
    qc_pass: bool = False

    @field_validator("script_path", "tts_text_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return checked_relative_path(value)


class ClipVoiceRecord(StrictModel):
    clip_uid: StrNotBlank
    script_revision: int = Field(ge=1)
    voice_id: StrNotBlank
    model_id: StrNotBlank
    wav_path: str
    alignment_path: str
    qc_pass: bool = False

    @field_validator("wav_path", "alignment_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return checked_relative_path(value)


class ClipPublishPackRecord(StrictModel):
    clip_uid: StrNotBlank
    title_en: StrNotBlank
    description_en: StrNotBlank
    hashtags: list[str] = Field(min_length=1, max_length=20)
    description_path: str
    hashtags_path: str
    final_video_path: str
    qc_pass: bool = False
    human_approved: bool = False

    @field_validator("description_path", "hashtags_path", "final_video_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return checked_relative_path(value)

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, value: list[str]) -> list[str]:
        if len({v.lower() for v in value}) != len(value):
            raise ValueError("Duplicate hashtags")
        if any(not re.fullmatch(r"#[A-Za-z0-9_]+", v) for v in value):
            raise ValueError("Hashtags must be #PascalCase or #letters_numbers")
        return value


class ClipRecord(StrictModel):
    clip_uid: StrNotBlank
    index_no: int = Field(ge=1)
    provider_project_id: StrNotBlank
    provider_clip_id: StrNotBlank
    status: ClipState
    folder: str
    narration_mode: NarrationMode = NarrationMode.ORIGINAL_COMMENTARY
    rights_state: RightsState = RightsState.UNRESOLVED
    accepted: bool = False
    script: ClipScriptRecord | None = None
    voice: ClipVoiceRecord | None = None
    publish_pack: ClipPublishPackRecord | None = None
    final_media_qc_pass: bool = False
    asmr_only_exception_approved: bool = False

    @field_validator("folder")
    @classmethod
    def safe_folder(cls, value: str) -> str:
        return checked_relative_path(value)

    @model_validator(mode="after")
    def ready_is_real(self) -> "ClipRecord":
        if self.script is not None:
            if self.script.clip_uid != self.clip_uid:
                raise ValueError("Wrong script/clip identity")
        if self.voice is not None:
            if self.voice.clip_uid != self.clip_uid:
                raise ValueError("Wrong voice/clip identity")
            if self.script is None or self.voice.script_revision != self.script.revision:
                raise ValueError("Voice does not match approved script revision")
        if self.publish_pack is not None and self.publish_pack.clip_uid != self.clip_uid:
            raise ValueError("Wrong publish_pack/clip identity")

        if self.status == ClipState.PUBLISH_READY:
            if not self.accepted or self.rights_state != RightsState.VERIFIED:
                raise ValueError("Publish-ready clip must be accepted and rights verified")
            if not self.final_media_qc_pass:
                raise ValueError("Publish-ready clip needs passing final media QC")
            if self.script is None or not self.script.qc_pass:
                raise ValueError("Publish-ready clip needs approved script")
            if self.narration_mode == NarrationMode.ASMR_ONLY:
                if not self.asmr_only_exception_approved:
                    raise ValueError("ASMR-only exception requires explicit approval")
            elif self.voice is None or not self.voice.qc_pass:
                raise ValueError("Narrated publish-ready clip needs passing TTS")
            if self.publish_pack is None or not self.publish_pack.qc_pass or not self.publish_pack.human_approved:
                raise ValueError("Publish-ready clip needs reviewed title/description/hashtags")
        return self


class BatchCounts(StrictModel):
    discovered: int = Field(ge=0)
    accepted: int = Field(ge=0)
    script_pass: int = Field(ge=0)
    voice_pass: int = Field(ge=0)
    final_pass: int = Field(ge=0)
    asmr_final_pass: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def verify_order(self) -> "BatchCounts":
        if not (self.final_pass - self.asmr_final_pass <= self.voice_pass <= self.script_pass <= self.accepted <= self.discovered):
            raise ValueError("Invalid narrated batch funnel counts")
        if self.final_pass > self.accepted or self.asmr_final_pass > self.final_pass:
            raise ValueError("Invalid final/ASMR exception counts")
        return self


class BatchManifestV25(StrictModel):
    schema_version: Literal["2.5"] = "2.5"
    batch_id: StrNotBlank
    source_id: StrNotBlank
    youtube_url: StrNotBlank
    batch_status: BatchState
    opus_projects: list[OpusProjectRecord]
    discovered_clips: list[ClipRecord]
    counts: BatchCounts
    opus_batch_closed: bool = False

    @model_validator(mode="after")
    def validate_batch(self) -> "BatchManifestV25":
        if not self.youtube_url.startswith(("https://www.youtube.com/watch?", "https://youtu.be/")):
            raise ValueError("Expected a public YouTube URL form (availability checked separately)")
        if self.opus_batch_closed or self.batch_status in CLOSED_BATCH_STATES:
            if any(p.status not in TERMINAL_OPUS_PROJECT_STATES for p in self.opus_projects):
                raise ValueError("Opus batch barrier cannot close while a project is pending")
        if len({p.project_id for p in self.opus_projects}) != len(self.opus_projects):
            raise ValueError("Duplicate Opus project ID")
        identities = [c.clip_uid for c in self.discovered_clips]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate clip UID")
        indices = [c.index_no for c in self.discovered_clips]
        if len(set(indices)) != len(indices):
            raise ValueError("Duplicate clip index")
        if indices and sorted(indices) != list(range(1, len(indices) + 1)):
            raise ValueError("Clip indices must be contiguous starting from 1")
        if len({c.folder for c in self.discovered_clips}) != len(self.discovered_clips):
            raise ValueError("Each clip must have a separate output folder")
        project_ids = {p.project_id for p in self.opus_projects}
        for c in self.discovered_clips:
            if c.provider_project_id not in project_ids:
                raise ValueError(f"Unknown Opus project for {c.clip_uid}")
            expected_uid = f"{self.source_id}:{c.provider_project_id}:{c.provider_clip_id}"
            if c.clip_uid != expected_uid:
                raise ValueError(f"Clip UID must be canonical: {expected_uid}")
        if self.counts.discovered != len(self.discovered_clips):
            raise ValueError("Discovered count does not equal number of clips")
        if self.counts.accepted != sum(c.accepted for c in self.discovered_clips):
            raise ValueError("Accepted count does not match clip list")
        if self.counts.script_pass != sum(bool(c.script and c.script.qc_pass) for c in self.discovered_clips):
            raise ValueError("Script-pass count does not match clip list")
        if self.counts.voice_pass != sum(bool(c.voice and c.voice.qc_pass) for c in self.discovered_clips):
            raise ValueError("Voice-pass count does not match clip list")
        if self.counts.final_pass != sum(c.status == ClipState.PUBLISH_READY for c in self.discovered_clips):
            raise ValueError("Final-pass count must reflect publish-ready clips")
        asmr_ready = sum(c.status == ClipState.PUBLISH_READY and c.narration_mode == NarrationMode.ASMR_ONLY for c in self.discovered_clips)
        if self.counts.asmr_final_pass != asmr_ready:
            raise ValueError("ASMR final exception count does not match clip list")
        return self


if __name__ == "__main__":
    print("Contract module imported OK. Run accompanying unittest for smoke validation.")
