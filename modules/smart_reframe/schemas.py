"""Pydantic schemas for Smart Reframe ASMR v1.0.
Compliant with Local_Video_Forge_Smart_Reframe_ASMR_v1.0_SPEC.md.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class ReframeLayoutType(str, Enum):
    STATIC_CROP = "STATIC_CROP"
    DYNAMIC_CROP = "DYNAMIC_CROP"
    WIDE_PRESERVE = "WIDE_PRESERVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class WidePreserveStyle(str, Enum):
    BLUR_BG = "BLUR_BG"
    SOLID_BG = "SOLID_BG"
    SUBTLE_GRADIENT = "SUBTLE_GRADIENT"


class ROIRegion(BaseModel):
    label: str = "interaction_core"
    # [x, y, w, h] normalized [0, 1]
    bbox_norm: list[float] = Field(default_factory=lambda: [0.2, 0.1, 0.6, 0.8])
    priority: int = 1
    confidence: float = 0.85
    reason: str = "Active tool-workpiece interaction contact point"

    @model_validator(mode="after")
    def validate_bbox(self) -> ROIRegion:
        if len(self.bbox_norm) != 4:
            raise ValueError("bbox_norm must be [x, y, w, h]")
        x, y, w, h = self.bbox_norm
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"bbox coordinates must be in [0, 1], got x={x}, y={y}")
        if w <= 0.0 or h <= 0.0:
            raise ValueError(f"bbox w and h must be positive, got w={w}, h={h}")
        return self


class CropWindowPx(BaseModel):
    x: int
    y: int
    w: int
    h: int
    scale_w: int = 1080
    scale_h: int = 1920


class ShotCropKeyframe(BaseModel):
    pts_sec: float
    type: Literal["CROP", "WIDE_PRESERVE"] = "CROP"
    crop_px: CropWindowPx | None = None
    wide_style: WidePreserveStyle = WidePreserveStyle.BLUR_BG
    layout_type: ReframeLayoutType = ReframeLayoutType.STATIC_CROP


class ShotReframePlan(BaseModel):
    shot_id: str
    edit_id: str
    stage_name: str
    start_sec: float
    end_sec: float
    duration_sec: float
    semantic_category: str = "CRAFT_ACTION"
    layout: ReframeLayoutType = ReframeLayoutType.STATIC_CROP
    wide_preserve_style: WidePreserveStyle = WidePreserveStyle.BLUR_BG
    reason: str = "Keep active contact point centered and stable"
    confidence: float = 0.90
    review_required: bool = False
    active_roi: ROIRegion = Field(default_factory=ROIRegion)
    crop_box_start: CropWindowPx | None = None
    crop_box_end: CropWindowPx | None = None
    ffmpeg_filter: str = ""
    keyframes: list[ShotCropKeyframe] = Field(default_factory=list)


class ReframePlanV1(BaseModel):
    schema_version: str = "1.0"
    job_id: str
    source_id: str
    input_sha256: str = ""
    edl_revision: str = "locked-v1"
    output_dimensions: dict[str, Any] = Field(default_factory=lambda: {"width": 1080, "height": 1920, "display_aspect": "9:16"})
    profile: str = "ASMR_METALCRAFT"
    shots: list[ShotReframePlan] = Field(default_factory=list)
