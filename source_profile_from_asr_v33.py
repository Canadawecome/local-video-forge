#!/usr/bin/env python3
"""Normalize language-ID evidence from a separately run ASR model.

This program DOES NOT transcribe audio or fetch URLs. A connected Whisper,
OpusClip, or other approved ASR adapter must provide measured language results.
It never infers country from language. Confidence cutoff is configurable but
model scores are not universally calibrated; low confidence => UNKNOWN.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from storytelling_contracts_v33 import SourceContext

def build_profile(data: dict, threshold: float = .85) -> SourceContext:
    if not .5 <= threshold <= 1.:
        raise ValueError('threshold outside [0.5, 1.0]')
    lid = data.get('language_detection') or {}
    candidate=str(lid.get('language') or 'und').strip().lower()
    confidence=lid.get('confidence')
    evidence=lid.get('evidence_ref')
    high=bool(re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]{2,8})*',candidate)) and candidate not in ('und','mul')
    if not isinstance(confidence,(float,int)) or not 0 <= confidence <= 1:
        high=False
    if not evidence: high=False
    if high and confidence >= threshold:
        lang,status,refs=candidate,'CONFIRMED',[str(evidence)]
    else:
        lang,status,refs='und','UNDETERMINED',[]
    # Country explicitly controlled separately via evidence + reviewer.
    country_review=data.get('country_review') or {}
    code=country_review.get('country_code')
    country_refs=country_review.get('evidence_refs') or []
    reviewer=country_review.get('reviewed_by')
    if country_review.get('verified') is True:
        country_status='VERIFIED'
    else:
        country_status='UNKNOWN';code=None;country_refs=[];reviewer=None
    return SourceContext.model_validate({
        'source_language':lang,'source_language_status':status,'language_evidence_refs':refs,
        'source_country':code,'source_country_status':country_status,
        'country_evidence_refs':country_refs,'country_reviewed_by':reviewer,
        'topic_en':data['topic_en'],'verified_facts':data.get('verified_facts',[])})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--confidence-min',type=float,default=.85)
    a=p.parse_args()
    profile=build_profile(json.loads(a.input.read_text(encoding='utf-8')),a.confidence_min)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(profile.model_dump_json(indent=2)+'\n',encoding='utf-8')
    print(profile.model_dump_json(indent=2))
if __name__=='__main__':main()
