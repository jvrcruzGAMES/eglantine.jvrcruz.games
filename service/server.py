#!/usr/bin/env python3
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import unquote, urlsplit
from config import DATA, ROOT

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self): self.serve(False)
    def do_HEAD(self): self.serve(True)
    def serve(self, head):
        path = unquote(urlsplit(self.path).path)
        if path == '/api/status':
            state = json.loads((DATA / 'status.json').read_text()) if (DATA / 'status.json').exists() else {'phase':'waiting'}
            release = DATA / 'public/current/release.json'
            state['latest'] = json.loads(release.read_text()) if release.exists() else None
            content = json.dumps(state).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            if not head: self.wfile.write(content)
            return
        if path == '/healthz':
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers()
            if not head: self.wfile.write(b'ok')
            return
        if path in ('/', '/index.html', '/style.css', '/app.js', '/icon.png'):
            base = ROOT / 'web'; relative = 'index.html' if path == '/' else path[1:]
        elif path == '/eglantine-archive-keyring.gpg':
            base = DATA / 'keys'; relative = path[1:]
        elif path.startswith(('/updates/', '/apt/')):
            base = (DATA / 'public/current').resolve(); relative = path[1:]
        elif path.startswith(('/releases/', '/logs/')):
            base = DATA / 'public'; relative = path[1:]
        else: return self.send_error(404)
        base = base.resolve()
        file = (base / relative).resolve()
        if not file.is_relative_to(base) or not file.is_file(): return self.send_error(404)
        size = file.stat().st_size
        ranges = [(0, size - 1)]
        partial = self.headers.get('Range')
        if partial:
            if not partial.startswith('bytes='): return self.range_error(size)
            ranges = []
            for item in partial[6:].split(','):
                match = re.fullmatch(r'\s*(\d*)-(\d*)\s*', item)
                if not match or not any(match.groups()): return self.range_error(size)
                a, b = match.groups()
                if a: start, end = int(a), min(int(b), size - 1) if b else size - 1
                else: start, end = max(0, size - int(b)), size - 1
                if start <= end and start < size: ranges.append((start, end))
            if not ranges: return self.range_error(size)
        mime = self.guess_type(str(file))
        boundary = 'eglantine-' + uuid.uuid4().hex
        multipart = len(ranges) > 1
        def part_header(start, end):
            return (f'--{boundary}\r\nContent-Type: {mime}\r\n'
                    f'Content-Range: bytes {start}-{end}/{size}\r\n\r\n').encode()
        closing = f'--{boundary}--\r\n'.encode()
        length = sum(end-start+1 for start, end in ranges)
        if multipart:
            length += sum(len(part_header(a,b))+2 for a,b in ranges) + len(closing)
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', f'multipart/byteranges; boundary={boundary}' if multipart else mime)
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache' if path.startswith(('/apt/', '/updates/')) else 'public, max-age=300')
        if partial and not multipart:
            start, end = ranges[0]
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if not head:
            try:
                with file.open('rb') as stream:
                    for start, end in ranges:
                        if multipart: self.wfile.write(part_header(start,end))
                        stream.seek(start)
                        remaining = end-start+1
                        while remaining > 0:
                            block = stream.read(min(1024*1024, remaining))
                            if not block: break
                            self.wfile.write(block); remaining -= len(block)
                        if multipart: self.wfile.write(b'\r\n')
                    if multipart: self.wfile.write(closing)
            except (BrokenPipeError, ConnectionResetError): pass
    def range_error(self, size):
        self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.send_header('Content-Length', '0'); self.end_headers()

if __name__ == '__main__':
    ThreadingHTTPServer((os.environ.get('BIND', '0.0.0.0'), int(os.environ.get('PORT', '39402'))), Handler).serve_forever()
