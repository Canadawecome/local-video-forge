"""Smart Reframe ASMR Director v1.0.
Master orchestrator for spatial reframe analysis, layout planning, and deliverable export.
Compliant with Local_Video_Forge_Smart_Reframe_ASMR_v1.0_SPEC.md.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from modules.smart_reframe.layout_engine import LayoutEngine
from modules.smart_reframe.roi_analyzer import ROIAnalyzer
from modules.smart_reframe.schemas import ReframePlanV1, ShotReframePlan

logger = logging.getLogger("smart_reframe.director")


class SmartReframeDirector:
    def __init__(
        self,
        target_width: int = 1080,
        target_height: int = 1920,
        keyframes_per_shot: int = 5,
    ):
        self.target_width = target_width
        self.target_height = target_height
        self.analyzer = ROIAnalyzer(keyframes_per_shot=keyframes_per_shot)
        self.layout_engine = LayoutEngine(target_width=target_width, target_height=target_height)

    def plan_reframe_for_edits(
        self,
        source_video: Path | str,
        edits: list[dict[str, Any]],
        output_dir: Path | str,
        job_id: str = "reframe_001",
        source_id: str = "src_001",
    ) -> ReframePlanV1:
        """Executes smart reframe planning for an entire list of EDL edit segments."""
        src_path = Path(source_video).resolve()
        out_folder = Path(output_dir).resolve()
        out_folder.mkdir(parents=True, exist_ok=True)

        sheets_dir = out_folder / "review" / "shot_contact_sheets"
        sheets_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"=== SMART REFRAME ASMR v1.0 START: {len(edits)} shots for {src_path.name} ===")

        shot_plans: list[ShotReframePlan] = []
        crop_keyframes_export: dict[str, Any] = {}

        for idx, edit in enumerate(edits, 1):
            edit_id = edit.get("edit_id", f"e{idx:03d}")
            shot_id = f"shot_{idx:03d}"
            stage_name = edit.get("stage", edit.get("stage_name", "CRAFT_ACTION"))
            start_sec = edit.get("source_start_ms", 0) / 1000.0
            end_sec = edit.get("source_end_ms", 1000) / 1000.0

            logger.info(f"[{idx}/{len(edits)}] Analyzing {shot_id} ({stage_name}): {start_sec:.2f}s -> {end_sec:.2f}s...")
            analysis = self.analyzer.analyze_shot(
                video_path=src_path,
                start_sec=start_sec,
                end_sec=end_sec,
                shot_id=shot_id,
                stage_name=stage_name,
            )

            shot_plan = self.layout_engine.plan_shot_layout(
                analysis=analysis,
                edit_id=edit_id,
                stage_name=stage_name,
            )
            shot_plans.append(shot_plan)

            # Record crop keyframes
            crop_keyframes_export[shot_id] = [
                kf.model_dump() for kf in shot_plan.keyframes
            ]

            # Save contact sheet for QA visual inspection
            if analysis.keyframe_images:
                self._save_contact_sheet(
                    images=analysis.keyframe_images,
                    out_path=sheets_dir / f"{shot_id}_contact.jpg",
                    shot_plan=shot_plan,
                )

            logger.info(
                f"[{idx}/{len(edits)}] {shot_id} -> {shot_plan.layout.value} | "
                f"Confidence: {shot_plan.confidence:.2f} | Reason: {shot_plan.reason}"
            )

        master_plan = ReframePlanV1(
            job_id=job_id,
            source_id=source_id,
            output_dimensions={"width": self.target_width, "height": self.target_height, "display_aspect": "9:16"},
            profile="ASMR_METALCRAFT",
            shots=shot_plans,
        )

        # Export deliverables per SPEC Section 2
        layouts_dir = out_folder / "layouts"
        layouts_dir.mkdir(parents=True, exist_ok=True)

        plan_path = layouts_dir / "reframe_plan.v1.json"
        plan_path.write_text(master_plan.model_dump_json(indent=2), encoding="utf-8")

        keyframes_path = layouts_dir / "crop_keyframes.v1.json"
        keyframes_path.write_text(json.dumps(crop_keyframes_export, indent=2), encoding="utf-8")

        logger.info(f"SMART REFRAME ASMR v1.0 PLAN COMPLETE: {plan_path}")
        return master_plan

    def _save_contact_sheet(
        self,
        images: list[np.ndarray],
        out_path: Path,
        shot_plan: ShotReframePlan,
    ) -> None:
        """Saves a multi-frame contact sheet showing ROI bounding box and layout selection."""
        try:
            resized = []
            target_h = 240
            for img in images[:5]:
                h, w = img.shape[:2]
                rw = int(round(w * target_h / h))
                rimg = cv2.resize(img, (rw, target_h))

                # Draw ROI box if crop
                if shot_plan.active_roi and shot_plan.layout != "WIDE_PRESERVE":
                    rx, ry, r_w, r_h = shot_plan.active_roi.bbox_norm
                    x1 = int(round(rx * rw))
                    y1 = int(round(ry * target_h))
                    x2 = int(round((rx + r_w) * rw))
                    y2 = int(round((ry + r_h) * target_h))
                    cv2.rectangle(rimg, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # Draw layout label
                cv2.putText(
                    rimg,
                    f"{shot_plan.layout.value}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                )
                resized.append(rimg)

            if resized:
                sheet = np.hstack(resized)
                cv2.imwrite(str(out_path), sheet)
        except Exception as e:
            logger.warning(f"Could not save contact sheet to {out_path}: {e}")
