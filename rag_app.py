"""Localhost UI server for the court-opinion RAG app."""

from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import court_rag

PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "static"


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


class RagHandler(BaseHTTPRequestHandler):
    server_version = "CourtRAG/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[rag_app] {self.address_string()} - {format % args}")

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        if self.path == "/api/status":
            self._send_json(court_rag.get_status())
            return

        if self.path == "/" or self.path == "/index.html":
            self._send_file(STATIC_DIR / "index.html")
            return

        rel = unquote(self.path.lstrip("/"))
        if rel.startswith("static/"):
            candidate = (PROJECT_ROOT / rel).resolve()
            if STATIC_DIR.resolve() in candidate.parents and candidate.is_file():
                self._send_file(candidate)
                return

        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/index":
                body = self._read_body()
                stats = court_rag.build_index(
                    chunk_size=int(body.get("chunk_size") or court_rag.DEFAULT_CHUNK_WORDS),
                    overlap=int(body.get("overlap") or court_rag.DEFAULT_OVERLAP_WORDS),
                )
                self._send_json({"ok": True, "index": asdict(stats)})
                return

            if self.path == "/api/query":
                body = self._read_body()
                result = court_rag.answer_question(
                    str(body.get("query") or ""),
                    use_index=bool(body.get("use_index", True)),
                    top_k=int(body.get("top_k") or 5),
                )
                self._send_json(asdict(result))
                return
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON request body"}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local court-opinion RAG app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8117)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), RagHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Court-opinion RAG app running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping RAG app.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
