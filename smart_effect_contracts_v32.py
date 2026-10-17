"""Validated, time-preserving visual effect contract for Local Video Forge v3.2.

No edits that move frames in time are executable under this contract. Thus
ASMR, English ElevenLabs narration and TTS captions remain in sync.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class MicroZoom(Strict):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    peak_scale: float = Field(default=1.045, ge=1.0, le=1.05)
    center_x: float = Field(default=.5, ge=.20, le=.80)
    center_y: float = Field(default=.5, ge=.20, le=.80)
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode='after')
    def check(self):
        if not (.65 <= self.end-self.start <= 3.5):
            raise ValueError('zoom duration must be 0.65..3.5 seconds')
        return self

class Grading(Strict):
    contrast: float = Field(default=1.04, ge=.98, le=1.08)
    saturation: float = Field(default=1.035, ge=.98, le=1.08)
    brightness: float = Field(default=0.0, ge=-.025, le=.025)

class HookSuggestion(Strict):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    evidence_ref: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    status: Literal['REQUIRES_UPSTREAM_RECUT'] = 'REQUIRES_UPSTREAM_RECUT'

    @model_validator(mode='after')
    def check(self):
        if self.end<=self.start or self.end-self.start>3:
            raise ValueError('hook suggestion invalid')
        return self

class SmartEffectPlan(Strict):
    schema_version: Literal['3.2'] = '3.2'
    preset: Literal['CINEMATIC_ASMR'] = 'CINEMATIC_ASMR'
    source_clip_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    duration_seconds: float = Field(gt=0)
    timeline_policy: Literal['PRESERVE_SOURCE_TIMECODES'] = 'PRESERVE_SOURCE_TIMECODES'
    audio_policy: Literal['NO_AUDIO_MODIFICATION'] = 'NO_AUDIO_MODIFICATION'
    grading: Grading = Field(default_factory=Grading)
    micro_zooms: list[MicroZoom] = Field(default_factory=list, max_length=8)
    result_first_hook: HookSuggestion | None = None
    storyboard_notes: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def validate_windows(self):
        last_end = 0.0
        for z in sorted(self.micro_zooms, key=lambda item:item.start):
            if z.start < last_end-1e-6:
                raise ValueError('Zoom windows overlap')
            if z.end>self.duration_seconds+0.001:
                raise ValueError('Zoom exceeds clip duration')
            last_end=z.end
        if self.result_first_hook and self.result_first_hook.end>self.duration_seconds+.001:
            raise ValueError('Hook suggestion outside clip')
        return self
