"""Offline smoke tests for batch fan-out invariants. Run: python -m unittest -v ..."""
import unittest

from pydantic import ValidationError

from local_video_forge_batch_contracts_v2_5 import BatchManifestV25


def clip(i, status="DISCOVERED", accepted=False, ready=False):
    u = f"src_001:opus_P1:clip_{i}"
    c = dict(clip_uid=u, index_no=i, provider_project_id="opus_P1",
             provider_clip_id=f"clip_{i}", status=status, folder=f"output/clip_{i:03d}",
             rights_state="VERIFIED" if accepted else "UNRESOLVED", accepted=accepted)
    if ready:
        c.update(status="PUBLISH_READY", accepted=True, rights_state="VERIFIED", final_media_qc_pass=True)
        c["script"] = dict(clip_uid=u, revision=1, story_angle=f"Angle {i}", title_en=f"Title {i}",
                           script_path="script_en.md", tts_text_path="script_tts.txt", evidence_refs=["ev1"], qc_pass=True)
        c["voice"] = dict(clip_uid=u, script_revision=1, voice_id="QIhD5ivPGEoYZQDocuHI",
                          model_id="eleven_multilingual_v2", wav_path="audio/voiceover.wav",
                          alignment_path="audio/alignment_word.json", qc_pass=True)
        c["publish_pack"] = dict(clip_uid=u, title_en=f"Title {i}", description_en=f"Unique clip {i}.",
                                 hashtags=["#Blacksmithing", f"#Part{i}"], description_path="description.txt",
                                 hashtags_path="hashtags.txt", final_video_path="final.mp4",
                                 qc_pass=True, human_approved=True)
    return c


def manifest(clips, opus_status="SUCCEEDED", batch_status="BATCH_PARTIAL"):
    return dict(schema_version="2.5", batch_id="batch_001", source_id="src_001",
                youtube_url="https://www.youtube.com/watch?v=VIDEO_ID", batch_status=batch_status,
                opus_projects=[dict(project_id="opus_P1", status=opus_status)],
                discovered_clips=clips,
                counts=dict(discovered=len(clips), accepted=sum(c["accepted"] for c in clips),
                            script_pass=sum(bool(c.get("script")) for c in clips),
                            voice_pass=sum(bool(c.get("voice")) for c in clips),
                            final_pass=sum(c["status"] == "PUBLISH_READY" for c in clips),
                            asmr_final_pass=sum(c["status"] == "PUBLISH_READY" and c.get("narration_mode") == "ASMR_ONLY" for c in clips)),
                opus_batch_closed=True)


class ContractTests(unittest.TestCase):
    def test_dynamic_n_0_1_5_10(self):
        for n in [0, 1, 5, 10]:
            with self.subTest(n=n):
                clips = [clip(i, ready=True) for i in range(1, n+1)]
                parsed = BatchManifestV25.model_validate(manifest(clips))
                self.assertEqual(parsed.counts.final_pass, n)
                self.assertEqual(len({c.folder for c in parsed.discovered_clips}), n)
                self.assertEqual(len({c.script.story_angle for c in parsed.discovered_clips}), n)

    def test_rejected_clips_not_counted(self):
        clips = [clip(i, ready=True) for i in range(1, 7)] + [clip(i, "REJECTED_QC") for i in range(7, 11)]
        data = manifest(clips)
        parsed = BatchManifestV25.model_validate(data)
        self.assertEqual((parsed.counts.discovered, parsed.counts.accepted, parsed.counts.voice_pass), (10, 6, 6))

    def test_cannot_close_while_opus_pending(self):
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest([], opus_status="RUNNING"))

    def test_duplicate_uid_rejected(self):
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest([clip(1), {**clip(1), "index_no": 2, "folder": "output/clip_002"}]))

    def test_fake_ready_rejected(self):
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest([clip(1, "PUBLISH_READY", accepted=True)]))

    def test_cross_clip_script_reference_rejected(self):
        clips = [clip(1, ready=True), clip(2, ready=True)]
        clips[1]["script"]["clip_uid"] = "src_001:opus_P1:clip_1"
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest(clips))

    def test_path_traversal_rejected(self):
        bad = clip(1, ready=True)
        bad["publish_pack"]["final_video_path"] = "../../wrong.mp4"
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest([bad]))

    def test_missing_description_tags_rejected(self):
        bad = clip(1, ready=True)
        bad["publish_pack"]["hashtags"] = []
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest([bad]))

    def test_explicit_asmr_exception(self):
        c = clip(1, ready=True)
        c["narration_mode"] = "ASMR_ONLY"
        c["asmr_only_exception_approved"] = True
        c["voice"] = None
        parsed = BatchManifestV25.model_validate(manifest([c]))
        self.assertEqual((parsed.counts.final_pass, parsed.counts.voice_pass, parsed.counts.asmr_final_pass), (1, 0, 1))

    def test_tts_revision_mismatch_rejected(self):
        bad = clip(1, ready=True)
        bad["voice"]["script_revision"] = 2
        with self.assertRaises(ValidationError):
            BatchManifestV25.model_validate(manifest([bad]))


if __name__ == "__main__":
    unittest.main()
