# google-asr-africa

**Transcribe African-language speech with Google's free web ASR endpoint — but
only for the languages where it actually works.**

The free `recognize_google` endpoint silently falls back to English for
languages it doesn't really support. You request `wolof` and get English
"transcripts" that look like success. That is worse than silence: it poisons
training data. This package ships a **verified** catalog of African languages
whose transcripts genuinely come back in the target language, a resumable
batched transcriber, and a probe that tests whether any new language code
really works before you trust it.

Verified against real audio (JW.org clips) with three independent signals:
transcribing under a bogus code (same output ⇒ the code does nothing),
GlotLID (what language is the text actually in), and africa-g2p orthography
coverage. See [`probe`](#probe-new-languages) below.

## Install

```bash
pip install google-asr-africa
```

## Transcribe

```bash
# list the verified languages
google-asr-africa list-languages

# transcribe a folder of audio (resumable)
google-asr-africa transcribe data/amharic_clips --language amharic
# --rpm 50 by default (rate-limit the free endpoint); --ext .flac to pick
# wav/mp3; 0 = unlimited
```

The transcriber is concurrent, rate-limited and **crash-safe**: every clip's
verdict is written the moment it's produced, so a rerun continues exactly
where a stopped run left off and retries only transient API failures.

```python
from google_asr_africa import transcribe_folder, support_code

tr = transcribe_folder('data/kirundi_clips', language='rn', rpm=50)
print(tr.stats)                       # {'ok':... 'unknown':... 'request':... 'error':...}
text = tr.transcripts['clip_00042.flac']
```

## Language semantics

Statuses per clip:

- **ok** — recognised in the requested language
- **unknown** — no intelligible speech heard (a real, final answer; never retried)
- **request** — API/network/rate-limit failure (transient; retried on rerun)
- **error** — unreadable clip or unexpected failure (retried on rerun)

## Verify a language before trusting it

```bash
# needs real audio with actual speech in the candidate language
google-asr-africa probe rg --audio my_kiraundi.wav
# SUPPORTED / UNSUPPORTED / REVIEW(<actual-language>)
```

It reports what the endpoint actually returns under the language's own code
and under a bogus code. If both come back identical, the code does nothing.
Then GlotLID and africa-g2p say whether the text is really in your language.
Supported results can be added to `languages.json` and shipped.

## Verified languages

20 African languages today (Amharic, Chichewa, Hausa, Igbo, Kinyarwanda,
Kirundi, Ndebele, Oromo, Sepedi, Sesotho, Setswana, Shona, Swahili, Swati,
Tsonga, Tigrinya, Twi, Venda, Xhosa, Yoruba, Zulu — 21 entries). Run
`list-languages` for the full table.

Verification method, the catalog and the probe trade the same source of truth
as the [Africa Female Speech](https://github.com/AfriSpeech/africa-female-speech)
dataset pipeline that first pinned these languages down.

## Related

- [africaspeech-selector](https://github.com/AfriSpeech/afrispeech-selector) — audio
  selection for ASR/TTS from recorded African speech.
- [africa-g2p](https://github.com/AfriSpeech/africa-g2p) — orthography toolkit
  used by the probe's character-cover signal.

## License

**MIT** — this license covers only the code in this repository (the thin
wrapper around Google's speech endpoint: catalog, batch transcriber, probe).
It does **not** license Google's ASR service or anything it produces.

Google's free web ASR endpoint is a Google service. Using it, and any
transcripts/intermediate audio it returns, is subject to
[Google's Terms of Service](https://policies.google.com/terms) and the terms
of the endpoint you call (`speech_recognition.recognize_google` is the
*web* demo endpoint, not the paid Cloud Speech-to-Text API). If your use
needs a commercial SLA or a formal data-processing agreement, use
[Google Cloud Speech-to-Text](https://cloud.google.com/speech-to-text) instead
and swap one line in [`transcribe.py`](src/google_asr_africa/transcribe.py).

Part of [AfriSpeech](https://github.com/AfriSpeech) — open-source tools for
African language technology.