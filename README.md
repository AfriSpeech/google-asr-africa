# google-asr-africa

Transcribe African-language speech with Google's free web ASR endpoint —
only for the languages where it actually works.

Google's free endpoint silently falls back to English for unsupported
languages, so you can get English "transcripts" of your African audio.
This package only ships languages we've **verified** transcribe in their own
orthography — with a resumable batch transcriber and a probe to test new ones.

## Install

```bash
pip install google-asr-africa
```

## Quick start

```bash
# list the verified languages
google-asr-africa list-languages

# transcribe a folder of audio (resumable, rate-limited)
google-asr-africa transcribe data/amharic_clips --language amharic
```

```python
from google_asr_africa import transcribe_folder

tr = transcribe_folder('data/kirundi_clips', language='rn', rpm=50)
print(tr.stats)                        # {'ok': 120, 'unknown': 3, ...}
text = tr.transcripts['clip_00042.flac']
```

Batches are crash-safe: a rerun continues where a stopped run left off and
retries only transient failures.

## Verify a new language

```bash
google-asr-africa probe rg --audio my_kiraundi.wav
# SUPPORTED / UNSUPPORTED / REVIEW(<actual-language>)
```

## Verified languages

Amharic, Chichewa, Hausa, Igbo, Kinyarwanda, Kirundi, Ndebele, Oromo,
Sepedi, Sesotho, Setswana, Shona, Swahili, Swati, Tigrinya, Tsonga, Twi,
Venda, Xhosa, Yoruba, Zulu. Run `list-languages` for the full table.

## License

MIT — covers this code only. Google's ASR service and its outputs are subject
to [Google's Terms of Service](https://policies.google.com/terms).

Part of [AfriSpeech](https://github.com/AfriSpeech) — open-source tools for
African language technology.