"""Authoritative v3.1 plan: ENGLISH_STORYTELLING_WITH_CLEAN_ASMR, no per-sentence dubbing.

Speech removal and story narration are independent operations. The source-language
transcript is evidence only; there is no speech_ids mapping for English narration.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Interval(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def check_time(self):
        if self.end <= self.start:
            raise ValueError('end must be greater than start')
        return self

class GermanSpeech(Interval):
    id: str = Field(min_length=1)
    text_de: str = ''
    evidence_ref: str | None = None

class ProtectedASMR(Interval):
    kind: Literal['hammer','grinding','saw','forge','machine','other'] = 'hammer'

class NarrationSegment(Interval):
    id: str = Field(min_length=1)
    text_en: str = Field(min_length=1)
    audio_path: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    role: Literal['hook','process','transition','payoff','explanation'] = 'process'

class AudioSettings(StrictModel):
    voice_gain_db: float = Field(default=0.0, ge=-12.0, le=6.0)
    peak_ceiling_dbfs: float = Field(default=-1.0, ge=-6.0, le=-0.3)
    # No duck_db by design. Prevent resurrection of the v1.0 30-40% ambience bug.

class StorytellingPlan(StrictModel):
    schema_version: Literal['3.1'] = '3.1'
    clip_uid: str = Field(min_length=1)
    mode: Literal['ENGLISH_STORYTELLING_WITH_CLEAN_ASMR'] = 'ENGLISH_STORYTELLING_WITH_CLEAN_ASMR'
    rights_status: Literal['VERIFIED','UNKNOWN','BLOCKED'] = 'UNKNOWN'
    music_rights_status: Literal['NO_MUSIC','CLEARED','UNKNOWN','BLOCKED'] = 'UNKNOWN'
    # CONFIRMED_ABSENT requires a reviewed absence check, not merely an empty SRT.
    german_speech_status: Literal['CONFIRMED_PRESENT','CONFIRMED_ABSENT','UNCERTAIN'] = 'UNCERTAIN'
    source_german_speech: list[GermanSpeech] = Field(default_factory=list)
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
        if self.german_speech_status == 'UNCERTAIN':
            raise ValueError('speech status must be confirmed before rendering')
        if not self.narration_segments:
            raise ValueError('storytelling mode needs English narration')
        if self.german_speech_status == 'CONFIRMED_PRESENT' and (not self.approved_workshop_stem_path or not self.workshop_stem_qc_passed):
            raise ValueError('CONFIRMED_PRESENT requires full-length approved speech-free workshop stem')
        if self.german_speech_status == 'CONFIRMED_ABSENT' and self.approved_workshop_stem_path:
            raise ValueError('Speech-free clips should use reviewed raw ASMR rather than unnecessary separation')
        if len(set(x.id for x in self.narration_segments)) != len(self.narration_segments):
            raise ValueError('Duplicate narration IDs')
        if len(set(x.id for x in self.source_german_speech)) != len(self.source_german_speech):
            raise ValueError('Duplicate German speech IDs')
        ordered = sorted(self.narration_segments, key=lambda x:x.start)
        for left,right in zip(ordered, ordered[1:]):
            if left.end > right.start + 0.001:
                raise ValueError('English narration windows overlap')
        return self

    def validate_duration(self, duration_sec: float):
        for k in ('source_german_speech','protected_asmr','narration_segments'):
            for s in getattr(self,k):
                if s.end > duration_sec + .075:
                    raise ValueError(f'{k}: out of video timeline')
