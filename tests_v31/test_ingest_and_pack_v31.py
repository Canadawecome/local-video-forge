import json
import pytest
from pathlib import Path
from ingest_opus_batch_v31 import ingest
from validate_publish_pack_v31 import validate

def test_ingest_all_and_deduplicate(tmp_path):
    inp=tmp_path/'input';inp.mkdir()
    for n,data in [('a.mp4',b'clip1'),('b.mp4',b'clip2'),('duplicate.mp4',b'clip1')]:
        (inp/n).write_bytes(data)
    r=ingest(inp,tmp_path/'out','https://www.youtube.com/watch?v=test',allowed=True)
    assert r['unique_clip_count']==2
    assert len(list((tmp_path/'out').glob('clip_*/clip.mp4')))==2
    assert len(r['items'])==3

def test_cannot_ingest_without_rights_review(tmp_path):
    inp=tmp_path/'input';inp.mkdir();(inp/'c.mp4').write_bytes(b'fake')
    with pytest.raises(ValueError,match='rights-reviewed'): ingest(inp,tmp_path/'out')

def test_publish_pack_reports_missing(tmp_path):
    out=validate(tmp_path)
    assert 'final.mp4' in out['missing'] and out['status']=='INCOMPLETE'
