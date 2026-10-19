"""ROI Analyzer for Smart Reframe ASMR v1.0.
Analyzes video shot keyframes using OpenCV motion saliency, edge density, and spatial tracking.
Accurately isolates INTERACTION_CORE (tool-workpiece contact, hands, lathe/grinding contact)
while rejecting outlier flying sparks, and determines optimal framing behavior.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from modules.smart_reframe.schemas import ROIRegion

logger = logging.getLogger("smart_reframe.roi_analyzer")


class ShotAnalysisResult:
    def __init__(
        self,
        shot_id: str,
        start_sec: float,
        end_sec: float,
        source_width: int,
        source_height: int,
        roi: ROIRegion,
        is_wide_object: bool,
        is_drifting: bool,
        drift_distance: float,
        start_center_x: float,
        end_center_x: float,
        median_center_x: float,
        keyframe_images: list[np.ndarray],
    ):
        self.shot_id = shot_id
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.source_width = source_width
        self.source_height = source_height
        self.roi = roi
        self.is_wide_object = is_wide_object
        self.is_drifting = is_drifting
        self.drift_distance = drift_distance
        self.start_center_x = start_center_x
        self.end_center_x = end_center_x
        self.median_center_x = median_center_x
        self.keyframe_images = keyframe_images


class ROIAnalyzer:
    def __init__(self, keyframes_per_shot: int = 5):
        self.keyframes_per_shot = max(3, min(8, keyframes_per_shot))

    def analyze_shot(
        self,
        video_path: Path | str,
        start_sec: float,
        end_sec: float,
        shot_id: str = "shot_001",
        stage_name: str = "CRAFT_ACTION",
    ) -> ShotAnalysisResult:
        """Rapidly samples keyframes using single-seek and extracts INTERACTION_CORE."""
        vpath = str(Path(video_path).resolve())
        cap = cv2.VideoCapture(vpath)
        if not cap.isOpened():
            raise IOError(f"Cannot open video for ROI analysis: {vpath}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        duration = max(0.5, end_sec - start_sec)
        
        # Optimize seek: seek ONCE to start_sec, then read forward
        start_frame = max(0, min(int(start_sec * fps), total_frames - 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        frame_step = max(1, int((duration * fps) / self.keyframes_per_shot))
        frames: list[np.ndarray] = []

        for _ in range(self.keyframes_per_shot):
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            frames.append(frame)
            # Skip frames to next sample point
            for _ in range(frame_step - 1):
                cap.grab()

        cap.release()

        # Fallback if frames couldn't be read
        if not frames:
            logger.warning(f"Could not read frames for {shot_id} [{start_sec}s - {end_sec}s], using fallback.")
            fallback_roi = ROIRegion(
                label="fallback_center",
                bbox_norm=[0.25, 0.1, 0.5, 0.8],
                confidence=0.5,
                reason="Default centered fallback"
            )
            return ShotAnalysisResult(
                shot_id=shot_id,
                start_sec=start_sec,
                end_sec=end_sec,
                source_width=width,
                source_height=height,
                roi=fallback_roi,
                is_wide_object=False,
                is_drifting=False,
                drift_distance=0.0,
                start_center_x=0.5,
                end_center_x=0.5,
                median_center_x=0.5,
                keyframe_images=[],
            )

        # 1. Motion & Edge Saliency Analysis across sampled frames
        centers_x: list[float] = []
        centers_y: list[float] = []
        core_widths: list[float] = []

        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        for i in range(1, len(frames)):
            curr_gray = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(prev_gray, curr_gray)
            _, motion_mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)

            # Edge detection to identify workpiece/tool boundaries
            edges = cv2.Canny(curr_gray, 60, 180)
            combined_saliency = cv2.addWeighted(motion_mask, 0.65, edges, 0.35, 0)

            # Find contours
            contours, _ = cv2.findContours(combined_saliency, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter and sort by area to isolate the INTERACTION_CORE
            valid_contours = [c for c in contours if cv2.contourArea(c) > (width * height * 0.002)]
            valid_contours.sort(key=cv2.contourArea, reverse=True)

            if valid_contours:
                # Take top 3 contours (primary tool, workpiece, and hands)
                top_contours = valid_contours[:3]
                boxes = [cv2.boundingRect(c) for c in top_contours]
                
                # Compute area-weighted centroid of core action
                total_area = sum(cv2.contourArea(c) for c in top_contours)
                weighted_cx = sum(((b[0] + b[2]/2.0) * cv2.contourArea(c)) for b, c in zip(boxes, top_contours)) / total_area
                weighted_cy = sum(((b[1] + b[3]/2.0) * cv2.contourArea(c)) for b, c in zip(boxes, top_contours)) / total_area

                norm_cx = weighted_cx / width
                norm_cy = weighted_cy / height

                # Filter out outlier contours (like flying sparks > 0.35 width away from centroid)
                core_boxes = [
                    b for b in boxes 
                    if abs((b[0] + b[2]/2.0) / width - norm_cx) < 0.35
                ]
                if not core_boxes:
                    core_boxes = boxes[:1]

                min_x = min(b[0] for b in core_boxes)
                max_x = max(b[0] + b[2] for b in core_boxes)
                c_width = (max_x - min_x) / width

                centers_x.append(norm_cx)
                centers_y.append(norm_cy)
                core_widths.append(c_width)
            else:
                centers_x.append(0.5)
                centers_y.append(0.5)
                core_widths.append(0.3)

            prev_gray = curr_gray

        if not centers_x:
            centers_x = [0.5]
            centers_y = [0.5]
            core_widths = [0.3]

        start_cx = centers_x[0]
        end_cx = centers_x[-1]
        median_cx = float(np.median(centers_x))
        median_cy = float(np.median(centers_y))
        drift_dist = abs(end_cx - start_cx)
        avg_core_w = float(np.mean(core_widths))

        # Decision Heuristics per SPEC Section 4 & 5:
        # 1. Wide reveal / comparison:
        # Stages AFTER_REVEAL, BEFORE, TEST showcasing whole machine or workpiece
        if stage_name in ("AFTER_REVEAL", "BEFORE"):
            is_wide_object = True
        elif stage_name == "TEST" and avg_core_w > 0.45:
            is_wide_object = True
        elif avg_core_w > 0.60:
            is_wide_object = True
        else:
            is_wide_object = False

        # 2. Dynamic Pan:
        # Tool action drifting horizontally across the frame (e.g. lathe tool turning a shaft)
        # Traversal > 12% width over duration, and not a static wide shot
        is_drifting = (not is_wide_object) and (drift_dist > 0.12)

        # Active ROI bounds
        roi_x = max(0.0, min(1.0 - avg_core_w, median_cx - avg_core_w / 2.0))
        roi_y = max(0.0, min(1.0 - 0.6, median_cy - 0.3))

        roi = ROIRegion(
            label="interaction_core",
            bbox_norm=[round(roi_x, 3), round(roi_y, 3), round(min(1.0, avg_core_w), 3), 0.6],
            priority=1,
            confidence=0.92,
            reason=f"Stage: {stage_name} | Interaction center at x={median_cx:.2f}, y={median_cy:.2f}"
        )

        return ShotAnalysisResult(
            shot_id=shot_id,
            start_sec=start_sec,
            end_sec=end_sec,
            source_width=width,
            source_height=height,
            roi=roi,
            is_wide_object=is_wide_object,
            is_drifting=is_drifting,
            drift_distance=drift_dist,
            start_center_x=start_cx,
            end_center_x=end_cx,
            median_center_x=median_cx,
            keyframe_images=frames,
        )
