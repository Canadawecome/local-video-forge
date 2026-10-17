"""Comprehensive Acceptance Test Suite for Local Video Forge v2.6.
Verifies all core requirements from Section 14 of SPEC_Local_Video_Forge_ASMR_v2.6_SOL_ONLY_FINAL.md:
- V26-S01: Zero Gemini dependency, runs via GPT-5.6 Sol (Trouter Cloud).
- V26-S02: Zero-download source scout in METADATA_ONLY mode cannot invent range windows.
- V26-S05: Sol adapter forbids raw MP4/audio input.
- V25-02 / V25-T05: OPUS_BATCH_BARRIER prevents fanout before projects reach terminal state.
- V25-T01 / V25-T02: 1 Source -> N Usable Clips -> N Unique Scripts -> N Voices -> N Folders.
- V25-T13: Publication pack hashtag and description validation.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from adapters.sol_adapter import SolAdapter
from config import Config
from local_video_forge_batch_contracts_v2_5 import (
    BatchCounts,
    BatchManifestV25,
    BatchState,
    ClipRecord,
    ClipState,
    NarrationMode,
    OpusProjectRecord,
    OpusProjectState,
    RightsState,
)
from local_video_forge_sol_source_contracts_v2_6 import (
    CandidateWindowV26,
    ClipEvidenceBundleV26,
    FrameEvidenceV26,
    SolRequestContentV26,
    SourceEvidenceV26,
    SourceScoutPlanV26,
    SpeechSegmentV26,
)
from modules.opus_manager import OpusManager
from modules.publication_pack import normalize_hashtags
from modules.source_scout import SourceScout

class AcceptanceTestsV26(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="lvf_test_"))
        Config.DATA_DIR = self.test_dir / "data"
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_v26_s01_no_gemini_dependency(self):
        """V26-S01: System executes without any GOOGLE_API_KEY or GEMINI_API_KEY."""
        self.assertNotIn("GOOGLE_API_KEY", os.environ)
        self.assertNotIn("GEMINI_API_KEY", os.environ)
        self.assertEqual(Config.OPENAI_MODEL, "gpt-5.6-sol")
        self.assertIn("trouter.cloud", Config.OPENAI_BASE_URL)

    def test_v26_s02_metadata_only_no_invented_windows(self):
        """V26-S02: METADATA_ONLY scout mode cannot claim visual windows or transcript."""
        with self.assertRaises(ValueError):
            SourceScoutPlanV26(
                source_id="src_meta_invalid",
                youtube_url="https://www.youtube.com/watch?v=12345678901",
                source_mode="METADATA_ONLY",
                source_summary="Test",
                global_opus_prompt_en="Find authentic blacksmithing sequences with mechanical ASMR.",
                candidate_windows=[
                    CandidateWindowV26(
                        window_id="win_invented",
                        start_sec=10.0,
                        end_sec=50.0,
                        evidence_ids=["ev_1"],
                        basis="SUBTITLE",
                        prompt_en="Hammer forging the axe blade",
                    )
                ],
                source_transcript_available=False,
            )

    def test_v26_s05_reject_raw_video_to_sol(self):
        """V26-S05: Sol multimodal schema strictly forbids raw MP4/audio input types."""
        with self.assertRaises(ValueError):
            SolRequestContentV26(type="input_video")  # type: ignore

        with self.assertRaises(ValueError):
            SolRequestContentV26(type="input_audio")  # type: ignore

        # Valid text and image
        t = SolRequestContentV26(type="input_text", text="Observing blacksmith")
        self.assertEqual(t.type, "input_text")
        img = SolRequestContentV26(type="input_image", image_url="data:image/jpeg;base64,1234")
        self.assertEqual(img.type, "input_image")

    def test_v25_t05_opus_batch_barrier(self):
        """V25-T05: Barrier prevents downstream processing if an Opus project is still pending."""
        opus_mgr = OpusManager()
        batch_id = opus_mgr.create_batch("src_barrier_test", "https://www.youtube.com/watch?v=12345678901")
        
        # Add a running project directly to DB
        from storage.db import get_connection
        proj_id = f"proj_running_{int(time.time()*1000)}"
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO opus_projects (id, batch_id, status) VALUES (?, ?, ?)""",
                (proj_id, batch_id, OpusProjectState.RUNNING.value)
            )

        with self.assertRaises(RuntimeError) as ctx:
            opus_mgr.close_batch_discovery(batch_id, "src_barrier_test", "https://www.youtube.com/watch?v=12345678901")
        self.assertIn("non-terminal", str(ctx.exception))

    def test_v25_t01_t02_dynamic_n_funnel(self):
        """V25-T01 & V25-T02: Batch counts enforce 1-to-N fanout funnel."""
        # Valid 3 clips batch funnel
        counts = BatchCounts(
            discovered=3,
            accepted=3,
            script_pass=3,
            voice_pass=3,
            final_pass=3,
            asmr_final_pass=0,
        )
        self.assertEqual(counts.discovered, 3)

        # Invalid counts where voiced exceeds scripted
        with self.assertRaises(ValueError):
            BatchCounts(
                discovered=3,
                accepted=3,
                script_pass=2,
                voice_pass=3,  # Invalid: cannot have more voice than script
                final_pass=2,
                asmr_final_pass=0,
            )

    def test_v25_t13_hashtag_normalization(self):
        """V25-T13: Hashtags are normalized to #PascalCase without duplicates."""
        raw = ["blacksmithing", "#forging", "Blacksmithing", "#artisan_tools!", "#ASMR"]
        cleaned = normalize_hashtags(raw)
        self.assertIn("#Blacksmithing", cleaned)
        self.assertIn("#Forging", cleaned)
        self.assertIn("#ASMR", cleaned)
        # Ensure no duplicates
        self.assertEqual(len(cleaned), len(set(cleaned)))

if __name__ == "__main__":
    unittest.main()
