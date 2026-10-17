"""Contract for the Local Video Forge v2.7 default hybrid dubbing / ASMR mode."""
from __future__ import annotations
from enum import Enum
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Interval(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def check_order(self):
        if self.end <= self.start:
            raise ValueError("Interval end must exceed start")
        return self


class GermanSpeech(Interval):
    id: str = Field(min_length=1)
    text_de: str = ""
    evidence_ref: str | None = None


class ProtectedASMR(Interval):
    kind: Literal["hammer", "grinding", "saw", "forge", "machine", "other"] = "hammer"


class VoiceSegment(Interval):
    id: str = Field(min_length=1)
    kind: Literal["dub", "commentary"]
    text_en: str = Field(min_length=1)
    speech_ids: list[str] = Field(default_factory=list)
    audio_path: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class AudioSettings(StrictModel):
    german_speech_duck_db: float = Field(default=-24.0, ge=-60, le=-12)
    commentary_duck_db: float = Field(default=0.0, ge=-18, le=0)  # Legacy only: v2.10 renderer ignores ducking to protect ASMR
    duck_attack_ms: int = Field(default=65, ge=10, le=500)
    duck_release_ms: int = Field(default=145, ge=10, le=900)
    voice_gain_db: float = Field(default=0, ge=-12, le=6)
    peak_ceiling_dbfs: float = Field(default=-1.0, ge=-6, le=-0.3)
    max_tts_overrun_sec: float = Field(default=0.10, ge=0, le=0.2)


class HybridClipPlan(StrictModel):
    schema_version: Literal["2.7"] = "2.7"
    clip_uid: str = Field(min_length=1)
    mode: Literal["HYBRID_SELECTIVE_DUB_ASMR_STORY"] = "HYBRID_SELECTIVE_DUB_ASMR_STORY"
    rights_status: Literal["VERIFIED", "BLOCKED", "UNKNOWN"] = "UNKNOWN"
    music_rights_status: Literal["NO_MUSIC", "CLEARED", "UNKNOWN", "BLOCKED"] = "UNKNOWN"
    source_german_speech: list[GermanSpeech] = Field(default_factory=list)
    protected_asmr: list[ProtectedASMR] = Field(default_factory=list)
    voice_segments: list[VoiceSegment] = Field(default_factory=list)
    # Only provide when a real speech-separation step has been QC-approved.
    approved_workshop_stem_path: str | None = None
    workshop_stem_qc_passed: bool = False
    settings: AudioSettings = Field(default_factory=AudioSettings)
    voice_id: str = "QIhD5ivPGEoYZQDocuHI"
    tts_model_id: str = "eleven_multilingual_v2"

    @model_validator(mode="after")
    def logical_checks(self):
        if self.rights_status != "VERIFIED":
            raise ValueError("Footage rights must be VERIFIED before rendering")
        if self.music_rights_status not in ("NO_MUSIC", "CLEARED"):
            raise ValueError("Music rights must be NO_MUSIC or CLEARED")
        if not self.voice_segments:
            raise ValueError("Hybrid mode requires at least one English voice segment")
        ids = [s.id for s in self.source_german_speech]
        vids = [s.id for s in self.voice_segments]
        if len(ids) != len(set(ids)) or len(vids) != len(set(vids)):
            raise ValueError("Duplicate speech/voice segment id")
        if self.approved_workshop_stem_path and not self.workshop_stem_qc_passed:
            raise ValueError("Workshop stem must pass QC before use")
        idset = set(ids)
        mapped = set()
        for v in self.voice_segments:
            if v.kind == "dub":
                if not v.speech_ids:
                    raise ValueError(f"Dub {v.id} has no German speech mapping")
                if set(v.speech_ids) - idset:
                    raise ValueError(f"Dub {v.id} refers to unknown speech ids")
                mapped.update(v.speech_ids)
            elif v.speech_ids:
                raise ValueError(f"Commentary {v.id} cannot map to German speech ids")
        if mapped != idset:
            raise ValueError(f"German speech not mapped to a dub: {sorted(idset - mapped)}")
        # Only with an independently approved speech-free workshop stem can an
        # overlapping German speech + hammer be kept without severe attenuation.
        for s in self.source_german_speech:
            for a in self.protected_asmr:
                overlap = min(s.end, a.end) - max(s.start, a.start)
                if overlap > 0.04 and not self.approved_workshop_stem_path:
                    raise ValueError(
                        f"German speech and protected ASMR overlap ({s.id}): "
                        "needs approved speech-free workshop stem or manual review"
                    )
        # v2.10: English dub can coincide with protected workshop ASMR.
        # Do not mute/duck the workshop bed when English voice is active.
        # Editors should avoid narrating over the strongest impacts where possible,
        # but dubbing during hammer blows must preserve the workshop ambience.
        # Prevent normal voice segments from overlapping one another.
        ordered = sorted(self.voice_segments, key=lambda s: s.start)
        for left, right in zip(ordered, ordered[1:]):
            if left.end > right.start + 0.001:
                raise ValueError(f"Voice windows {left.id} and {right.id} overlap")
        return self

    def validate_duration(self, duration_sec: float):
        for group_name, items in (
            ("source_german_speech", self.source_german_speech),
            ("protected_asmr", self.protected_asmr),
            ("voice_segments", self.voice_segments),
        ):
            for item in items:
                if item.end > duration_sec + 0.075:
                    raise ValueError(f"{group_name}: end {item.end} beyond clip {duration_sec:.3f}s")
