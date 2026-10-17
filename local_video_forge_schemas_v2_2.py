"""Local Video Forge v2.2 — schemas and semantic validators.

Python 3.11+, pydantic>=2.6.  Model output is untrusted until both
Pydantic and validate_against_media() succeed.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


EPS = 0.05


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateWindow(Strict):
    window_id: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    asmr_quality_score: float = Field(ge=0, le=1)
    custom_prompt: str = Field(min_length=15, max_length=600)
    rationale: str

    @model_validator(mode="after")
    def check_interval(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("candidate end_sec must be greater than start_sec")
        return self


class OpusScoutPlan(Strict):
    video_summary: str
    candidate_windows: list[CandidateWindow] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def check_unique_ids(self):
        ids = [x.window_id for x in self.candidate_windows]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate window ids")
        return self


class Interval(Strict):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def correct_order(self):
        if self.end <= self.start:
            raise ValueError("end must exceed start")
        return self


class Shot(Strict):
    shot_id: str
    # Source coordinates are ALWAYS local to the chosen input asset, not YouTube.
    asset_id: str
    source_in: float = Field(ge=0)
    source_out: float = Field(gt=0)
    output_start: float = Field(ge=0)
    output_end: float = Field(gt=0)
    speed: float = Field(ge=0.85, le=1.25)
    label: Literal["ACTION", "DETAIL", "TALKING_HEAD", "INTERVIEW", "ASMR", "MUSIC", "SILENCE"]
    role: Literal["hook", "body", "payoff", "bridge"]
    reframe_mode: Literal["keep_opus_9_16", "local_dynamic_crop"]
    fine_crop_offset_x: float = Field(ge=-0.15, le=0.15)
    audio_mode: Literal["raw_asmr", "stem_dubbed", "ducked_ambience", "muted"]

    @model_validator(mode="after")
    def check_duration(self):
        if self.source_out <= self.source_in:
            raise ValueError(f"{self.shot_id}: invalid source interval")
        if self.output_end <= self.output_start:
            raise ValueError(f"{self.shot_id}: invalid output interval")
        expected = (self.source_out - self.source_in) / self.speed
        actual = self.output_end - self.output_start
        if abs(expected - actual) > EPS:
            raise ValueError(f"{self.shot_id}: expected {expected:.3f}s, got {actual:.3f}s")
        return self


class Narration(Strict):
    track_id: str
    track_type: Literal["dub", "commentary"]
    shot_id: str
    output_in: float = Field(ge=0)
    output_out: float = Field(gt=0)
    de_source_text: str | None
    en_script_text: str = Field(min_length=2)
    evidence_refs: list[str]
    remove_original_vocals: bool
    adaptive_duck_db: float = Field(ge=-14, le=-5)
    adaptive_stem_gain: float = Field(ge=0.60, le=1.05)

    @model_validator(mode="after")
    def check_narration(self):
        if self.output_out <= self.output_in:
            raise ValueError(f"{self.track_id}: invalid narration range")
        if self.track_type == "dub" and not self.de_source_text:
            raise ValueError(f"{self.track_id}: dub requires German source transcription")
        if not self.evidence_refs:
            raise ValueError(f"{self.track_id}: must refer to at least one verified source")
        words = len(self.en_script_text.split())
        if words / (self.output_out - self.output_in) > 3.5:
            raise ValueError(f"{self.track_id}: excessive estimated speech rate")
        return self


class AudioConfig(Strict):
    default_duck_db: float = Field(ge=-14, le=-5)
    fade_ms: int = Field(ge=40, le=300)
    audio_boundary_fade_ms: int = Field(ge=0, le=100)
    target_lufs: float = Field(ge=-18, le=-12)
    true_peak_dbtp: float = Field(ge=-3, le=-1)
    vocal_separation_policy: Literal["conditional_qc", "never"]


class CaptionConfig(Strict):
    enabled: bool
    format: Literal["ass"]
    style_preset: Literal["pace-adaptive", "minimal-clean"]
    vertical_position_pct: int = Field(ge=65, le=82)
    max_words_per_line: int = Field(ge=2, le=6)
    hide_intervals: list[Interval]


class ZoomEffect(Strict):
    shot_id: str
    output_start: float = Field(ge=0)
    duration: float = Field(gt=0, le=3.5)
    start_scale: float = Field(ge=1, le=1.08)
    end_scale: float = Field(ge=1, le=1.08)
    easing: Literal["linear", "ease_in_out_sine"]


class EffectsConfig(Strict):
    zooms: list[ZoomEffect]


class ExportConfig(Strict):
    width: Literal[1080]
    height: Literal[1920]
    fps: Literal[24, 25, 30, 50, 60]
    codec: Literal["h264"]
    crf: int = Field(ge=16, le=23)
    pixel_format: Literal["yuv420p"]


class EditPlanV22(Strict):
    schema_version: Literal["2.2"]
    source_origin: Literal["opusclip_clean_plate", "licensed_source_fallback"]
    source_youtube_url: str | None
    edit_mode: Literal["A", "B", "C"]
    mode_reason: str
    shots: list[Shot]
    narration_tracks: list[Narration]
    audio_mastering: AudioConfig
    captions: CaptionConfig
    effects: EffectsConfig
    export: ExportConfig

    @model_validator(mode="after")
    def check_timeline(self):
        if not self.shots:
            raise ValueError("at least one shot required")
        sid = [s.shot_id for s in self.shots]
        if len(sid) != len(set(sid)):
            raise ValueError("duplicate shot_id")
        s_by_id = {s.shot_id: s for s in self.shots}
        current = 0.0
        for shot in self.shots:
            if abs(shot.output_start - current) > EPS:
                raise ValueError(f"timeline gap/overlap before {shot.shot_id}")
            current = shot.output_end
        nids = [n.track_id for n in self.narration_tracks]
        if len(nids) != len(set(nids)):
            raise ValueError("duplicate track_id")
        if self.edit_mode == "A" and self.narration_tracks:
            raise ValueError("ASMR_ONLY cannot contain narration")
        if self.edit_mode in ("B", "C") and not self.narration_tracks:
            raise ValueError("dubbing/commentary mode requires narration")
        if self.edit_mode == "A" and self.captions.enabled:
            raise ValueError("ASMR_ONLY should not invent dialogue captions")
        last_end = 0.0
        sum_dur = 0.0
        for n in self.narration_tracks:
            if n.shot_id not in s_by_id:
                raise ValueError(f"{n.track_id}: referenced shot not found")
            shot = s_by_id[n.shot_id]
            if n.output_in < shot.output_start - EPS or n.output_out > shot.output_end + EPS:
                raise ValueError(f"{n.track_id}: must fit in referenced shot")
            if n.output_in < last_end - 0.02:
                raise ValueError("overlapping narration tracks")
            if n.output_out > current + EPS:
                raise ValueError("narration outside final video")
            last_end = n.output_out
            sum_dur += n.output_out - n.output_in
            if self.edit_mode == "B" and n.track_type != "dub":
                raise ValueError("mode B narration must be dub")
            if self.edit_mode == "C" and n.track_type != "commentary":
                raise ValueError("mode C narration must be commentary")
        if current and sum_dur / current > 0.75:
            raise ValueError("narration occupies more than 75% of runtime")
        for z in self.effects.zooms:
            if z.shot_id not in s_by_id:
                raise ValueError("zoom references unknown shot")
            s = s_by_id[z.shot_id]
            if z.output_start < s.output_start - EPS or z.output_start + z.duration > s.output_end + EPS:
                raise ValueError("zoom extends outside referenced shot")
        for c in self.captions.hide_intervals:
            if c.end > current + EPS:
                raise ValueError("caption hide_interval exceeds video length")
        return self


def validate_against_media(plan: EditPlanV22, asset_durations: dict[str, float],
                           verified_evidence_ids: set[str]) -> None:
    """Call AFTER probing source media and building a verified evidence registry."""
    for s in plan.shots:
        if s.asset_id not in asset_durations:
            raise ValueError(f"asset not found: {s.asset_id}")
        if s.source_out > asset_durations[s.asset_id] + EPS:
            raise ValueError(f"shot {s.shot_id} exceeds asset duration")
    for n in plan.narration_tracks:
        missing = set(n.evidence_refs) - verified_evidence_ids
        if missing:
            raise ValueError(f"narration {n.track_id}: unverified evidence {sorted(missing)}")


def tts_sync_action(measured_tts_s: float, available_window_s: float,
                    min_atempo: float = 0.95, max_atempo: float = 1.08) -> tuple[str, float]:
    """FFmpeg atempo > 1 speeds up, < 1 slows down; preserves pitch approximately."""
    if measured_tts_s <= 0 or available_window_s <= 0:
        raise ValueError("durations must be > 0")
    required = measured_tts_s / available_window_s
    if min_atempo <= required <= max_atempo:
        return ("atempo", required)
    return ("rewrite_or_move_window", required)
