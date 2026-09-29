"""Serve a built site over HTTP, for phones on the same Wi-Fi.

    audiobook-serve SITE_DIR [--host 0.0.0.0] [--port 8000]

Range requests are the reason this exists instead of `python -m http.server`:
iOS Safari will not play an <audio> source that does not answer with 206.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
    # Safari wants audio/ogg for an Opus stream; audio/opus is not a real type
    ".opus": "audio/ogg", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".json": "application/json; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
    ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
    ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8", ".map": "application/json",
}
NO_CACHE = {".html", ".js", ".mjs", ".css", ".json"}
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")

ROOT = Path(".")


class Handler(BaseHTTPRequestHandler):
    server_version = "make-audiobook/1.0"
    protocol_version = "HTTP/1.1"

    # -- helpers ---------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    def resolve(self) -> Path | None:
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        from urllib.parse import unquote

        rel = unquote(path).lstrip("/")
        target = (ROOT / rel).resolve() if rel else ROOT.resolve()
        try:  # path traversal guard
            target.relative_to(ROOT.resolve())
        except ValueError:
            return None
        if target.is_dir():
            target = target / "index.html"
        return target

    def fail(self, status: HTTPStatus, message: str = "") -> None:
        body = (message or status.phrase).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # -- verbs -----------------------------------------------------------

    def do_HEAD(self) -> None:
        self.serve(head_only=True)

    def do_GET(self) -> None:
        self.serve(head_only=False)

    def serve(self, head_only: bool) -> None:
        target = self.resolve()
        if target is None:
            return self.fail(HTTPStatus.FORBIDDEN)
        if not target.is_file():
            return self.fail(HTTPStatus.NOT_FOUND, f"not found: {self.path}")

        ext = target.suffix.lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        size = target.stat().st_size
        cache = "no-cache" if ext in NO_CACHE else "max-age=86400"

        start, end = 0, size - 1
        partial = False
        rng = self.headers.get("Range")
        if rng:
            m = _RANGE_RE.match(rng.strip())
            if not m:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            first, last = m.group(1), m.group(2)
            if first == "":                      # suffix range: last N bytes
                start = max(0, size - int(last or 0))
            else:
                start = int(first)
                end = int(last) if last else size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            partial = True

        length = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", cache)
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head_only:
            return
        with target.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return  # the player seeked away; normal
                remaining -= len(chunk)


def local_ips() -> list[str]:
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # the address actually used to reach the LAN
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main() -> int:
    global ROOT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site_dir")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    ROOT = Path(args.site_dir).expanduser().resolve()
    if not ROOT.is_dir():
        raise SystemExit(f"{ROOT} is not a directory")
    os.chdir(ROOT)

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        raise SystemExit(f"cannot bind {args.host}:{args.port}: {e.strerror} (try --port)")
    server.daemon_threads = True
    print(f"serving {ROOT}")
    print(f"  http://localhost:{args.port}/")
    for ip in local_ips():
        print(f"  http://{ip}:{args.port}/")
    print("Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
