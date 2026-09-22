"""Smoke tests for the REST server (no network calls to Google)."""
from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from google_asr_africa.server import Handler


@pytest.fixture(scope='module')
def server():
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    yield httpd.server_address[1]
    httpd.shutdown()


def _get(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('GET', path)
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, r.getheader('Content-Type'), body


def test_health(server):
    status, ctype, body = _get(server, '/health')
    assert status == 200
    assert json.loads(body)['ok'] is True


def test_languages(server):
    status, ctype, body = _get(server, '/languages')
    assert status == 200
    data = json.loads(body)
    assert isinstance(data, list) and len(data) >= 20
    assert all('code' in row for row in data)


def test_root_serves_html(server):
    status, ctype, body = _get(server, '/')
    assert status == 200
    assert 'text/html' in ctype
    assert b'google-asr-africa' in body


def test_unknown_path_404(server):
    status, _, body = _get(server, '/nope')
    assert status == 404


def test_post_bad_language(server):
    conn = http.client.HTTPConnection('127.0.0.1', server, timeout=5)
    conn.request('POST', '/transcribe?language=klingon',
                 body=b'\x00\x01\x02', headers={'Content-Type': 'audio/flac'})
    r = conn.getresponse()
    data = json.loads(r.read())
    conn.close()
    assert r.status == 200
    assert data['status'] == 'error'
    assert 'not a verified' in data['error']