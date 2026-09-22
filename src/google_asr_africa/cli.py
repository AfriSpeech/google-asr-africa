"""CLI: transcribe folders, list verified languages, probe candidates."""
from __future__ import annotations

import argparse
import os
import sys


def _list_languages(args):
    from .languages import catalog
    rows = catalog()
    print(f'{"code":<5} {"iso":<4} {"language":<28}')
    print('-' * 37)
    for e in rows:
        print(f'{e["code"]:<5} {e.get("iso", ""):<4} '
              f'{e.get("language", ""):<28}')


def _transcribe(args):
    from .languages import support_code
    from .transcribe import transcribe_folder

    code = args.language
    if code:
        resolved = support_code(code)
        if not resolved:
            print(f'error: {code!r} is not a verified supported language. '
                  f'Run `google-asr-africa list-languages` to see what is.')
            sys.exit(2)
        code = resolved
    if not os.path.isdir(args.dir):
        print(f'error: not a directory: {args.dir}')
        sys.exit(2)

    print(f'Transcribing {args.dir} in {code} (rpm={args.rpm}, '
          f'ext={args.ext})', flush=True)
    tr = transcribe_folder(args.dir, code, rpm=args.rpm, ext=args.ext)
    print(f'ok={tr.stats.get("ok", 0)} unknown={tr.stats.get("unknown", 0)} '
          f'request={tr.stats.get("request", 0)} '
          f'error={tr.stats.get("error", 0)}')


def _probe(args):
    from .probe import probe_code
    probe_code(args.code, audio=args.audio, out=args.out, verbose=True)


def _serve(args):
    from .server import serve
    serve(args.host, args.port, log=not args.quiet)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='google-asr-africa',
        description='Transcribe African-language speech with Google\'s free '
                    'ASR endpoint.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_list = sub.add_parser('list-languages',
                            help='show the verified catalog')
    p_list.set_defaults(func=_list_languages)

    p_tr = sub.add_parser('transcribe',
                          help='transcribe every audio file in a folder')
    p_tr.add_argument('dir', help='folder of audio files')
    p_tr.add_argument('--language', help='google code / iso / name of a '
                                         'verified language')
    p_tr.add_argument('--rpm', type=int, default=50,
                      help='requests per minute cap (0 = unlimited)')
    p_tr.add_argument('--ext', default='.flac',
                      help='audio extension to transcribe (default .flac)')
    p_tr.set_defaults(func=_transcribe)

    p_probe = sub.add_parser('probe',
                             help='check whether a new language code really '
                                  'works (needs audio)')
    p_probe.add_argument('code', help='google ASR language code, e.g. rg')
    p_probe.add_argument('--audio', help='wav/flac file with real speech in '
                                         'this language')
    p_probe.add_argument('--out', help='csv to append the result to '
                                       '(default asr_support.csv)')
    p_probe.set_defaults(func=_probe)

    p_srv = sub.add_parser('serve',
                           help='start the REST API + browser test UI')
    p_srv.add_argument('--host', default='0.0.0.0')
    p_srv.add_argument('--port', type=int, default=8000)
    p_srv.add_argument('--quiet', action='store_true', help='no startup banner')
    p_srv.set_defaults(func=_serve)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()