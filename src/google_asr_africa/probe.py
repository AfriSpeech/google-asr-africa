"""Probe whether a language code really works on Google's free ASR endpoint.

Google's free endpoint is unreliable for low-resource languages: an
unsupported code silently falls back to the English model, and you get English
"transcripts" of your African audio — which looks like success and is worse
than nothing.

This probe applies the three-signal test from the pipeline:

    1. bogus-identity   transcribing with a bogus code ('zz-ZZ') yields the
                        same output => the code does nothing -> UNSUPPORTED.
    2. GlotLID          what language is the text ACTUALLY in? Decisive for
                        Latin-script languages that look English-ish.
    3. orthography      share of characters outside the language's africa-g2p
                        grapheme inventory (set when a g2p table is found).

Some ISO codes need near-cousin tolerance (e.g. 'run' vs 'kin', 'swa' vs
'swh'); pass --accept 'run kin' style via the ACCEPT map below.
"""
from __future__ import annotations

import csv
import json
import os
import re
import time

import numpy as np
import soundfile as sf
import speech_recognition as sr

# GlotLID labels accepted as a match for an ISO code when varieties overlap.
ACCEPT = {
    'twi': {'twi', 'aka', 'fat'}, 'fat': {'fat', 'twi', 'aka'},
    'run': {'run', 'kin'}, 'kin': {'kin', 'run'},
    'sot': {'sot', 'nso'}, 'nso': {'nso', 'sot'},
    'kon': {'kon', 'ktu', 'kng'}, 'ktu': {'ktu', 'kon'},
    'nde': {'nde', 'nbl'}, 'nbl': {'nbl', 'nde'},
    'swa': {'swa', 'swh'}, 'swh': {'swh', 'swa'},
    'nya': {'nya'}, 'mlg': {'mlg', 'plt'},
}
BOGUS = 'zz-ZZ'
CHUNKS = 10
CHUNK_SEC = 8.0
SR = 16000
FIELDS = ['code', 'iso', 'n_own', 'n_bogus', 'identical', 'lid_label',
          'lid_prob', 'oov_rate', 'verdict', 'sample']

_model = None


def _lid(text: str):
    global _model
    if _model is None:
        import fasttext
        from huggingface_hub import hf_hub_download
        _model = fasttext.load_model(
            hf_hub_download('cis-lmu/glotlid', 'model_v3.bin'))
    t = ' '.join(text.split())
    if len(t) < 12:
        return '', 0.0
    lab, pr = _model.predict(t, k=1)
    return lab[0].replace('__label__', ''), float(pr[0])


def graphemes(iso: str, g2p_dir: str):
    p = os.path.join(g2p_dir, f'{iso}.json')
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding='utf-8'))
    gs = []
    for v in d.get('scripts', {}).values():
        gs += v or []
    return sorted({g for g in gs if g}, key=len, reverse=True)


def oov_rate(text: str, graphs):
    if not graphs:
        return ''
    t = re.sub(r'[\d\W_]+', ' ', text.lower())
    tot = bad = 0
    for w in t.split():
        i = 0
        while i < len(w):
            for g in graphs:
                if w.startswith(g, i):
                    i += len(g)
                    break
            else:
                bad += 1
                i += 1
            tot += 1
    return f'{bad/tot:.3f}' if tot else ''


def _chunks(audio: str, work: str):
    os.makedirs(work, exist_ok=True)
    info = sf.info(audio)
    total = info.frames / info.samplerate
    if total < CHUNK_SEC * 2:
        return []
    step = max(CHUNK_SEC, (total - CHUNK_SEC - 10) / CHUNKS)
    out = []
    for i in range(CHUNKS):
        start = 10 + i * step
        if start + CHUNK_SEC > total:
            break
        data, srate = sf.read(audio, start=int(start * info.samplerate),
                              frames=int(CHUNK_SEC * info.samplerate),
                              dtype='int16')
        if data.ndim > 1:
            data = data[:, 0]
        if np.abs(data).mean() < 200:
            continue
        p = os.path.join(work, f'c{i}.wav')
        sf.write(p, data, srate)
        out.append(p)
    return out


def _transcribe(paths, code, rec):
    out = []
    for p in paths:
        try:
            with sr.AudioFile(p) as s:
                a = rec.record(s)
            t = rec.recognize_google(a, language=code)
            if t and t.strip():
                out.append(t.strip())
        except sr.UnknownValueError:
            pass
        except Exception:
            time.sleep(1)
    return out


def probe_code(code: str, audio: str | None = None,
               iso: str = '', g2p_dir: str | None = None,
               out: str | None = None, verbose: bool = False) -> dict:
    """Run the three-signal probe for one google ASR language code.

    Returns a row dict with the verdict. When ``audio`` is given it probes
    that file directly; otherwise you must pass pre-cut chunk wavs via
    ``chunks=`` (see tests).
    """
    if not audio:
        raise ValueError('no audio supplied; pass --audio with real speech '
                         'in this language')
    return _run(code, audio, iso=iso, g2p_dir=g2p_dir, out=out, verbose=verbose)


def _run(code: str, audio: str, iso: str = '',
         g2p_dir: str | None = None, out: str | None = None,
         verbose: bool = False) -> dict:
    work = os.path.join(os.path.dirname(os.path.abspath(audio)) or '.',
                        f'.probe_{code}')
    rec = sr.Recognizer()
    row = dict(code=code, iso=iso, n_own=0, n_bogus=0, identical='',
               lid_label='', lid_prob='', oov_rate='', verdict='', sample='')
    try:
        ch = _chunks(audio, work)
        for f in os.listdir(work):
            os.remove(os.path.join(work, f))
        if not ch:
            row['verdict'] = 'NO_AUDIO'
        else:
            own = _transcribe(ch, code, rec)
            bog = _transcribe(ch, BOGUS, rec)
            text = ' '.join(own)
            label, prob = _lid(text) if text else ('', 0.0)
            base = label.split('_')[0] if label else ''
            ident = bool(own) and own == bog
            row.update(n_own=len(own), n_bogus=len(bog), identical=str(ident),
                       lid_label=label, lid_prob=f'{prob:.3f}',
                       oov_rate=oov_rate(text, graphemes(iso, g2p_dir or '')),
                       sample=' | '.join(own[:2])[:220])
            ok = ACCEPT.get(iso, {iso}) if iso else {base}
            if not own:
                row['verdict'] = 'NO_OUTPUT'
            elif ident:
                row['verdict'] = 'UNSUPPORTED'
            elif base in ok:
                row['verdict'] = 'SUPPORTED'
            elif base == 'eng':
                row['verdict'] = 'UNSUPPORTED'
            else:
                row['verdict'] = f'REVIEW({base})'
    except Exception as e:  # noqa: BLE001 - verdict rows, not exceptions
        row['verdict'] = f'ERROR {type(e).__name__}'
        if verbose:
            print(f'  ERROR {type(e).__name__}: {e}')
    if verbose:
        print(f'{code}: {row["verdict"]}  own={row["n_own"]} '
              f'bogus={row["n_bogus"]} identical={row["identical"]} '
              f'lid={row["lid_label"]}({row["lid_prob"]}) '
              f'oov={row["oov_rate"]}')
    if out:
        new = not os.path.exists(out)
        fh = open(out, 'a', newline='', encoding='utf-8')
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
        fh.close()
    return row