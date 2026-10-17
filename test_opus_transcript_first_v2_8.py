from opus_transcript_first_v2_8 import (
    Segment, MapPiece, TranscriptError, parse_srt, to_srt, from_opus_project_api,
    choose_transcript, map_project_to_clip,
)
import unittest

SRT='''1
00:00:02,000 --> 00:00:03,500
Hier wird der Stahl erhitzt.

2
00:00:07,300 --> 00:00:09,100
Jetzt schlagen wir mit dem Hammer.
'''

class TranscriptTests(unittest.TestCase):
    def test_srt_parse(self):
        s=parse_srt(SRT); self.assertEqual(len(s),2); self.assertEqual(s[1].start,7.3)
    def test_srt_round_trip(self):
        self.assertEqual(parse_srt(to_srt(parse_srt(SRT)))[0].end,3.5)
    def test_srt_priority_does_not_call_whisper(self):
        def fail(): raise AssertionError('whisper unexpectedly called')
        segs,info=choose_transcript(duration=20,clip_srt=SRT,whisper_fallback=fail)
        self.assertFalse(info['whisper_used']); self.assertEqual(len(segs),2)
    def test_invalid_srt_calls_whisper(self):
        segs,info=choose_transcript(duration=2,clip_srt=SRT,
            whisper_fallback=lambda:[Segment(0,1,'Guten Tag')])
        self.assertTrue(info['whisper_used']); self.assertEqual(len(segs),1)
    def test_clip_timed_json_skips_whisper(self):
        segs,info=choose_transcript(duration=5,clip_timed=[{'start':.1,'end':1,'text':'Ja'}],
            whisper_fallback=lambda: (_ for _ in ()).throw(AssertionError()))
        self.assertEqual(info['source'],'opus_clip_timed_json')
    def test_untimed_clip_text_falls_back(self):
        _,info=choose_transcript(duration=5,clip_timed={'transcript':'Hallo'},
            whisper_fallback=lambda:[Segment(1,2,'Hallo')])
        self.assertTrue(info['whisper_used'])
    def test_project_timebase_no_map_calls_whisper(self):
        project={'data':[[{'id':0,'start':100,'end':101,'text':'Hallo','words':[{'word':'Hallo','start':100,'end':101}]}]]}
        _,info=choose_transcript(duration=5,project_transcript=project,
            whisper_fallback=lambda:[Segment(.5,1.2,'Hallo')])
        self.assertEqual(info['source'],'local_whisper_fallback')
    def test_source_project_parse(self):
        data={'data':[[{'id':0,'start':100,'end':102,'text':'Guten Tag','words':[{'word':'Guten','start':100,'end':100.7},{'word':'Tag','start':100.8,'end':101.4}]}]]}
        s=from_opus_project_api(data); self.assertEqual([x.text for x in s],['Guten','Tag'])
    def test_cli_millisecond_payload(self):
        from opus_transcript_first_v2_8 import from_opus_project_api
        p={'paragraphs':[{'start_ms':100000,'end_ms':101000,'text':'Hallo',
            'words':[{'word':'Hallo','start_ms':100000,'end_ms':101000}]}]}
        words=from_opus_project_api(p)
        self.assertEqual(words[0].start,100)
        self.assertEqual(words[0].end,101)
    def test_verified_reorder_map(self):
        source=[Segment(50,51,'first'),Segment(100,101,'second')]
        pieces=[MapPiece(100,102,0,2), MapPiece(50,52,2,4)]
        output=map_project_to_clip(source,pieces,4)
        self.assertEqual([s.text for s in output],['second','first'])
    def test_reject_partial_word_crossing_cut(self):
        with self.assertRaises(TranscriptError):
            map_project_to_clip([Segment(1,2,'word')],[MapPiece(1.5,3,0,1.5)],1.5)
    def test_srt_empty_calls_whisper(self):
        s,i=choose_transcript(duration=10,clip_srt='',whisper_fallback=lambda:[])
        self.assertTrue(i['whisper_used']);self.assertTrue(i['empty_transcript_requires_vad_or_listen_qc'])
    def test_no_data_no_fallback_is_error(self):
        with self.assertRaises(TranscriptError): choose_transcript(duration=10)

if __name__=='__main__': unittest.main()
