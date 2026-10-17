#!/usr/bin/env python3
"""Conservatively migrate v3.2 story plan to v3.3 universal source fields.

DOES NOT certify that audio is speech-free in languages other than German.
Does NOT make country assertions. Requires human re-review of audio and context.
"""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

def migrate(folder: Path, *, write: bool=False, topic_en: str='Workshop craft process') -> dict:
    path=folder/'story_plan.json'
    original=json.loads(path.read_text(encoding='utf-8'))
    if original.get('schema_version')!='3.1':
        raise ValueError('Only v3.2 bundle schema_version=3.1 can be migrated')
    german=original.pop('source_german_speech',[])
    original.pop('german_speech_status',None)
    original['schema_version']='3.3'
    original['source_context']={
        'source_language':'und','source_language_status':'UNDETERMINED',
        'language_evidence_refs':[],
        'source_country':None,'source_country_status':'UNKNOWN',
        'country_evidence_refs':[],'country_reviewed_by':None,
        'topic_en':topic_en,'verified_facts':[]}
    original['source_speech_status']='UNCERTAIN'
    original['source_speech']=[{'id':item['id'],'start':item['start'],
        'end':item['end'],'language':'de','transcript':item.get('text_de',''),
        'evidence_ref':item.get('evidence_ref')} for item in german]
    # Do NOT grandfather old German-only clean-stem review into all-speech guarantee.
    original['workshop_stem_qc_passed']=False
    result={'status':'MIGRATED_PENDING_SOURCE_AND_AUDIO_REVIEW','plan':original,
            'action':'Confirm all source speech removed, source language/country evidence; reapprove replacement_qc.json using source_voice_absent.'}
    if write:
        shutil.copy2(path,path.with_suffix('.v32.backup.json'))
        path.write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Put old QC aside, preserving historical evidence but invalidating old approval.
        qc=folder/'audio'/'replacement_qc.json'
        if qc.is_file():
            qc.rename(qc.with_suffix('.v32.backup.json'))
        result['written']=str(path)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder',required=True,type=Path)
    p.add_argument('--topic-en',default='Workshop craft process')
    p.add_argument('--write',action='store_true',help='write v3.3 plan and back up old plan/QC')
    a=p.parse_args()
    r=migrate(a.folder,write=a.write,topic_en=a.topic_en)
    print(json.dumps(r,ensure_ascii=False,indent=2))
