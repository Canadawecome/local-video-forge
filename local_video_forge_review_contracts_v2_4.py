"""Local Video Forge v2.4: source evidence, audio/music rights, hooks and export QC.

These contracts check data consistency, not legal originality or provider/API availability.
They complement (do not replace) v2.2 render and v2.3 preproduction schemas.
Python 3.11+, Pydantic 2.x. No network calls, downloads or scraping.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TimeSpan(StrictModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)

    @model_validator(mode="after")
    def chronological(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must exceed start_sec")
        return self


class EvidenceItem(StrictModel):
    evidence_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    source_uri: str | None = None
    source_kind: Literal[
        "observed_video", "german_transcript", "author_description",
        "trusted_fact_sheet", "manual_editor_note", "licensed_metadata"
    ]
    observation: str = Field(min_length=3)
    time_range: TimeSpan | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    reviewed_by: str | None = None
    asset_sha256: str | None = None


class ContentClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    kind: Literal["VISUAL", "PROCESS", "TECHNICAL_SPEC", "PRICE_VALUE", "HISTORICAL", "OTHER"]
    text: str = Field(min_length=3)
    evidence_refs: list[str] = Field(default_factory=list)
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "NEEDS_REVIEW"] = "NEEDS_REVIEW"
    reviewer_id: str | None = None

    @model_validator(mode="after")
    def verify_claim(self):
        if self.verdict == "SUPPORTED" and not self.evidence_refs:
            raise ValueError("supported claim must cite evidence")
        if self.kind in {"TECHNICAL_SPEC", "PRICE_VALUE", "HISTORICAL"} and self.verdict == "SUPPORTED" and not self.reviewer_id:
            raise ValueError("technical, value and historical claims require a reviewer")
        return self


class AssetRights(StrictModel):
    asset_id: str = Field(min_length=1)
    asset_kind: Literal["SOURCE_VIDEO", "EMBEDDED_MUSIC", "FOLEY", "VOICEOVER", "IMAGE", "OTHER"]
    rights_holder: str | None = None
    license_status: Literal["VERIFIED", "PENDING", "REJECTED"] = "PENDING"
    proof_path: str | None = None
    territories: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    commercial_use: bool = False
    allowed_transformations: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    verified_by: str | None = None

    @model_validator(mode="after")
    def verify_rights(self):
        if self.license_status == "VERIFIED":
            if not all([self.rights_holder, self.proof_path, self.verified_by]):
                raise ValueError("VERIFIED asset requires holder, proof_path and verifier")
            if not self.territories or not self.platforms:
                raise ValueError("VERIFIED asset must specify territories and platforms")
        return self

    def can_use_commercially(self, now: datetime | None = None, *, territory: str = "US", platform: str = "TikTok") -> bool:
        now = now or datetime.now(timezone.utc)
        if self.expires_at:
            exp = self.expires_at
            if exp.tzinfo is None:
                return False  # a naive expiry is not reliably comparable
            if exp <= now:
                return False
        return (
            self.license_status == "VERIFIED"
            and self.commercial_use
            and territory in self.territories
            and platform in self.platforms
        )


class AudioSegment(StrictModel):
    span: TimeSpan
    labels: list[Literal["WORKSHOP_ASMR", "GERMAN_SPEECH", "MUSIC", "ROOM_TONE", "UNKNOWN"]] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    protected_asmr: bool = False

    @model_validator(mode="after")
    def check_protected(self):
        if self.protected_asmr and "WORKSHOP_ASMR" not in self.labels:
            raise ValueError("protected_asmr segment must include WORKSHOP_ASMR label")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("duplicate audio labels")
        return self


class AudioContentMap(StrictModel):
    asset_id: str
    duration_sec: float = Field(gt=0)
    segments: list[AudioSegment] = Field(default_factory=list)

    @model_validator(mode="after")
    def segments_within_asset(self):
        for item in self.segments:
            if item.span.end_sec > self.duration_sec + 0.05:
                raise ValueError("audio segment exceeds asset duration")
        return self


class MusicRightsReview(StrictModel):
    music_resolution: Literal["NO_MUSIC", "LICENSED", "RESOLVED_WITHOUT_UNLICENSED_MUSIC", "UNRESOLVED"] = "UNRESOLVED"
    music_asset_ids: list[str] = Field(default_factory=list)
    reviewed_by: str | None = None
    notes: str | None = None
    audio_qc_passed: bool = False

    @model_validator(mode="after")
    def resolution_review(self):
        if self.music_resolution in {"NO_MUSIC", "LICENSED", "RESOLVED_WITHOUT_UNLICENSED_MUSIC"}:
            if not self.reviewed_by or not self.audio_qc_passed:
                raise ValueError("resolved music requires reviewer and QC pass")
        if self.music_resolution == "LICENSED" and not self.music_asset_ids:
            raise ValueError("licensed music requires corresponding asset IDs")
        return self


class HookCandidate(StrictModel):
    hook_id: str = Field(min_length=1)
    hook_type: Literal[
        "RESULT_FIRST", "ACTION_FIRST", "TECHNICAL_CURIOSITY",
        "COUNTER_INTUITION", "HIGH_STAKES", "VALUE_IRONY"
    ]
    source_asset_id: str
    source_span: TimeSpan
    suggested_first_line: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    same_project_verified: bool = False
    review_status: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED"] = "NEEDS_REVIEW"
    reviewed_by: str | None = None

    @model_validator(mode="after")
    def hook_review(self):
        if self.suggested_first_line and not self.evidence_refs:
            raise ValueError("hook with spoken factual claim requires evidence")
        if self.hook_type == "RESULT_FIRST" and self.review_status == "APPROVED" and not self.same_project_verified:
            raise ValueError("RESULT_FIRST must verify same-project footage")
        if self.review_status == "APPROVED" and not self.reviewed_by:
            raise ValueError("approved hook requires reviewer")
        return self


class OpusCandidateScore(StrictModel):
    candidate_id: str
    asset_id: str
    action_and_crop: float = Field(ge=0, le=5)
    asmr_quality: float = Field(ge=0, le=5)
    story_feasibility: float = Field(ge=0, le=5)
    clean_plate: float = Field(ge=0, le=5)
    duration_fit: float = Field(ge=0, le=5)
    opus_viral_score: float | None = Field(default=None, ge=0, le=100)
    qc_status: Literal["PASS", "REVIEW", "REJECT"] = "REVIEW"
    reason: str = ""

    @property
    def editing_suitability_score(self) -> float:
        return round(100 * (
            .30 * self.action_and_crop + .30 * self.asmr_quality
            + .20 * self.story_feasibility + .10 * self.clean_plate
            + .10 * self.duration_fit
        ) / 5, 1)


class ExportReview(StrictModel):
    project_id: str
    used_asset_ids: list[str] = Field(min_length=1)
    assets_rights: list[AssetRights] = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    claims: list[ContentClaim] = Field(default_factory=list)
    hooks: list[HookCandidate] = Field(default_factory=list)
    selected_hook_id: str | None = None
    audio_maps: list[AudioContentMap] = Field(default_factory=list)
    music_review: MusicRightsReview
    timeline_qc_passed: bool = False
    render_qc_passed: bool = False
    manual_approved_by: str | None = None
    territory: str = "US"
    platform: str = "TikTok"
    requested_status: Literal["DRAFT", "PUBLISH_READY"] = "DRAFT"

    @model_validator(mode="after")
    def cross_reference(self):
        if len(set(self.used_asset_ids)) != len(self.used_asset_ids):
            raise ValueError("duplicate used asset IDs")
        evidence_index = {e.evidence_id: e for e in self.evidence}
        rights_index = {r.asset_id: r for r in self.assets_rights}
        hooks_index = {h.hook_id: h for h in self.hooks}
        if len(evidence_index) != len(self.evidence) or len(rights_index) != len(self.assets_rights) or len(hooks_index) != len(self.hooks):
            raise ValueError("duplicate evidence, rights or hook IDs")
        if self.selected_hook_id and self.selected_hook_id not in hooks_index:
            raise ValueError("selected hook does not exist")
        for claim in self.claims:
            if any(ref not in evidence_index for ref in claim.evidence_refs):
                raise ValueError(f"claim {claim.claim_id}: unknown evidence")
        for hook in self.hooks:
            if any(ref not in evidence_index for ref in hook.evidence_refs):
                raise ValueError(f"hook {hook.hook_id}: unknown evidence")
            if hook.source_asset_id not in rights_index:
                raise ValueError(f"hook {hook.hook_id}: source asset missing rights review")
        if self.requested_status == "PUBLISH_READY":
            if not self.timeline_qc_passed or not self.render_qc_passed or not self.manual_approved_by:
                raise ValueError("PUBLISH_READY requires timeline QC, render QC and human approval")
            if self.music_review.music_resolution == "UNRESOLVED":
                raise ValueError("PUBLISH_READY impossible while music rights unresolved")
            if self.music_review.music_resolution == "LICENSED":
                if any(not rights_index.get(id_) or not rights_index[id_].can_use_commercially(territory=self.territory, platform=self.platform) for id_ in self.music_review.music_asset_ids):
                    raise ValueError("PUBLISH_READY requires properly licensed music assets")
            if any(not rights_index.get(id_) or not rights_index[id_].can_use_commercially(territory=self.territory, platform=self.platform) for id_ in self.used_asset_ids):
                raise ValueError("PUBLISH_READY requires rights for every used asset")
            if any(c.verdict != "SUPPORTED" for c in self.claims):
                raise ValueError("PUBLISH_READY requires every published claim supported")
            if self.selected_hook_id and hooks_index[self.selected_hook_id].review_status != "APPROVED":
                raise ValueError("PUBLISH_READY requires approved selected hook")
        return self


if __name__ == "__main__":
    from pydantic import ValidationError

    r = AssetRights(
        asset_id="video_01", asset_kind="SOURCE_VIDEO", rights_holder="owner",
        license_status="VERIFIED", proof_path="rights/permission.txt", territories=["US"],
        platforms=["TikTok"], commercial_use=True,
        allowed_transformations=["crop", "dub"], verified_by="editor"
    )
    assert r.can_use_commercially()
    ev = EvidenceItem(evidence_id="ev_01", asset_id="video_01", source_kind="observed_video",
                      observation="hammer strikes steel", confidence="HIGH")
    hook = HookCandidate(hook_id="h1", hook_type="ACTION_FIRST", source_asset_id="video_01",
                         source_span=TimeSpan(start_sec=0, end_sec=2),
                         suggested_first_line="The smith shapes steel with a hammer.",
                         evidence_refs=["ev_01"], review_status="APPROVED", reviewed_by="editor")
    music = MusicRightsReview(music_resolution="NO_MUSIC", reviewed_by="editor", audio_qc_passed=True)
    gate = ExportReview(project_id="p01", used_asset_ids=["video_01"], assets_rights=[r], evidence=[ev],
                        claims=[ContentClaim(claim_id="c1", kind="PROCESS", text="hammer strikes steel",
                                              verdict="SUPPORTED", evidence_refs=["ev_01"])],
                        hooks=[hook], selected_hook_id="h1", music_review=music,
                        timeline_qc_passed=True, render_qc_passed=True,
                        manual_approved_by="editor", requested_status="PUBLISH_READY")
    assert gate.requested_status == "PUBLISH_READY"
    for invalid in [
        {"music_resolution": "UNRESOLVED"},
        {"music_resolution": "NO_MUSIC", "audio_qc_passed": True},
    ]:
        try:
            MusicRightsReview.model_validate(invalid)
        except ValidationError:
            pass
        else:
            if invalid["music_resolution"] != "UNRESOLVED":
                raise AssertionError("expected invalid music review")
    try:
        ExportReview.model_validate({**gate.model_dump(), "claims": [
            {"claim_id": "x", "kind": "PRICE_VALUE", "text": "Sold for $5000", "verdict": "UNSUPPORTED"}
        ]})
    except ValidationError:
        pass
    else:
        raise AssertionError("PUBLISH_READY should reject unsupported claim")
    print("v2.4 review contract smoke tests passed")
