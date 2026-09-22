"""Zero-dependency REST API for google-asr-africa.

Built on the stdlib ``http.server`` so the container has nothing but Python.

Endpoints
    GET  /health                 -> {"ok": true, "version": "..."}
    GET  /languages              -> [{code, iso, language}, ...]
    GET  /                       -> a small browser UI for trying the API
    POST /transcribe?language=am -> audio bytes in the body -> transcription

The transcriber writes the uploaded bytes to a temp file and runs the same
`transcribe_one` used everywhere else, so statuses and language semantics are
identical to the CLI/library.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, supported, support_code
from .transcribe import STATUS_OK, STATUS_UNK, transcribe_one

_MAX_BODY = 64 * 1024 * 1024  # 64 MB upload cap

_UI = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>google-asr-africa</title>
<style>
:root{--bg:#fbfaf7;--ink:#16130d;--line:#e7e2d8;--accent:#b3540f;--ok:#2f6b3a}
*{box-sizing:border-box}
body{font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--ink);
     max-width:640px;margin:3rem auto;padding:0 1rem}
h1{font-size:1.4rem}
code{background:#efece4;padding:.1em .35em;border-radius:4px}
fieldset{border:1px solid var(--line);border-radius:8px;padding:1rem;margin:1rem 0}
label{display:block;font-weight:600;margin:.6rem 0 .25rem}
select,input[type=file]{width:100%;padding:.5rem;border:1px solid var(--line);
     border-radius:6px;background:#fff;font-size:1rem}
button{margin-top:1rem;padding:.55rem 1.2rem;border:0;border-radius:6px;
      background:var(--accent);color:#fff;font-size:1rem;cursor:pointer}
button:disabled{opacity:.6;cursor:wait}
#result{margin-top:1rem;padding:.8rem;border-radius:8px;white-space:pre-wrap;
       display:none}
#result.ok{background:#eaf6ec;border:1px solid #bcddbf}
#result.err{background:#fdeeee;border:1px solid #eec8c8}
.muted{color:#6b6559;font-size:.85rem}
</style>
</head>
<body>
<h1>google-asr-africa</h1>
<p class="muted">Transcribe African-language speech with Google's free ASR
endpoint. Pick a verified language, upload an audio clip, and get the
transcript. Under the hood this calls <code>POST /transcribe?language=&lt;code&gt;</code>.</p>

<fieldset>
 <label for="lang">Language</label>
 <select id="lang"></select>
 <label for="file">Audio clip</label>
 <input type="file" id="file" accept="audio/*,.flac,.wav,.mp3,.ogg,.webm">
 <button id="go">Transcribe</button>
</fieldset>
<div id="result"></div>

<script>
const langSel=document.getElementById('lang');
const fileIn=document.getElementById('file');
const goBtn=document.getElementById('go');
const res=document.getElementById('result');

fetch('/languages').then(r=>r.json()).then(rows=>{
  rows.forEach(r=>{
    const o=document.createElement('option');
    o.value=r.code;
    o.textContent=`${r.language} (${r.code})`;
    langSel.appendChild(o);
  });
});

goBtn.onclick=async()=>{
  const file=fileIn.files[0];
  if(!file){show('Pick an audio file first.','err');return}
  res.style.display='block';res.className='';
  res.textContent='Transcribing…';
  goBtn.disabled=true;
  try{
    const r=await fetch(`/transcribe?language=${encodeURIComponent(langSel.value)}`,{
      method:'POST',
      headers:{'Content-Type':file.type || 'application/octet-stream'},
      body:file,
    });
    const j=await r.json();
    if(j.status==='ok') show(j.text,'ok');
    else if(j.status==='unknown') show('No intelligible speech detected.','err');
    else show(j.error || j.status,'err');
  }catch(e){show('Request failed: '+e,'err')}
  finally{goBtn.disabled=false}
};

function show(msg,cls){res.className=cls;res.textContent=msg}
</script>
</body>
</html>
"""


def _health() -> bytes:
    return json.dumps({'ok': True, 'version': __version__},
                      ensure_ascii=False).encode()


def _languages() -> bytes:
    return json.dumps(supported(), ensure_ascii=False).encode()


def _transcribe(body: bytes, language: str) -> dict:
    resolved = support_code(language) if language else None
    if not resolved:
        return {'status': 'error', 'error': f'language {language!r} is not '
                                            f'a verified supported language'}
    if not body:
        return {'status': 'error', 'error': 'empty request body'}
    if len(body) > _MAX_BODY:
        return {'status': 'error', 'error': 'request body too large'}
    with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as fh:
        fh.write(body)
        path = fh.name
    try:
        import asyncio
        result = asyncio.run(transcribe_one(path, resolved))
        if result.ok:
            return {'status': 'ok', 'text': result.text, 'language': resolved}
        if result.status == STATUS_UNK:
            return {'status': 'unknown', 'text': None, 'language': resolved}
        return {'status': result.status, 'error': result.text or 'transient '
                'API failure'}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'google-asr-africa/{}'.format(__version__)

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, ctype: str = 'application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        n = int(self.headers.get('Content-Length', '0') or 0)
        if n > _MAX_BODY:
            self._send(413, json.dumps({'status': 'error',
                                        'error': 'request too large'})
                       .encode())
            return b''
        return self.rfile.read(n) if n else b''

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self._send(200, _health())
        elif path == '/languages':
            self._send(200, _languages())
        elif path == '/':
            self._send(200, _UI.encode('utf-8'), 'text/html; charset=utf-8')
        else:
            self._send(404, json.dumps({'status': 'error',
                                        'error': 'not found'}).encode())

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/transcribe':
            self._send(404, json.dumps({'status': 'error',
                                        'error': 'not found'}).encode())
            return
        query = parse_qs(urlparse(self.path).query)
        language = (query.get('language') or [''])[0]
        body = self._read_body()
        if not body:
            return  # _read_body already answered
        self._send(200, json.dumps(_transcribe(body, language),
                                   ensure_ascii=False).encode())


def serve(host: str = '0.0.0.0', port: int = 8000,
          log: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    if log:
        print(f'google-asr-africa {__version__} listening on '
              f'http://{host}:{port}')
        print('  GET  /  (browser UI)    GET /health    GET /languages')
        print('  POST /transcribe?language=<code>  (audio bytes in the body)')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='google-asr-africa serve',
                                 description='REST API + test UI.')
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--quiet', action='store_true', help='no startup banner')
    a = ap.parse_args(argv)
    serve(a.host, a.port, log=not a.quiet)