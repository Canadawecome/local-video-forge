"""Offline tests for GPT-5.6 Sol media/evidence adaptation. No API calls."""
import unittest
from pydantic import ValidationError
from local_video_forge_sol_source_contracts_v2_6 import (
    SourceScoutPlanV26, FrameEvidenceV26, ClipEvidenceBundleV26,
    SolRequestContentV26
)

def source(**kw):
    x = dict(source_id="src_1", youtube_url="https://www.youtube.com/watch?v=ABC123",
             source_mode="METADATA_ONLY", source_summary="Workshop metal cutting.",
             global_opus_prompt_en="Find authentic metalwork and ASMR close-ups.")
    x.update(kw)
    return x

def frame(t=2):
    return dict(clip_time_sec=t, image_path=f"frames/{int(t)}.jpg", sha256="a" * 64,
                extraction_method="UNIFORM")

class SourceScoutTests(unittest.TestCase):
    def test_metadata_only_without_timestamps(self):
        x=SourceScoutPlanV26.model_validate(source())
        self.assertEqual(x.openai_model,"gpt-5.6-sol")
        self.assertFalse(x.candidate_windows)

    def test_reject_invented_window(self):
        with self.assertRaises(ValidationError):
            SourceScoutPlanV26.model_validate(source(candidate_windows=[dict(window_id="w1",start_sec=10,end_sec=20,
                evidence_ids=["e1"],basis="SUBTITLE",prompt_en="Find a hammer strike.")]))

    def test_subtitle_timestamps_have_basis(self):
        x=SourceScoutPlanV26.model_validate(source(source_mode="SUBTITLE_ENRICHED",
            source_transcript_available=True,
            evidence=[dict(evidence_id="e1",source_kind="SUBTITLE",text="Jetzt schlagen wir.",
                           start_sec=10,end_sec=30,verified=True)],
            candidate_windows=[dict(window_id="w1",start_sec=12,end_sec=22,
                                    evidence_ids=["e1"],basis="SUBTITLE",prompt_en="Find visible metal forging.")]))
        self.assertEqual(len(x.candidate_windows),1)

    def test_reject_window_outside_evidence(self):
        with self.assertRaises(ValidationError):
            SourceScoutPlanV26.model_validate(source(source_mode="SUBTITLE_ENRICHED",
                source_transcript_available=True,
                evidence=[dict(evidence_id="e1",source_kind="SUBTITLE",text="Forge",start_sec=10,end_sec=25)],
                candidate_windows=[dict(window_id="w1",start_sec=8,end_sec=20,
                                        evidence_ids=["e1"],basis="SUBTITLE",prompt_en="Find visible metal forging.")]))

    def test_zero_original_download_mode(self):
        with self.assertRaises(ValidationError):
            SourceScoutPlanV26.model_validate(source(source_downloaded=True))

    def test_source_frame_evidence_requires_refs(self):
        with self.assertRaises(ValidationError):
            SourceScoutPlanV26.model_validate(source(source_mode="AUTHORIZED_SOURCE_FRAMES",source_downloaded=True,
                 evidence=[dict(evidence_id="e1",source_kind="SOURCE_FRAME",text="hammer",start_sec=3,end_sec=4)]))

class ClipEvidenceTests(unittest.TestCase):
    def clip(self, **kwargs):
        x=dict(clip_uid="src_1:p1:c1",clip_duration_sec=61,video_path="opus_original.mp4",image_frames=[frame(2),frame(4)])
        x.update(kwargs)
        return x

    def test_clip_ok(self):
        x=ClipEvidenceBundleV26.model_validate(self.clip())
        self.assertEqual(len(x.image_frames),2)

    def test_reject_future_frame(self):
        with self.assertRaises(ValidationError):
            ClipEvidenceBundleV26.model_validate(self.clip(image_frames=[frame(100)]))

    def test_reject_unsafe_path(self):
        with self.assertRaises(ValidationError):
            FrameEvidenceV26.model_validate(dict(frame(2),image_path="../../secrets.jpg"))

    def test_reject_unsorted_frames(self):
        with self.assertRaises(ValidationError):
            ClipEvidenceBundleV26.model_validate(self.clip(image_frames=[frame(4),frame(2)]))

    def test_reject_unseen_video(self):
        with self.assertRaises(ValidationError):
            ClipEvidenceBundleV26.model_validate(self.clip(visual_inspection_ready=False))

    def test_reject_raw_video_as_sol_input(self):
        with self.assertRaises(ValidationError):
            SolRequestContentV26.model_validate({"type":"input_video","video_url":"https://youtube.com/watch?v=123"})

    def test_allow_text_and_frame_image(self):
        self.assertEqual(SolRequestContentV26(type="input_text",text="Analyse frames").type,"input_text")
        self.assertEqual(SolRequestContentV26(type="input_image",image_url="data:image/jpeg;base64,YQ==").type,"input_image")

if __name__ == '__main__':
    unittest.main()
