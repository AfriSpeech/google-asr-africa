import json
import os

import pytest

from google_asr_africa import languages


def test_catalog_present():
    rows = languages.catalog()
    assert len(rows) >= 20
    fields = {'code', 'language', 'iso'}
    assert fields <= set(rows[0])


def test_catalog_is_slim():
    for e in languages.catalog():
        assert set(e) <= {'code', 'language', 'iso'}


def test_supported_subset():
    all_codes = {e['code'] for e in languages.catalog()}
    sup = set(languages.supported_codes())
    assert sup and sup <= all_codes


def test_support_code_resolution():
    assert languages.support_code('ny') == 'ny'
    assert languages.support_code('nya') == 'ny'
    assert languages.support_code('amharic') == 'am'
    assert languages.support_code('Twi') == 'ak'
    assert languages.support_code('zz') is None
    assert languages.support_code('rubbish') is None


def test_is_supported_verdicts():
    sup = set(languages.supported_codes())
    for e in languages.catalog():
        assert e['code'] in sup


def test_languages_json_matches_pypackage_data():
    p = os.path.join(os.path.dirname(languages.__file__), 'languages.json')
    assert os.path.exists(p)
    with open(p) as fh:
        assert len(json.load(fh)) == len(languages.catalog())