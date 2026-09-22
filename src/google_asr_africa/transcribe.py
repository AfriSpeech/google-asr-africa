"""Resumable batched transcription with Google's free ASR endpoint.

The batch machinery is lifted and generalised from the Africa Female Speech
pipeline: it is async, rate-limited, and crash-safe. Every clip's verdict is
recorded the moment it is produced, so a rerun continues exactly where a
stopped run left off instead of paying for the same clips twice.

Statuses (the important design choice):
    ok      - text recognised in the requested language
    unknown - the model heard no intelligible speech (a real, final answer)
    request - API/network/rate-limit failure (transient - retry later)
    error   - unreadable clip or unexpected failure (retry later)

Only ``unknown`` is a verdict about the audio. ``request``/``error`` clips are
left untracked, so a rerun picks them up again.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import time
from typing import Dict, List, Optional, Set, Tuple

import speech_recognition as sr


@dataclasses.dataclass
class Result:
    """Verdict for a single audio file."""
    path: str
    status: str
    text: str = ''

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK and bool(self.text.strip())


STATUS_OK = 'ok'
STATUS_UNK = 'unknown'
STATUS_REQ = 'request'
STATUS_ERR = 'error'


@dataclasses.dataclass
class Transcripts:
    """Container for a batch run's transcriptions and log tracking."""
    transcripts: Dict[str, str]
    done: Set[str]
    failed: Set[str]
    stats: Dict[str, int]


def load_log(path: str) -> Set[str]:
    out: Set[str] = set()
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            out = {l.strip() for l in fh if l.strip()}
    return out


def append_log(path: str, line: str) -> None:
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


async def transcribe_one(clip_path: str, language: str,
                         tries: int = 3) -> Result:
    """Transcribe one audio file in ``language`` (google code) via the free endpoint."""
    recognizer = sr.Recognizer()

    def sync():
        try:
            with sr.AudioFile(clip_path) as source:
                audio = recognizer.record(source)
        except Exception as e:  # unreadable / corrupt file
            return Result(clip_path, STATUS_ERR, str(e))
        for attempt in range(tries):
            try:
                text = recognizer.recognize_google(audio, language=language)
                return Result(clip_path, STATUS_OK, text)
            except sr.UnknownValueError:
                return Result(clip_path, STATUS_UNK)
            except sr.RequestError:
                if attempt == tries - 1:
                    return Result(clip_path, STATUS_REQ)
                time.sleep(2 ** attempt)
            except Exception as e:
                return Result(clip_path, STATUS_ERR, str(e))
        return Result(clip_path, STATUS_REQ)

    return await asyncio.to_thread(sync)


class _Tracker:
    """Shared mutable state across coroutines: logs, transcripts and stats."""

    def __init__(self, done_log: str, failed_log: str, tr_path: str,
                 language: str, rpm: int):
        self.done = load_log(done_log)
        self.failed = load_log(failed_log)
        self.transcripts: Dict[str, str] = {}
        self.tr_path = tr_path
        self.done_log = done_log
        self.stats = {STATUS_OK: 0, STATUS_UNK: 0, STATUS_REQ: 0, STATUS_ERR: 0}
        self.lam = rpm or 1000
        self.interval = 60.0 / self.lam if rpm else 0.0
        self.sem = asyncio.Semaphore(min(8, max(1, self.lam // 15)))
        self.lock = asyncio.Lock()
        self._last = 0.0

    async def pace(self):
        if self.interval:
            async with self.lock:
                wait = max(0.0, self._last + self.interval - time.time())
                self._last = max(time.time(), self._last + self.interval)
            if wait:
                await asyncio.sleep(wait)

    def persist(self, result: Result):
        """Record a verdict, then atomically write transcripts.json."""
        name = os.path.basename(result.path)
        if result.ok:
            self.transcripts[name] = result.text
            self.stats[STATUS_OK] += 1
            append_log(self.done_log, name)
        elif result.status == STATUS_UNK:
            self.transcripts[name] = ''
            self.failed.add(name)
            self.stats[STATUS_UNK] += 1
            append_log(os.path.join(os.path.dirname(self.done_log), 'failed.log'),
                       name)
        else:
            self.stats[result.status] += 1
        tmp = self.tr_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(self.transcripts, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, self.tr_path)


def _cut_lines(path: str) -> int:
    n = 0
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            n = sum(1 for _ in fh)
    return n


async def _run(clips: List[str], language: str, rpm: int,
               done_log: str, failed_log: str, tr_path: str,
               progress_every: int = 100):
    tracker = _Tracker(done_log, failed_log, tr_path, language, rpm)
    todo = [c for c in clips if os.path.basename(c)
            not in tracker.done | tracker.failed]

    print(f'  transcribe: {len(todo)} to do ({len(tracker.done)} done, '
          f'{len(tracker.failed)} failed)', flush=True)
    if not todo:
        has_tr = os.path.exists(tr_path)
        if has_tr:
            with open(tr_path, encoding='utf-8') as fh:
                tracker.transcripts = json.load(fh)
        return tracker

    n_total = 0
    t0 = time.time()

    async def process_one(clip: str):
        nonlocal n_total
        await tracker.pace()
        async with tracker.sem:
            result = await transcribe_one(clip, language)
            tracker.persist(result)
            n_total += 1
            if n_total % progress_every == 0:
                s = tracker.stats
                el = (time.time() - t0) / 60
                extra = ''
                if s[STATUS_REQ] or s[STATUS_ERR]:
                    extra = f', {s[STATUS_REQ]} api-fail, {s[STATUS_ERR]} bad-clip'
                print(f'  ... {n_total}/{len(todo)} ({s[STATUS_OK]} ok, '
                      f'{s[STATUS_UNK]} no-speech{extra}, {el:.1f} min)',
                      flush=True)

    await asyncio.gather(*(process_one(c) for c in todo))
    s = tracker.stats
    print(f'  transcribe done: {s[STATUS_OK]} ok, {s[STATUS_UNK]} no-speech, '
          f'{s[STATUS_REQ]} api-fail, {s[STATUS_ERR]} bad-clip, '
          f'{(time.time()-t0)/60:.1f} min', flush=True)
    if s[STATUS_REQ]:
        print('  NOTE: %d clips failed on the API (rate limit/network), not '
              'the audio. They are NOT in failed.log - rerun this stage to '
              'retry them.' % s[STATUS_REQ], flush=True)
    return tracker


def transcribe_folder(folder: str, language: str, rpm: int = 50,
                      ext: str = '.flac') -> Transcripts:
    """Transcribe every ``*{ext}`` file in ``folder``, resumably.

    Crash-safe: transcripts.json (name -> text) plus done.log / failed.log are
    kept next to the audio. Re-running resumes and retries transient failures.
    """
    clips = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                   if f.endswith(ext))
    if not clips:
        raise FileNotFoundError(f'no {ext} files in {folder}')
    tr_path = os.path.join(folder, 'transcripts.json')
    done_log = os.path.join(folder, 'done.log')
    failed_log = os.path.join(folder, 'failed.log')
    tracker = asyncio.run(_run(clips, language, rpm, done_log, failed_log,
                               tr_path))
    return Transcripts(tracker.transcripts, tracker.done, tracker.failed,
                       dict(tracker.stats))