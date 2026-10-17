from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from test_render_v2_12 import mkclip, wave
from strict_english_render_v2_12 import (
    process, rms_db, compact_ass, compact_caption_cues,
    check_asmr_retention, check_transient_retention, SR,
)


def test_four_word_cues_and_natural_pause():
    words=[(.1,.22,'In'),(.23,.36,'his'),(.37,.58,'workshop'),(.59,.71,'today'),
           (1.3,1.45,'hot'),(1.46,1.66,'steel')]
    cues=compact_caption_cues(words,max_words=4,max_chars=28)
    assert [x[2] for x in cues]==['In his workshop today','hot steel']
    ass,style=compact_ass(cues,1080,1920)
    assert style['font_px']==54 and style['anchor_y_pct']==85
    assert r'\pos(540,1632)' in ass


def test_per_shot_caption_position_and_emphasis(tmp_path):
    p=mkclip(tmp_path/'clip')
    (p/'caption_regions.json').write_text(json.dumps([
       {'start':0,'end':2.0,'anchor_pct':85.0},
       {'start':2.0,'end':3.0,'anchor_pct':78.0,'italic_terms':['Bright']}
    ]))
    result=process(p)
    assert result['caption_style']['adaptive_regions']==2
    ass=(p/'captions_en.ass').read_text()
    assert r'\pos(160,483)' in ass  # default/full-frame 85%
    assert r'\pos(160,443)' in ass  # letterbox shot 78%
    assert r'{\i1}Bright{\i0}' in ass
    assert 'Bright steel.' in (p/'captions_en.srt').read_text()


def test_unsafe_caption_region_stops_render(tmp_path):
    p=mkclip(tmp_path/'clip')
    (p/'caption_regions.json').write_text(json.dumps([
      {'start':0,'end':2.5,'anchor_pct':85},
      {'start':2.0,'end':2.9,'anchor_pct':78}
    ]))
    with pytest.raises(ValueError,match='region time/position invalid'):
        process(p)
    assert not (p/'final.mp4').exists()


def test_voice_not_auto_clamped_to_quiet_bed(tmp_path):
    p=mkclip(tmp_path/'clip')
    # English voice much stronger than the background, but safely below clipping.
    sf.write(p/'audio'/'tts'/'story1.wav',wave(.65,500,.20),SR)
    result=process(p)
    speech,_=sf.read(p/'audio'/'english_voice_only.wav',always_2d=True)
    a,b=round(2.2*SR),round(2.6*SR)
    assert rms_db(speech[a:b]) > -22  # no old +4dB-to-background clamp
    assert result['workshop_bed_never_ducked_for_english_voice']
    assert result['legacy_max_voice_over_bed_db_ignored']
    assert len(result['final_mp4_asmr_during_voice'])==2


def test_bed_survives_in_final_encoded_mp4(tmp_path):
    p=mkclip(tmp_path/'clip')
    result=process(p)
    vals=result['final_mp4_asmr_during_voice']
    assert len(vals)==2
    assert all(x['estimated_change_db'] > -7 for x in vals)
    master=result['mastering']
    assert 'integrated_lufs' in master and 'true_peak_dbtp' in master
    assert 'reference_integrated_lufs' in master


def test_short_impact_loss_is_rejected_even_when_average_rms_is_similar():
    raw=wave(2.0,300,.045)
    bed=raw.copy()
    a=round(1.10*SR)
    duration=.025
    hit=wave(duration,1800,.22)
    raw[a:a+len(hit)] += hit
    marks=[type('Mark',(),{'start':1.0,'end':1.4,'kind':'hammer'})()]
    # A brief, strong high-frequency hammer hit is gone in separated bed.
    # Average RMS over the entire region should not alone reject it.
    assert rms_db(bed[round(SR):round(1.4*SR)])-rms_db(raw[round(SR):round(1.4*SR)]) > -8
    check_asmr_retention(raw,bed,marks)
    with pytest.raises(ValueError,match='transient'):
        check_transient_retention(raw,bed,marks)
