import json
import os
import tempfile
from pathlib import Path

import pytest

from google_asr_africa import transcribe
from google_asr_africa.transcribe import STATUS_ERR, STATUS_OK, STATUS_UNK


def test_load_log_missing_ok(tmp_path):
    assert transcribe.load_log(str(tmp_path / 'nope.log')) == set()


def test_append_and_load_log(tmp_path):
    p = str(tmp_path / 'done.log')
    transcribe.append_log(p, 'a.flac')
    transcribe.append_log(p, 'b.flac')
    assert transcribe.load_log(p) == {'a.flac', 'b.flac'}


def test_transcribe_one_bad_file(tmp_path):
    bad = tmp_path / 'empty.flac'
    bad.write_bytes(b'')
    import asyncio
    res = asyncio.run(transcribe.transcribe_one(str(bad), 'ny'))
    assert res.status == STATUS_ERR
    assert res.ok is False


def test_tracker_unknown_persists(tmp_path):
    done = str(tmp_path / 'done.log')
    failed = str(tmp_path / 'failed.log')
    tr = str(tmp_path / 'transcripts.json')
    tracker = transcribe._Tracker(done, failed, tr, 'ny', rpm=0)
    res = transcribe.Result(str(tmp_path / 'a.flac'), STATUS_UNK)
    tracker.persist(res)
    assert tracker.stats[STATUS_UNK] == 1
    with open(tr) as fh:
        assert json.load(fh) == {'a.flac': ''}


def test_transcribe_folder_no_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        transcribe.transcribe_folder(str(tmp_path), 'ny')