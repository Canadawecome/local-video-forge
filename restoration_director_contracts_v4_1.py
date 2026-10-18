"""Restoration Cut & Edit Director — SPEC v4.1 Contracts & Schemas.
Enforces single adaptive 75-150s full-transformation video, strict single-video policy,
restoration stage taxonomy, audio-first ASMR, and handoff contracts.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RestorationStage(str, Enum):
    BEFORE = "BEFORE"
    INSPECTION = "INSPECTION"
    DISASSEMBLY = "DISASSEMBLY"
    RUST_REMOVAL = "RUST_REMOVAL"
    CLEANING = "CLEANING"
    REPAIR = "REPAIR"
    HEATING_FORGING = "HEATING_FORGING"
    GRINDING = "GRINDING"
    POLISHING = "POLISHING"
    PAINT_FINISH = "PAINT_FINISH"
    ASSEMBLY = "ASSEMBLY"
    TEST = "TEST"
    AFTER_REVEAL = "AFTER_REVEAL"
    OTHER = "OTHER"


MIN_RUNTIME_MS = 75000   # 75.0s
MAX_RUNTIME_MS = 150000  # 150.0s
FRAME_TOLERANCE_MS = 500 # Frame alignment leeway


class RuntimeDecision(StrictModel):
    mode: Literal["SINGLE_FULL"] = "SINGLE_FULL"
    target_duration_ms: int = Field(ge=MIN_RUNTIME_MS - FRAME_TOLERANCE_MS, le=MAX_RUNTIME_MS + FRAME_TOLERANCE_MS)
    reason: str = Field(min_length=5)
    duration_candidate_ranges: list[str] = Field(default_factory=lambda: ["75-90s", "90-120s", "120-150s"])
    preserved_key_stages: list[str] = Field(default_factory=list)
    lost_if_shortened: list[str] = Field(default_factory=list)
    why_not_longer: str = Field(min_length=5)

    @model_validator(mode="after")
    def validate_single_policy(self) -> RuntimeDecision:
        if self.mode != "SINGLE_FULL":
            raise ValueError(f"SPEC v4.1 strictly forbids multi-part modes; got {self.mode}")
        return self


class NarrationFlex(StrictModel):
    safe_to_extend: bool = False
    min_duration_ms: int = Field(ge=0)
    max_duration_ms: int = Field(ge=0)
    critical_asmr: bool = False
    do_not_cut: bool = False
    source_available_ms: int | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> NarrationFlex:
        if self.max_duration_ms < self.min_duration_ms:
            raise ValueError("max_duration_ms must be >= min_duration_ms")
        return self


class ReframeROI(StrictModel):
    mode: Literal["smart_reframe", "split_screen", "blurred_background_with_full_frame"] = "smart_reframe"
    roi: list[float] = Field(default_factory=lambda: [0.2, 0.05, 0.6, 0.9])  # [x, y, w, h] normalized

    @field_validator("roi")
    @classmethod
    def validate_roi(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("ROI must be [x, y, w, h] with 4 elements")
        for val in v:
            if not (0.0 <= val <= 1.0):
                raise ValueError("ROI coordinates must be normalized between 0.0 and 1.0")
        if v[2] <= 0.0 or v[3] <= 0.0:
            raise ValueError("ROI width and height must be positive")
        return v


class EditDecision(StrictModel):
    edit_id: str = Field(pattern=r"^e\d{3,}$")
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(gt=0)
    output_start_ms: int = Field(ge=0)
    output_end_ms: int = Field(gt=0)
    stage: RestorationStage
    same_object_id: str = Field(min_length=1)
    purpose: str = Field(min_length=3)
    action_peak_ms: int | None = None
    playback_speed: float = Field(default=1.0, ge=0.5, le=2.5)
    reframe: ReframeROI = Field(default_factory=ReframeROI)
    source_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    asmr_priority: Literal["low", "medium", "high", "critical"] = "medium"
    narration_flex: NarrationFlex

    @model_validator(mode="after")
    def validate_intervals(self) -> EditDecision:
        if self.source_end_ms <= self.source_start_ms:
            raise ValueError(f"source_end_ms ({self.source_end_ms}) must exceed source_start_ms ({self.source_start_ms})")
        if self.output_end_ms <= self.output_start_ms:
            raise ValueError(f"output_end_ms ({self.output_end_ms}) must exceed output_start_ms ({self.output_start_ms})")
        expected_dur = (self.source_end_ms - self.source_start_ms) / self.playback_speed
        actual_dur = self.output_end_ms - self.output_start_ms
        if abs(expected_dur - actual_dur) > 100.0:
            raise ValueError(f"Duration mismatch: expected {expected_dur:.1f}ms from speed {self.playback_speed}, got {actual_dur}ms")
        return self


class EffectItem(StrictModel):
    type: Literal["matched_flash_cut", "dissolve", "hard_cut", "speed_ramp", "ting_accent"]
    between: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=120, ge=0, le=1000)


class RestorationCutDirectorOutput(StrictModel):
    schema_version: Literal["4.1"] = "4.1"
    source_id: str = Field(min_length=1)
    analysis_coverage_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    runtime_decision: RuntimeDecision
    edits: list[EditDecision] = Field(default_factory=list)
    effects: list[EffectItem] = Field(default_factory=list)
    status: Literal[
        "READY_FOR_RENDER",
        "INSUFFICIENT_STRONG_FOOTAGE",
        "MISSING_TRANSFORMATION_PAYOFF",
        "NEEDS_EDITORIAL_REVIEW",
    ] = "READY_FOR_RENDER"

    @model_validator(mode="after")
    def validate_story_and_timeline(self) -> RestorationCutDirectorOutput:
        # If insufficient or missing payoff, edits may be partial or empty
        if self.status in {"INSUFFICIENT_STRONG_FOOTAGE", "MISSING_TRANSFORMATION_PAYOFF", "NEEDS_EDITORIAL_REVIEW"}:
            return self

        if not self.edits:
            raise ValueError("READY_FOR_RENDER requires at least one edit decision")

        # 1. Timeline contiguity and non-overlapping check
        prev_end = 0
        for i, e in enumerate(self.edits):
            if i == 0 and e.output_start_ms != 0:
                raise ValueError(f"First edit must start at output 0ms, got {e.output_start_ms}")
            if i > 0 and e.output_start_ms != prev_end:
                raise ValueError(f"Gap or overlap at edit {e.edit_id}: starts at {e.output_start_ms}ms, prev ended at {prev_end}ms")
            prev_end = e.output_end_ms

        # 2. Hard duration policy: 75,000 - 150,000 ms (+/- tolerance)
        total_output_ms = self.edits[-1].output_end_ms
        if total_output_ms < MIN_RUNTIME_MS - FRAME_TOLERANCE_MS:
            raise ValueError(f"Output duration {total_output_ms}ms is under strict 75s minimum (got {total_output_ms/1000.0:.2f}s)")
        if total_output_ms > MAX_RUNTIME_MS + FRAME_TOLERANCE_MS:
            raise ValueError(f"Output duration {total_output_ms}ms exceeds strict 150s maximum (got {total_output_ms/1000.0:.2f}s)")

        # 3. Exactly ONE video check: forbid part references or split IDs
        for e in self.edits:
            if re.search(r"part[_\-\s]?\d", e.edit_id, re.IGNORECASE) or re.search(r"episode[_\-\s]?\d", e.edit_id, re.IGNORECASE):
                raise ValueError(f"SPEC v4.1 forbids multi-part edit IDs; found {e.edit_id}")

        return self


# Section 4 Handoff Models (Downstream Review Module Compatibility)

class StoryMapStage(StrictModel):
    stage_id: str
    stage_name: RestorationStage
    output_start_sec: float = Field(ge=0.0)
    output_end_sec: float = Field(gt=0.0)
    object_identity: str
    visual_transformation: str
    factual_observations: list[str] = Field(default_factory=list)


class AudioEvent(StrictModel):
    event_id: str
    sound_type: Literal["impact", "grinding", "scrubbing", "clicking", "scraping", "cutting", "machine", "other"]
    source_time_ms: int = Field(ge=0)
    output_time_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    ducking_recommended: bool = False


class QAReportV41(StrictModel):
    schema_version: Literal["4.1"] = "4.1"
    verdict: Literal["PASS", "REVISE_EDL", "NEEDS_HUMAN_REVIEW"]
    actual_duration_sec: float
    within_75_150s: bool
    single_video_verified: bool
    object_identity_verified: bool
    transformation_complete: bool
    audio_clipping_detected: bool = False
    black_frames_detected: bool = False
    observations: list[str] = Field(default_factory=list)
    revision_count: int = Field(default=0, ge=0, le=2)
