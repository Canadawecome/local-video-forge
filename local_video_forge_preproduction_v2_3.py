"""Optional pre-production contracts for Local Video Forge v2.3.

Inputs are evidence supplied/observed through compliant means; this module
neither scrapes platforms nor predicts virality or validates publishing rights.
Use alongside local_video_forge_schemas_v2_2.py for render-time contracts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrendSignal(StrictModel):
    signal_id: str = Field(min_length=1)
    source_platform: Literal["tiktok", "youtube", "manual"]
    post_url: str = Field(min_length=8)
    topic_de: str = Field(min_length=2)
    observed_at: datetime
    published_at: datetime | None = None
    creator_handle: str | None = None
    follower_count: int | None = Field(default=None, ge=0)
    view_count: int | None = Field(default=None, ge=0)
    median_recent_views: int | None = Field(default=None, gt=0)
    confidence: Literal["LOW", "REVIEW", "HIGH"] = "LOW"
    provenance_note: str | None = None

    @model_validator(mode="after")
    def ensure_time_order(self):
        if self.published_at and self.published_at > self.observed_at:
            raise ValueError("published_at cannot be after observed_at")
        return self

    @property
    def simple_outlier(self) -> float | None:
        if self.view_count is None or self.follower_count is None:
            return None
        return self.view_count / max(self.follower_count, 1)

    @property
    def baseline_ratio(self) -> float | None:
        if self.view_count is None or self.median_recent_views is None:
            return None
        return self.view_count / self.median_recent_views


class MatchEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    kind: Literal["creator_cross_link", "object_match", "shot_match", "timeline_match", "manual_review"]
    detail: str = Field(min_length=8)


class SourceMatch(StrictModel):
    tiktok_url: str
    youtube_url: str
    same_creator: bool
    same_project: bool | None = None
    evidence: list[MatchEvidence] = Field(default_factory=list)
    status: Literal["CONFIRMED", "NEEDS_REVIEW", "NO_MATCH"] = "NEEDS_REVIEW"
    reviewed_by: str | None = None

    @model_validator(mode="after")
    def check_match(self):
        if self.status == "CONFIRMED":
            if not (self.same_creator and self.same_project):
                raise ValueError("confirmed requires same creator AND same project")
            if not self.evidence or not self.reviewed_by:
                raise ValueError("confirmed requires evidence and reviewer")
        if self.status == "NO_MATCH" and self.same_project is True:
            raise ValueError("NO_MATCH inconsistent with same_project=True")
        return self


class OpportunityAxes(StrictModel):
    visual_hook: float = Field(ge=0, le=5)
    story_arc: float = Field(ge=0, le=5)
    authentic_asmr: float = Field(ge=0, le=5)
    vertical_crop: float = Field(ge=0, le=5)
    market_signal: float = Field(ge=0, le=5)

    @property
    def score_100(self) -> float:
        weights = (0.25, 0.25, 0.20, 0.15, 0.15)
        vals = (self.visual_hook, self.story_arc, self.authentic_asmr,
                self.vertical_crop, self.market_signal)
        return round(sum(x / 5 * 100 * w for x, w in zip(vals, weights)), 2)


class ReplayPeak(StrictModel):
    at_sec: float = Field(ge=0)
    note: str | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"


class ProtectedAsmrInterval(StrictModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    reason: str = Field(min_length=3)

    @model_validator(mode="after")
    def validate_order(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("ASMR end must exceed start")
        return self


class HookOption(StrictModel):
    hook_id: str = Field(min_length=1)
    kind: Literal["RESULT_FIRST", "ACTION_FIRST", "TECHNICAL_CURIOSITY"]
    source_asset_id: str
    source_in: float = Field(ge=0)
    source_out: float = Field(gt=0)
    proposed_line_en: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    human_approved: bool = False

    @model_validator(mode="after")
    def validate_time(self):
        if self.source_out <= self.source_in:
            raise ValueError("hook source_out must exceed source_in")
        if self.proposed_line_en and not self.evidence_refs:
            raise ValueError("spoken factual hook needs evidence references")
        return self


class StoryBeat(StrictModel):
    beat_id: str = Field(min_length=1)
    role: Literal["HOOK", "CONTEXT", "PROCESS", "PAYOFF", "ENDING"]
    source_asset_ids: list[str] = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = Field(min_length=3)


class PreproductionPlan(StrictModel):
    schema_version: Literal["2.3"] = "2.3"
    entry_mode: Literal["DIRECT_URL", "DISCOVERY_ASSISTED"]
    youtube_url: str
    source_match: SourceMatch | None = None
    trend_signals: list[TrendSignal] = Field(default_factory=list)
    opportunity_axes: OpportunityAxes | None = None
    manual_replay_peaks: list[ReplayPeak] = Field(default_factory=list)
    hook_options: list[HookOption] = Field(default_factory=list)
    selected_hook_id: str | None = None
    protected_asmr_intervals: list[ProtectedAsmrInterval] = Field(default_factory=list)
    story_beats: list[StoryBeat] = Field(default_factory=list)
    rights_verified: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def validate_preproduction(self):
        if self.entry_mode == "DISCOVERY_ASSISTED":
            if not self.source_match or self.source_match.status != "CONFIRMED":
                raise ValueError("discovery-assisted requires confirmed same-project match")
            if self.source_match.youtube_url != self.youtube_url:
                raise ValueError("source match URL differs from project URL")
        if self.selected_hook_id:
            opts = {h.hook_id: h for h in self.hook_options}
            if len(opts) != len(self.hook_options):
                raise ValueError("duplicate hook IDs")
            if self.selected_hook_id not in opts:
                raise ValueError("selected hook not in hook options")
            if not opts[self.selected_hook_id].human_approved:
                raise ValueError("selected hook requires human approval")
        if any(a.end_sec <= a.start_sec for a in self.protected_asmr_intervals):
            raise ValueError("invalid protected ASMR interval")
        return self

    def ready_for_paid_pipeline(self) -> bool:
        """True means editorial/rights flags are present, not legal certification."""
        return self.rights_verified and (self.entry_mode == "DIRECT_URL" or
            self.source_match is not None and self.source_match.status == "CONFIRMED")


if __name__ == "__main__":
    from datetime import timezone
    signal = TrendSignal(
        signal_id="sig-1", source_platform="tiktok",
        post_url="https://www.tiktok.com/@example/video/1234",
        topic_de="Schmiedekunst", observed_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
        follower_count=2500, view_count=100000, median_recent_views=8000,
    )
    assert signal.simple_outlier == 40.0
    assert signal.baseline_ratio == 12.5
    axes = OpportunityAxes(visual_hook=4, story_arc=5, authentic_asmr=5,
                           vertical_crop=4, market_signal=3)
    assert 0 <= axes.score_100 <= 100
    p = PreproductionPlan(entry_mode="DIRECT_URL",
                          youtube_url="https://www.youtube.com/watch?v=example",
                          rights_verified=True)
    assert p.ready_for_paid_pipeline()
    print("Preproduction schema smoke tests passed")
