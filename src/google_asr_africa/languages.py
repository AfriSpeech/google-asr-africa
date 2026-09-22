"""Verified-language catalog for Google's free ASR endpoint.

`google` (the speech_recognition language hint, e.g. ``ny``, ``am``) is what
you pass on every call. The catalog is the outcome of `probe_asr_support`:
each entry was tested against real audio (JW.org) transcribed under both the
language's own code and a bogus code, and independently checked with GlotLID
(what language the text is really in) plus africa-g2p orthography coverage.
Only languages whose transcripts were actually in the target language are
"supported".

The catalog lives in ``languages.json`` alongside this module, so adding a
newly probed language is just editing the file.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_CAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'languages.json')


def catalog() -> List[Dict[str, Any]]:
    """Return the full verified-language catalog."""
    with open(_CAT_PATH, encoding='utf-8') as fh:
        return json.load(fh)


def supported() -> List[Dict[str, Any]]:
    """Return catalog entries that pass the ASR support verdict."""
    return [e for e in catalog() if e.get('verdict', 'SUPPORTED') == 'SUPPORTED']


def supported_codes() -> List[str]:
    """Google ASR language codes known to transcribe in the target language."""
    return [e['code'] for e in supported()]


def support_code(name_or_code: str) -> Optional[str]:
    """Resolve a language name or code to a supported google ASR code.

    Accepts a google code (``ny``), an ISO 639-3 code (``nya``), or a common
    language name. Returns None when nothing matches or the language is not
    verified as supported.
    """
    target = name_or_code.strip().lower()
    for e in supported():
        if e['code'] == target:
            return e['code']
        if e.get('iso') == target:
            return e['code']
        if e.get('language', '').lower() == target:
            return e['code']
    return None


def support_codes_for(language: str) -> List[str]:
    """All verified codes that can transcribe *language honestly*.

    Useful when a macro-language has several verified varieties (none do
    today, but see Swahili/Kirundi where GlotLID accepts the near cousin). The
    catalog keeps one entry per code, so this mostly round-trips a single
    entry; it exists so callers don't have to know that.
    """
    out: List[str] = []
    for e in supported():
        if support_code(language) == e['code']:
            out.append(e['code'])
    if not out:
        c = support_code(language)
        if c:
            out = [c]
    return out