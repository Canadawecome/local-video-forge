"""Fail-closed check for common unsupported geography in English narration.

This is a partial lexical tripwire, NOT a full fact-check or NER engine.
Editors must still review claims and references before publishing.
"""
from __future__ import annotations
import re
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from storytelling_contracts_v33 import StorytellingPlan

# Can be extended: English country names / demonyms / high-signal place names.
# Each alias maps to *country of geographic origin*, not language.
_COUNTRY_ALIASES = {
    'DE': ('germany','german','berlin','munich','bavaria','hamburg','deutschland'),
    'KR': ('south korea','korea','korean','seoul','busan','incheon','daegu'),
    'KP': ('north korea','north korean','pyongyang'),
    'JP': ('japan','japanese','tokyo','osaka','kyoto','nagoya'),
    'CN': ('china','chinese','beijing','shanghai','guangzhou','shenzhen'),
    'US': ('united states','american','america','u.s.','usa','new york','california'),
    'GB': ('united kingdom','british','britain','england','english workshop','london'),
    'FR': ('france','french','paris'),
    'IT': ('italy','italian','rome','milan'),
    'VN': ('vietnam','vietnamese','hanoi','ho chi minh city'),
}
# Keep named material/technical terms from turning into false location claims:
# these are NOT whitelisted; a reviewer may choose generic non-geographic phrasing.
_ALIASES = sorted({alias for aliases in _COUNTRY_ALIASES.values() for alias in aliases}, key=len, reverse=True)
_PATTERN = re.compile(r'(?<!\w)(?:' + '|'.join(
    re.escape(a).replace(r'\ ',r'\s+') for a in _ALIASES
) + r')(?!\w)', re.I)


def detected_geography(text: str) -> list[dict]:
    found=[]
    for match in _PATTERN.finditer(text):
        token=match.group(0).casefold()
        for code,aliases in _COUNTRY_ALIASES.items():
            if token in aliases:
                found.append({'word':match.group(0),'country_code':code})
                break
    return found


def validate_geography_claims(plan: 'StorytellingPlan', text: str, *, field: str) -> None:
    hits=detected_geography(text)
    if not hits: return
    country=(plan.source_context.source_country if plan.source_context.source_country_status=='VERIFIED' else None)
    invalid=[h for h in hits if h['country_code']!=country]
    if invalid:
        phrases=', '.join(f"{h['word']} ({h['country_code']})" for h in invalid)
        raise ValueError(f'UNSUPPORTED_COUNTRY_CLAIM in {field}: {phrases}; source country is {country or "UNKNOWN"}. '
                         'Use a process-focused sentence or verify a location with evidence and human review.')


def validate_publication_texts(plan: 'StorytellingPlan', folder) -> None:
    for name in ('script_en.md','script_tts.txt','description.txt'):
        p=folder/name
        if p.is_file():
            validate_geography_claims(plan,p.read_text(encoding='utf-8'),field=name)
