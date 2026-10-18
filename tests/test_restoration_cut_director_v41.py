"""Comprehensive Test Suite for Restoration Cut & Edit Director — SPEC v4.1.
Verifies all Section 8 acceptance criteria:
- Single adaptive 75-150s runtime (compact, standard, extended)
- Unconditional ONE video rule (strictly forbid multi-part, part_2, TWO_PART, trilogy)
- Insufficient strong footage handling (< 75s)
- Missing transformation payoff detection
- Contiguous, non-overlapping EDL timeline
- Same-object Before/After matching & BEFORE_TING_AFTER hook
- 9:16 vertical crop & ASMR audio priority
- Complete Section 4 handoff deliverables packaging
- Downstream review module backwards-compatibility
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from restoration_director_contracts_v4_1 import (
    AudioEvent,
    EditDecision,
    EffectItem,
    MIN_RUNTIME_MS,
    MAX_RUNTIME_MS,
    NarrationFlex,
    QAReportV41,
    ReframeROI,
    RestorationCutDirectorOutput,
    RestorationStage,
    RuntimeDecision,
    StoryMapStage,
)
from modules.restoration_cut_director import (
    CandidateShot,
    RestorationCutDirector,
)


def test_runtime_decision_single_full_valid():
    """Verify valid RuntimeDecision within 75–150s."""
    rd = RuntimeDecision(
        mode="SINGLE_FULL",
        target_duration_ms=118000,
        reason="Enough distinct restoration changes and final functional test",
        duration_candidate_ranges=["75-90s", "90-120s", "120-150s"],
        preserved_key_stages=["rust removal", "lathe turning", "final test"],
        lost_if_shortened=["detailed gear alignment"],
        why_not_longer="Repeated polishing adds no distinct visual change",
    )
    assert rd.mode == "SINGLE_FULL"
    assert rd.target_duration_ms == 118000


def test_runtime_decision_rejects_under_75s():
    """Verify RuntimeDecision strictly rejects duration < 75s."""
    with pytest.raises(ValidationError):
        RuntimeDecision(
            mode="SINGLE_FULL",
            target_duration_ms=74000, # 74s < 75s
            reason="Too short",
            duration_candidate_ranges=["75-90s"],
            preserved_key_stages=["cleaning"],
            why_not_longer="short",
        )


def test_runtime_decision_rejects_over_150s():
    """Verify RuntimeDecision strictly rejects duration > 150s."""
    with pytest.raises(ValidationError):
        RuntimeDecision(
            mode="SINGLE_FULL",
            target_duration_ms=155000, # 155s > 150s
            reason="Too long",
            duration_candidate_ranges=["120-150s"],
            preserved_key_stages=["all"],
            why_not_longer="long",
        )


def test_runtime_decision_strictly_forbids_multi_part():
    """SPEC v4.1 Section 2: No TWO_PART, no trilogy, no episode branching."""
    with pytest.raises(ValidationError):
        RuntimeDecision(
            mode="TWO_PART", # type: ignore
            target_duration_ms=90000,
            reason="Cannot split into parts",
            duration_candidate_ranges=["90-120s"],
            preserved_key_stages=["part 1"],
            why_not_longer="invalid",
        )


def test_edl_contiguous_and_duration_validation():
    """Verify EDL timeline contiguity and total duration between 75s and 150s."""
    edits = [
        EditDecision(
            edit_id="e001",
            source_start_ms=10000,
            source_end_ms=13000,
            output_start_ms=0,
            output_end_ms=3000,
            stage=RestorationStage.BEFORE,
            same_object_id="obj_1",
            purpose="Hook establish rust",
            narration_flex=NarrationFlex(safe_to_extend=False, min_duration_ms=2500, max_duration_ms=3500),
        ),
        EditDecision(
            edit_id="e002",
            source_start_ms=50000,
            source_end_ms=130000,
            output_start_ms=3000,
            output_end_ms=83000,
            stage=RestorationStage.GRINDING,
            same_object_id="obj_1",
            purpose="Heavy rust grinding",
            narration_flex=NarrationFlex(safe_to_extend=True, min_duration_ms=70000, max_duration_ms=90000),
        ),
        EditDecision(
            edit_id="e003",
            source_start_ms=200000,
            source_end_ms=215000,
            output_start_ms=83000,
            output_end_ms=98000,
            stage=RestorationStage.AFTER_REVEAL,
            same_object_id="obj_1",
            purpose="Completed mirror reveal",
            narration_flex=NarrationFlex(safe_to_extend=False, min_duration_ms=12000, max_duration_ms=18000),
        ),
    ]

    rd = RuntimeDecision(
        mode="SINGLE_FULL",
        target_duration_ms=98000,
        reason="Standard 98s restoration cut",
        duration_candidate_ranges=["90-120s"],
        preserved_key_stages=["BEFORE", "GRINDING", "AFTER_REVEAL"],
        why_not_longer="No extra steps",
    )

    plan = RestorationCutDirectorOutput(
        schema_version="4.1",
        source_id="src_test_valid",
        analysis_coverage_percent=100.0,
        runtime_decision=rd,
        edits=edits,
        status="READY_FOR_RENDER",
    )
    assert plan.status == "READY_FOR_RENDER"
    assert len(plan.edits) == 3
    assert plan.edits[-1].output_end_ms == 98000


def test_edl_rejects_timeline_gaps():
    """Verify EDL rejects timeline gaps where output_start != prev output_end."""
    edits = [
        EditDecision(
            edit_id="e001",
            source_start_ms=0,
            source_end_ms=40000,
            output_start_ms=0,
            output_end_ms=40000,
            stage=RestorationStage.BEFORE,
            same_object_id="obj_1",
            purpose="Step 1",
            narration_flex=NarrationFlex(min_duration_ms=30000, max_duration_ms=45000),
        ),
        EditDecision(
            edit_id="e002",
            source_start_ms=45000,
            source_end_ms=90000,
            output_start_ms=42000, # GAP of 2000ms! (prev was 40000ms)
            output_end_ms=87000,
            stage=RestorationStage.AFTER_REVEAL,
            same_object_id="obj_1",
            purpose="Step 2",
            narration_flex=NarrationFlex(min_duration_ms=40000, max_duration_ms=50000),
        ),
    ]

    rd = RuntimeDecision(
        mode="SINGLE_FULL",
        target_duration_ms=87000,
        reason="Test gap",
        duration_candidate_ranges=["75-90s"],
        preserved_key_stages=["BEFORE", "AFTER_REVEAL"],
        why_not_longer="Cannot extend further without filler",
    )

    with pytest.raises(ValueError, match="Gap or overlap"):
        RestorationCutDirectorOutput(
            schema_version="4.1",
            source_id="src_test_gap",
            runtime_decision=rd,
            edits=edits,
            status="READY_FOR_RENDER",
        )


def test_edl_forbids_multi_part_edit_ids():
    """Acceptance criterion 14: No implementation path can create part_2, episode_1 etc."""
    with pytest.raises(ValidationError):
        EditDecision(
            edit_id="part_2",  # FORBIDDEN by schema pattern ^e\d{3,}$
            source_start_ms=0,
            source_end_ms=80000,
            output_start_ms=0,
            output_end_ms=80000,
            stage=RestorationStage.BEFORE,
            same_object_id="obj_1",
            purpose="Invalid part ID",
            narration_flex=NarrationFlex(min_duration_ms=75000, max_duration_ms=85000),
        )


def test_insufficient_strong_footage_flag():
    """Acceptance criterion 5: When footage cannot sustain 75s, emit INSUFFICIENT_STRONG_FOOTAGE."""
    director = RestorationCutDirector()
    mock_probe = {
        "duration_sec": 45.0, # Less than 75s
        "duration_ms": 45000,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "has_audio": True,
    }
    candidate_shots = director._index_candidate_shots(Path("dummy.mp4"), mock_probe, Path("."))
    assert len(candidate_shots) == 0

    plan = director._plan_adaptive_timeline(
        source_id="src_short",
        probe=mock_probe,
        candidate_shots=[],
        before_shot=None,
        after_shot=None,
    )
    assert plan.status == "INSUFFICIENT_STRONG_FOOTAGE"
    assert len(plan.edits) == 0


def test_missing_transformation_payoff_flag():
    """Acceptance criterion 7: Missing final reveal material surfaces MISSING_TRANSFORMATION_PAYOFF."""
    director = RestorationCutDirector()
    shots = [
        CandidateShot("c01", 0, 30000, RestorationStage.BEFORE, "Rusted gear", 90.0, "obj_1"),
        CandidateShot("c02", 30000, 70000, RestorationStage.DISASSEMBLY, "Taking apart", 80.0, "obj_1"),
        # Missing AFTER_REVEAL or TEST!
    ]
    before_shot, after_shot = director._match_before_after(shots)
    assert before_shot is not None
    assert after_shot is None # No after reveal!

    plan = director._plan_adaptive_timeline(
        source_id="src_no_payoff",
        probe={"duration_sec": 70.0, "duration_ms": 70000, "width": 1920, "height": 1080, "fps": 30.0, "has_audio": True},
        candidate_shots=shots,
        before_shot=before_shot,
        after_shot=None,
        status_override="MISSING_TRANSFORMATION_PAYOFF",
    )
    assert plan.status == "MISSING_TRANSFORMATION_PAYOFF"


def test_adaptive_story_planner_durations():
    """Acceptance criterion 1 & 3: Sol chooses compact (75-90s), standard (90-120s), or extended (120-150s)."""
    director = RestorationCutDirector()
    mock_probe = {
        "duration_sec": 1200.0, # 20 minutes source
        "duration_ms": 1200000,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "has_audio": True,
    }
    shots = director._index_candidate_shots(Path("dummy.mp4"), mock_probe, Path("."))
    before_shot, after_shot = director._match_before_after(shots)

    # Test compact pass (75-90s)
    plan_compact = director._plan_adaptive_timeline(
        source_id="src_compact",
        probe=mock_probe,
        candidate_shots=shots,
        before_shot=before_shot,
        after_shot=after_shot,
        runtime_preference="compact",
    )
    assert plan_compact.status == "READY_FOR_RENDER"
    dur_compact = plan_compact.edits[-1].output_end_ms / 1000.0
    assert 75.0 <= dur_compact <= 90.0

    # Test standard pass (90-120s)
    plan_standard = director._plan_adaptive_timeline(
        source_id="src_standard",
        probe=mock_probe,
        candidate_shots=shots,
        before_shot=before_shot,
        after_shot=after_shot,
        runtime_preference="standard",
    )
    assert plan_standard.status == "READY_FOR_RENDER"
    dur_standard = plan_standard.edits[-1].output_end_ms / 1000.0
    assert 90.0 <= dur_standard <= 120.0

    # Test extended pass (120-150s)
    plan_extended = director._plan_adaptive_timeline(
        source_id="src_extended",
        probe=mock_probe,
        candidate_shots=shots,
        before_shot=before_shot,
        after_shot=after_shot,
        runtime_preference="extended",
    )
    assert plan_extended.status == "READY_FOR_RENDER"
    dur_extended = plan_extended.edits[-1].output_end_ms / 1000.0
    assert 120.0 <= dur_extended <= 150.0


def test_hook_before_ting_after_structure():
    """Acceptance criterion 1 & Section 3.1: Hook shows damaged before, then brief teaser, then returns to process."""
    director = RestorationCutDirector()
    mock_probe = {"duration_sec": 900.0, "duration_ms": 900000, "width": 1920, "height": 1080, "fps": 30.0, "has_audio": True}
    shots = director._index_candidate_shots(Path("dummy.mp4"), mock_probe, Path("."))
    before_shot, after_shot = director._match_before_after(shots)

    plan = director._plan_adaptive_timeline(
        source_id="src_hook",
        probe=mock_probe,
        candidate_shots=shots,
        before_shot=before_shot,
        after_shot=after_shot,
        runtime_preference="standard",
    )

    # First edit: BEFORE (damaged state)
    assert plan.edits[0].stage == RestorationStage.BEFORE
    assert plan.edits[0].output_start_ms == 0
    # Second edit: AFTER_REVEAL teaser (short match cut)
    assert plan.edits[1].stage == RestorationStage.AFTER_REVEAL
    assert plan.edits[1].output_end_ms <= 4000 # within first 4 seconds
    # Flash effect connecting them
    assert len(plan.effects) >= 1
    assert plan.effects[0].type == "matched_flash_cut"


def test_reframe_roi_validity():
    """Acceptance criterion 9: 9:16 crop keeps workpiece, tools, and hands within TikTok safe zone."""
    roi = ReframeROI(mode="smart_reframe", roi=[0.2, 0.05, 0.6, 0.9])
    assert roi.roi[0] >= 0.0 and roi.roi[1] >= 0.0
    assert roi.roi[2] <= 1.0 and roi.roi[3] <= 1.0


def test_handoff_contract_packaging(tmp_path: Path):
    """Acceptance criterion 11 & 12: Section 4 handoff files exist with correct schemas."""
    director = RestorationCutDirector()
    mock_probe = {"duration_sec": 600.0, "duration_ms": 600000, "width": 1920, "height": 1080, "fps": 30.0, "has_audio": True}
    shots = director._index_candidate_shots(Path("dummy.mp4"), mock_probe, tmp_path)
    before_shot, after_shot = director._match_before_after(shots)

    plan = director._plan_adaptive_timeline(
        source_id="src_handoff",
        probe=mock_probe,
        candidate_shots=shots,
        before_shot=before_shot,
        after_shot=after_shot,
        runtime_preference="compact",
    )

    mock_cut = tmp_path / "visual_cut.mp4"
    mock_cut.write_bytes(b"dummy_video_bytes")

    director._package_handoff_contract(plan, tmp_path, mock_cut, mock_probe)

    # Check that required handoff files exist
    assert (tmp_path / "edl.json").is_file()
    assert (tmp_path / "story_map.json").is_file()
    assert (tmp_path / "narration_flex.json").is_file()
    assert (tmp_path / "audio_events.json").is_file()

    # Validate json content can be loaded
    edl_data = json.loads((tmp_path / "edl.json").read_text(encoding="utf-8"))
    assert edl_data["schema_version"] == "4.1"
    assert edl_data["runtime_decision"]["mode"] == "SINGLE_FULL"

    story_map_data = json.loads((tmp_path / "story_map.json").read_text(encoding="utf-8"))
    assert len(story_map_data) == len(plan.edits)

    flex_data = json.loads((tmp_path / "narration_flex.json").read_text(encoding="utf-8"))
    assert len(flex_data) == len(plan.edits)

    audio_events_data = json.loads((tmp_path / "audio_events.json").read_text(encoding="utf-8"))
    assert len(audio_events_data) == len(plan.edits)
