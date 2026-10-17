"""v3.4 GPT-first viral clip planning and conservative post-Opus approval schemas.

A generated model opinion is not a guarantee of virality or a substitute for footage review.
All timestamps refer to the original media in the matching evidence manifest.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Frame(Strict):
    id: str = Field(min_length=1)
    time_sec: float = Field(ge=0)
    path: str = Field(min_length=1)


class EvidenceManifest(Strict):
    schema_version: Literal['3.4'] = '3.4'
    media_kind: Literal['SOURCE', 'OPUS_CLIP']
    media_sha256: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$')
    media_file: str = Field(min_length=1)
    duration_sec: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    frames: list[Frame] = Field(min_length=1)
    transcript_path: str | None = None
    visual_sampling_note: str = Field(min_length=1)

    @model_validator(mode='after')
    def check_frames(self):
        if len({f.id for f in self.frames}) != len(self.frames):
            raise ValueError('Duplicate evidence frame id')
        if any(f.time_sec > self.duration_sec + .15 for f in self.frames):
            raise ValueError('Evidence frame outside media duration')
        return self


class ViralCandidate(Strict):
    id: str = Field(min_length=1)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    hook_at_sec: float = Field(ge=0)
    evidence_frame_ids: list[str] = Field(min_length=1)
    hook_visual: str = Field(min_length=12)
    actions: list[str] = Field(min_length=1)
    hook_why: str = Field(min_length=12)
    asmr_notes: str = Field(min_length=5)
    narrative_arc: str = Field(min_length=12)
    potential_score: int = Field(ge=0, le=100)
    uncertainty_notes: str = Field(min_length=2)
    desired_clip_min_sec: int = Field(default=45, ge=10, le=180)
    desired_clip_max_sec: int = Field(default=90, ge=10, le=180)

    @model_validator(mode='after')
    def check_times(self):
        if self.end_sec <= self.start_sec:
            raise ValueError('End must exceed start')
        if not self.start_sec <= self.hook_at_sec <= self.end_sec:
            raise ValueError('Hook must be inside source interval')
        if self.desired_clip_max_sec < self.desired_clip_min_sec:
            raise ValueError('Bad target duration')
        return self


class PrecutPlan(Strict):
    schema_version: Literal['3.4'] = '3.4'
    mode: Literal['GPT_FIRST_VIRAL_DIRECTOR'] = 'GPT_FIRST_VIRAL_DIRECTOR'
    source_sha256: str = Field(min_length=64, max_length=64)
    source_duration_sec: float = Field(gt=0)
    rights_status: Literal['VERIFIED','UNKNOWN','BLOCKED'] = 'UNKNOWN'
    analysis_model: str = Field(min_length=2)
    source_country_status: Literal['UNKNOWN','VERIFIED'] = 'UNKNOWN'
    source_language: str = 'und'
    production_topic_en: str = Field(min_length=2)
    candidates: list[ViralCandidate] = Field(min_length=1)

    @model_validator(mode='after')
    def check_plan(self):
        if len({x.id for x in self.candidates}) != len(self.candidates):
            raise ValueError('Duplicate candidate id')
        if any(x.end_sec > self.source_duration_sec + .1 for x in self.candidates):
            raise ValueError('Candidate beyond end of source')
        return self


class ReviewScores(Strict):
    hook: int = Field(ge=0, le=100)
    action_asmr: int = Field(ge=0, le=100)
    narrative_arc: int = Field(ge=0, le=100)
    vertical_framing: int = Field(ge=0, le=100)
    pacing: int = Field(ge=0, le=100)
    english_story_potential: int = Field(ge=0, le=100)

    def total(self) -> float:
        return round(self.hook*.25+self.action_asmr*.25+self.narrative_arc*.20+
                     self.vertical_framing*.15+self.pacing*.10+self.english_story_potential*.05, 2)


class PostcutReview(Strict):
    schema_version: Literal['3.4'] = '3.4'
    source_candidate_id: str = Field(min_length=1)
    clip_sha256: str = Field(min_length=64, max_length=64)
    clip_duration_sec: float = Field(gt=0)
    review_model: str = Field(min_length=2)
    analyzed_media: Literal['EXPORTED_CLIP_VISUAL_FRAMES'] = 'EXPORTED_CLIP_VISUAL_FRAMES'
    review_evidence_frame_ids: list[str] = Field(min_length=2)
    hook_evidence_frame_ids: list[str] = Field(min_length=1)
    scores: ReviewScores
    includes_real_mechanical_action: bool
    has_obvious_visual_hook: bool
    coherent_visual_story: bool
    subject_framed_correctly: bool
    serious_export_defect: bool
    content_rights_reviewed: bool
    mapped_to_planned_source: Literal['VERIFIED','UNVERIFIED','MISMATCH'] = 'UNVERIFIED'
    source_mapping_evidence: str | None = None
    model_confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1)
    suggested_recut: str | None = None
    asmr_warning: str = Field(min_length=1)

    @model_validator(mode='after')
    def check_review(self):
        if self.mapped_to_planned_source == 'VERIFIED' and not (self.source_mapping_evidence or '').strip():
            raise ValueError('Verified mapping must cite source range or human verification')
        if self.mapped_to_planned_source != 'VERIFIED' and self.source_mapping_evidence:
            raise ValueError('Mapping evidence only allowed for VERIFIED mapping')
        return self


class Approval(Strict):
    schema_version: Literal['3.4'] = '3.4'
    status: Literal['APPROVED','RECUT','REJECTED','HOLD']
    candidate_id: str
    media_sha256: str
    review_sha256: str
    evidence_sha256: str
    precut_plan_sha256: str
    mapping_sha256: str
    score: float
    blockers: list[str]
    next_step: str


class SourceMapping(Strict):
    schema_version: Literal['3.4'] = '3.4'
    source_candidate_id: str = Field(min_length=1)
    verified_by: Literal['OPUS_PROVIDER','HUMAN_EDITOR']
    opus_project_id: str | None = None
    human_reviewer: str | None = None
    source_time_ranges: list[list[float]] = Field(min_length=1)
    time_unit: Literal['SECONDS','MILLISECONDS']
    evidence_note: str = Field(min_length=5)

    @model_validator(mode='after')
    def validate_mapping(self):
        if self.verified_by == 'OPUS_PROVIDER' and not self.opus_project_id:
            raise ValueError('Opus range verification needs provider project ID')
        if self.verified_by == 'HUMAN_EDITOR' and not self.human_reviewer:
            raise ValueError('Manual range verification needs editor ID')
        if any(len(r)!=2 or r[0]<0 or r[1]<=r[0] for r in self.source_time_ranges):
            raise ValueError('Invalid source time ranges')
        return self
