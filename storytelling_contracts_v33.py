"""v3.3 Universal Source story plan (no source-country/source-language default).

Structured analysis must be supplied by an upstream vision/transcript adapter and
reviewed as needed. This module DOES NOT identify language or location by itself.
"""
from __future__ import annotations
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Interval(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def check_interval(self):
        if self.end <= self.start:
            raise ValueError('end must be greater than start')
        return self

class SourceSpeech(Interval):
    id: str = Field(min_length=1)
    language: str = 'und'  # e.g. ko, ja, de, mul, und; not a country code
    transcript: str = ''
    evidence_ref: str | None = None

    @model_validator(mode='after')
    def check_language(self):
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', self.language):
            raise ValueError('Speech language must be BCP-47 style or und/mul')
        return self

class SourceFact(StrictModel):
    claim_en: str = Field(min_length=2)
    evidence_refs: list[str] = Field(min_length=1)

class SourceContext(StrictModel):
    # 'und' = undetermined. Never imply de/DE when unknown.
    source_language: str = 'und'
    source_language_status: Literal['CONFIRMED','UNDETERMINED'] = 'UNDETERMINED'
    language_evidence_refs: list[str] = Field(default_factory=list)
    source_country: str | None = None  # ISO 3166-1 alpha-2, e.g. KR, JP, DE
    source_country_status: Literal['VERIFIED','UNKNOWN'] = 'UNKNOWN'
    country_evidence_refs: list[str] = Field(default_factory=list)
    country_reviewed_by: str | None = None
    topic_en: str = Field(min_length=2)
    verified_facts: list[SourceFact] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_context(self):
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', self.source_language):
            raise ValueError('source_language must be BCP-47 style or und/mul')
        if self.source_language_status == 'CONFIRMED':
            if self.source_language in ('und','mul') or not self.language_evidence_refs:
                raise ValueError('Confirmed source language needs a language code and evidence')
        elif self.source_language != 'und':
            raise ValueError('Unconfirmed source language must use und, not a guess')
        if self.source_country_status == 'VERIFIED':
            if (not self.source_country or not re.fullmatch('[A-Z]{2}',self.source_country)
                or not self.country_evidence_refs or not (self.country_reviewed_by or '').strip()):
                raise ValueError('Verified source country needs ISO code, evidence, and a reviewer')
        elif self.source_country is not None or self.country_evidence_refs or self.country_reviewed_by:
            raise ValueError('Unknown country must be null with no invented evidence')
        return self

class ProtectedASMR(Interval):
    kind: Literal['hammer','grinding','saw','forge','machine','other'] = 'hammer'

class NarrationSegment(Interval):
    id: str = Field(min_length=1)
    text_en: str = Field(min_length=1)
    audio_path: str | None = None
    evidence_refs: list[str] = Field(min_length=1)
    role: Literal['hook','process','transition','payoff','explanation'] = 'process'

class AudioSettings(StrictModel):
    voice_gain_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    peak_ceiling_dbfs: float = Field(default=-1.0, ge=-6.0, le=-0.3)
    bed_ducking_db: float = Field(default=0.0, ge=-12.0, le=0.0)
    audio_direction_notes: str = Field(default='')

class StorytellingPlan(StrictModel):
    schema_version: Literal['3.3'] = '3.3'
    clip_uid: str = Field(min_length=1)
    mode: Literal['ENGLISH_STORYTELLING_WITH_CLEAN_ASMR'] = 'ENGLISH_STORYTELLING_WITH_CLEAN_ASMR'
    rights_status: Literal['VERIFIED','UNKNOWN','BLOCKED'] = 'UNKNOWN'
    music_rights_status: Literal['NO_MUSIC','CLEARED','UNKNOWN','BLOCKED'] = 'UNKNOWN'
    source_context: SourceContext
    source_speech_status: Literal['CONFIRMED_PRESENT','CONFIRMED_ABSENT','UNCERTAIN'] = 'UNCERTAIN'
    source_speech: list[SourceSpeech] = Field(default_factory=list)
    protected_asmr: list[ProtectedASMR] = Field(default_factory=list)
    narration_segments: list[NarrationSegment] = Field(default_factory=list)
    approved_workshop_stem_path: str | None = None
    workshop_stem_qc_passed: bool = False
    settings: AudioSettings = Field(default_factory=AudioSettings)
    voice_id: str = 'QIhD5ivPGEoYZQDocuHI'
    tts_model_id: str = 'eleven_multilingual_v2'

    @model_validator(mode='after')
    def validate_plan(self):
        if self.rights_status != 'VERIFIED':
            raise ValueError('rights_status must be VERIFIED')
        if self.music_rights_status not in ('NO_MUSIC','CLEARED'):
            raise ValueError('music rights must be reviewed')
        if self.source_speech_status == 'UNCERTAIN':
            raise ValueError('source speech status must be confirmed before rendering')
        if not self.narration_segments:
            raise ValueError('storytelling needs original English narration')
        if self.source_speech_status == 'CONFIRMED_PRESENT' and (
            not self.approved_workshop_stem_path or not self.workshop_stem_qc_passed):
            raise ValueError('CONFIRMED_PRESENT requires full-length approved speech-free workshop stem')
        if self.source_speech_status == 'CONFIRMED_ABSENT' and (
            self.approved_workshop_stem_path or self.source_speech):
            raise ValueError('No source speech: reviewed raw bed only, no speech segments')
        if len({x.id for x in self.narration_segments}) != len(self.narration_segments):
            raise ValueError('Duplicate narration IDs')
        if len({x.id for x in self.source_speech}) != len(self.source_speech):
            raise ValueError('Duplicate source speech IDs')
        ordered = sorted(self.narration_segments, key=lambda x:x.start)
        for left, right in zip(ordered,ordered[1:]):
            if left.end > right.start + 0.001:
                raise ValueError('English narration windows overlap')
        from story_claim_guard_v33 import validate_geography_claims
        validate_geography_claims(self, ' '.join(s.text_en for s in self.narration_segments), field='narration_segments')
        return self

    def validate_duration(self,duration_sec: float):
        for k in ('source_speech','protected_asmr','narration_segments'):
            for s in getattr(self,k):
                if s.end > duration_sec + .075:
                    raise ValueError(f'{k}: out of video timeline')
