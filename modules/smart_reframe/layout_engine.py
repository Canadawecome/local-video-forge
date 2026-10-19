"""Layout Engine for Smart Reframe ASMR v1.0.
Implements normative selection between STATIC_CROP, DYNAMIC_CROP, and WIDE_PRESERVE.
Calculates crop windows and generates deterministic FFmpeg filtergraphs.
"""
from __future__ import annotations

import logging
from typing import Any

from modules.smart_reframe.roi_analyzer import ShotAnalysisResult
from modules.smart_reframe.schemas import (
    CropWindowPx,
    ReframeLayoutType,
    ShotCropKeyframe,
    ShotReframePlan,
    WidePreserveStyle,
)

logger = logging.getLogger("smart_reframe.layout_engine")


class LayoutEngine:
    def __init__(
        self,
        target_width: int = 1080,
        target_height: int = 1920,
        max_crop_speed_ratio: float = 0.12,  # 0.12 * source_width / sec
    ):
        self.target_width = target_width
        self.target_height = target_height
        self.max_crop_speed_ratio = max_crop_speed_ratio

    def plan_shot_layout(
        self,
        analysis: ShotAnalysisResult,
        edit_id: str = "e001",
        stage_name: str = "CRAFT_ACTION",
    ) -> ShotReframePlan:
        """Determines optimal layout and generates exact FFmpeg filter for this shot."""
        src_w = analysis.source_width
        src_h = analysis.source_height
        duration = max(0.5, analysis.end_sec - analysis.start_sec)

        # 9:16 crop width for source height
        # Ensure even pixel dimensions
        crop_w = int(round(src_h * 9.0 / 16.0))
        if crop_w % 2 != 0:
            crop_w += 1
        crop_h = src_h
        max_x = max(0, src_w - crop_w)

        # Mode 1: WIDE_PRESERVE
        if analysis.is_wide_object:
            layout_type = ReframeLayoutType.WIDE_PRESERVE
            reason = f"Stage {stage_name}: Workpiece or reveal exceeds 9:16 safe bounds; preserved full width with blurred background"
            
            # Filter graph for WIDE_PRESERVE (BLUR_BG)
            # 1. Scale background to fill 1080x1920, boxblur, dim
            # 2. Scale foreground to fit 1080 width, maintain 16:9 ratio (1080x608)
            # 3. Overlay in vertical center
            fg_h = int(round(self.target_width * src_h / src_w))
            if fg_h % 2 != 0:
                fg_h += 1

            vf = (
                f"split[bg][fg];"
                f"[bg]scale={self.target_width}:{self.target_height}:force_original_aspect_ratio=increase,"
                f"crop={self.target_width}:{self.target_height},"
                f"boxblur=25:5,"
                f"eq=brightness=-0.15[bg_blur];"
                f"[fg]scale={self.target_width}:{fg_h}:flags=lanczos[fg_scaled];"
                f"[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2,"
                f"setsar=1"
            )

            plan = ShotReframePlan(
                shot_id=analysis.shot_id,
                edit_id=edit_id,
                stage_name=stage_name,
                start_sec=analysis.start_sec,
                end_sec=analysis.end_sec,
                duration_sec=duration,
                semantic_category=stage_name,
                layout=layout_type,
                wide_preserve_style=WidePreserveStyle.BLUR_BG,
                reason=reason,
                confidence=0.92,
                review_required=False,
                active_roi=analysis.roi,
                crop_box_start=None,
                crop_box_end=None,
                ffmpeg_filter=vf,
                keyframes=[
                    ShotCropKeyframe(
                        pts_sec=analysis.start_sec,
                        type="WIDE_PRESERVE",
                        wide_style=WidePreserveStyle.BLUR_BG,
                        layout_type=layout_type,
                    ),
                    ShotCropKeyframe(
                        pts_sec=analysis.end_sec,
                        type="WIDE_PRESERVE",
                        wide_style=WidePreserveStyle.BLUR_BG,
                        layout_type=layout_type,
                    ),
                ]
            )
            return plan

        # Mode 2: DYNAMIC_CROP
        if analysis.is_drifting:
            layout_type = ReframeLayoutType.DYNAMIC_CROP
            
            # Target center coordinates
            start_target_px = analysis.start_center_x * src_w
            end_target_px = analysis.end_center_x * src_w

            # Desired start and end crop X
            desired_start_x = int(round(start_target_px - crop_w / 2.0))
            desired_end_x = int(round(end_target_px - crop_w / 2.0))

            # Clamp desired positions to source boundary
            x_start = max(0, min(max_x, desired_start_x))
            x_end = max(0, min(max_x, desired_end_x))

            # Velocity limit: max allowable shift over duration
            max_travel_px = int(round(self.max_crop_speed_ratio * src_w * duration))
            actual_travel = x_end - x_start
            if abs(actual_travel) > max_travel_px:
                sign = 1 if actual_travel > 0 else -1
                x_end = x_start + sign * max_travel_px
                x_end = max(0, min(max_x, x_end))

            reason = f"Stage {stage_name}: Tool action drifts across frame; smoothed dynamic pan from X={x_start} to X={x_end}"

            # Dynamic FFmpeg crop expression:
            # X(t) = x_start + (x_end - x_start) * (t / duration)
            delta_x = x_end - x_start
            x_expr = f"{x_start}+{delta_x}*t/{duration:.3f}"

            vf = (
                f"crop={crop_w}:{crop_h}:'{x_expr}':0,"
                f"scale={self.target_width}:{self.target_height}:flags=lanczos,"
                f"setsar=1"
            )

            box_start = CropWindowPx(x=x_start, y=0, w=crop_w, h=crop_h)
            box_end = CropWindowPx(x=x_end, y=0, w=crop_w, h=crop_h)

            plan = ShotReframePlan(
                shot_id=analysis.shot_id,
                edit_id=edit_id,
                stage_name=stage_name,
                start_sec=analysis.start_sec,
                end_sec=analysis.end_sec,
                duration_sec=duration,
                semantic_category=stage_name,
                layout=layout_type,
                reason=reason,
                confidence=0.88,
                review_required=False,
                active_roi=analysis.roi,
                crop_box_start=box_start,
                crop_box_end=box_end,
                ffmpeg_filter=vf,
                keyframes=[
                    ShotCropKeyframe(
                        pts_sec=analysis.start_sec,
                        type="CROP",
                        crop_px=box_start,
                        layout_type=layout_type,
                    ),
                    ShotCropKeyframe(
                        pts_sec=analysis.end_sec,
                        type="CROP",
                        crop_px=box_end,
                        layout_type=layout_type,
                    ),
                ]
            )
            return plan

        # Mode 3: STATIC_CROP (Stable ROI anchoring)
        layout_type = ReframeLayoutType.STATIC_CROP
        target_center_px = analysis.median_center_x * src_w
        desired_x = int(round(target_center_px - crop_w / 2.0))
        x_static = max(0, min(max_x, desired_x))

        reason = f"Stage {stage_name}: Stable active contact zone anchored at X={x_static} (center={analysis.median_center_x:.2f})"

        vf = (
            f"crop={crop_w}:{crop_h}:{x_static}:0,"
            f"scale={self.target_width}:{self.target_height}:flags=lanczos,"
            f"setsar=1"
        )

        box_static = CropWindowPx(x=x_static, y=0, w=crop_w, h=crop_h)

        plan = ShotReframePlan(
            shot_id=analysis.shot_id,
            edit_id=edit_id,
            stage_name=stage_name,
            start_sec=analysis.start_sec,
            end_sec=analysis.end_sec,
            duration_sec=duration,
            semantic_category=stage_name,
            layout=layout_type,
            reason=reason,
            confidence=0.95,
            review_required=False,
            active_roi=analysis.roi,
            crop_box_start=box_static,
            crop_box_end=box_static,
            ffmpeg_filter=vf,
            keyframes=[
                ShotCropKeyframe(
                    pts_sec=analysis.start_sec,
                    type="CROP",
                    crop_px=box_static,
                    layout_type=layout_type,
                ),
            ]
        )
        return plan
