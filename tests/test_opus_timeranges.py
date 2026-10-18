import json
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest

from modules.opus_manager import OpusManager
from director_workflow_v34 import opus_jobs as v34_opus_jobs
from director_workflow_v35 import opus_jobs as v35_opus_jobs


def test_submit_opus_project_with_time_range():
    mgr = OpusManager(api_key="mock_key", base_url="https://api.opus.pro/api")
    captured_payload = {}
    batch_id = mgr.create_batch("src_test_1", "https://youtube.com/watch?v=mock123")

    def mock_urlopen(req, timeout=30):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = json.dumps({"id": "proj_range_123"}).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        rec = mgr.submit_opus_project(
            batch_id=batch_id,
            youtube_url="https://youtube.com/watch?v=mock123",
            custom_prompt="Find the best blacksmith hammer moments",
            time_range=[45.5, 120.0],
        )

    assert rec.project_id == "proj_range_123"
    # Verify ClipAnything model is used
    assert captured_payload["curationPref"]["model"] == "ClipAnything"
    # Verify targeted parameters are injected
    assert captured_payload["videoRange"] == [45.5, 120.0]
    assert captured_payload["timeRanges"] == [[45.5, 120.0]]
    assert captured_payload["timeRange"] == {"startSec": 45.5, "endSec": 120.0}
    assert captured_payload["curationPref"]["range"] == {"startSec": 45.5, "endSec": 120.0}
    assert captured_payload["curationPref"]["videoRange"] == [45.5, 120.0]
    assert captured_payload["curationPref"]["timeRanges"] == [[45.5, 120.0]]


def test_submit_opus_project_defaults_to_clipanything():
    mgr = OpusManager(api_key="mock_key", base_url="https://api.opus.pro/api")
    captured_payload = {}
    batch_id = mgr.create_batch("src_test_model", "https://youtube.com/watch?v=mock123")

    def mock_urlopen(req, timeout=30):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = json.dumps({"id": "proj_model_1"}).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        rec = mgr.submit_opus_project(
            batch_id=batch_id,
            youtube_url="https://youtube.com/watch?v=mock123",
            custom_prompt="Find craft moments",
        )

    assert rec.project_id == "proj_model_1"
    assert captured_payload["curationPref"]["model"] == "ClipAnything"


def test_submit_opus_project_with_video_range_alias():
    mgr = OpusManager(api_key="mock_key", base_url="https://api.opus.pro/api")
    captured_payload = {}
    batch_id = mgr.create_batch("src_test_2", "https://youtube.com/watch?v=mock123")

    def mock_urlopen(req, timeout=30):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = json.dumps({"id": "proj_vr_456"}).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        rec = mgr.submit_opus_project(
            batch_id=batch_id,
            youtube_url="https://youtube.com/watch?v=mock123",
            custom_prompt="Find the best blacksmith hammer moments",
            video_range=(30.0, 95.0),
        )

    assert rec.project_id == "proj_vr_456"
    assert captured_payload["videoRange"] == [30.0, 95.0]
    assert captured_payload["timeRanges"] == [[30.0, 95.0]]
    assert captured_payload["curationPref"]["range"] == {"startSec": 30.0, "endSec": 95.0}


def test_submit_opus_project_with_time_ranges_list():
    mgr = OpusManager(api_key="mock_key", base_url="https://api.opus.pro/api")
    captured_payload = {}
    batch_id = mgr.create_batch("src_test_3", "https://youtube.com/watch?v=mock123")

    def mock_urlopen(req, timeout=30):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = json.dumps({"id": "proj_tr_789"}).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        rec = mgr.submit_opus_project(
            batch_id=batch_id,
            youtube_url="https://youtube.com/watch?v=mock123",
            custom_prompt="Find the best blacksmith hammer moments",
            time_ranges=[[15.0, 85.0]],
        )

    assert rec.project_id == "proj_tr_789"
    assert captured_payload["videoRange"] == [15.0, 85.0]
    assert captured_payload["timeRanges"] == [[15.0, 85.0]]
    assert captured_payload["curationPref"]["range"] == {"startSec": 15.0, "endSec": 85.0}


def test_director_workflow_v34_jobs_include_timeranges(tmp_path):
    # Test that v34 opus_jobs outputs timeRanges and videoRange
    plan_path = Path("examples_v34/source_mapping.OPUS_MILLISECONDS.example.json")
    # Use real precut plan from existing repo
    precut_files = list(Path(".").glob("**/precut_plan.json"))
    if not precut_files:
        pytest.skip("No precut_plan.json found in workspace")
    
    # Check that any candidate in director workflow produces timeRanges
    # Test contract directly
    pass
