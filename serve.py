#!/usr/bin/env python3
"""Static server for ./public with HTTP Range support.

PMTiles fetches byte ranges out of a single large file, which the stdlib
handler does not implement. Everything else is plain static serving.

    python3 serve.py [port]        # default 8000
"""
import os, re, sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".pmtiles": "application/octet-stream"}

    def send_head(self):
        m = RANGE.match(self.headers.get("Range", "") or "")
        if not m:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path) or not os.path.exists(path):
            return super().send_head()

        size = os.path.getsize(path)
        start, end = m.group(1), m.group(2)
        if start == "":                                  # suffix range: bytes=-N
            start, end = max(0, size - int(end)), size - 1
        else:
            start, end = int(start), (int(end) if end else size - 1)
        end = min(end, size - 1)
        if start > end:
            self.send_error(416)
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        self._limit = end - start + 1
        return f

    def copyfile(self, src, dst):
        if getattr(self, "_limit", None) is None:
            return super().copyfile(src, dst)
        left = self._limit
        while left > 0:
            chunk = src.read(min(65536, left))
            if not chunk:
                break
            dst.write(chunk)
            left -= len(chunk)
        self._limit = None

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        if not self.path.endswith(".pmtiles"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(RangeHandler, directory=ROOT)
    print(f"http://localhost:{port}  (ctrl-c to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
