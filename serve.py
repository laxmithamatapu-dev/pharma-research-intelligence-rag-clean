import contextlib
import json
import os
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"
MAX_QUESTION_CHARS = 2000
MAX_BODY_BYTES = 16384


class Service:
    """Owns one warm pipeline; questions are answered one at a time."""

    def __init__(self, pipeline, log_path):
        self.pipeline = pipeline
        self.log_path = Path(log_path)
        self.lock = threading.Lock()
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.answered = 0
        self.busy = False

    def health(self):
        return {
            "status": "ok",
            "retrieval_mode": self.pipeline.mode,
            "model": self.pipeline.generator.model_name,
            "busy": self.busy,
            "answered": self.answered,
            "started_at": self.started_at,
        }

    def ask(self, question):
        with self.lock:
            self.busy = True
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as log, contextlib.redirect_stdout(log):
                    print(f"\n===== {datetime.now().isoformat(timespec='seconds')} {question}")
                    result = self.pipeline.answer(question)
                self.answered += 1
                return result
            finally:
                self.busy = False


def make_handler(service):

    class Handler(BaseHTTPRequestHandler):

        def _send(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(HTTPStatus.OK, service.health())
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if self.path != "/ask":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"body must be 1-{MAX_BODY_BYTES} bytes"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(HTTPStatus.BAD_REQUEST, {"error": "body must be JSON"})
                return
            question = payload.get("question") if isinstance(payload, dict) else None
            if not isinstance(question, str) or not question.strip():
                self._send(HTTPStatus.BAD_REQUEST, {"error": "field 'question' is required"})
                return
            if len(question) > MAX_QUESTION_CHARS:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"question longer than {MAX_QUESTION_CHARS} characters"})
                return
            result = service.ask(question.strip())
            status = HTTPStatus.INTERNAL_SERVER_ERROR if result.get("error") else HTTPStatus.OK
            self._send(status, result)

        def log_message(self, format, *args):
            sys.stderr.write(f"[serve] {self.address_string()} {format % args}\n")

    return Handler


def main():
    host = os.environ.get("RAG_HOST", "127.0.0.1")
    port = int(os.environ.get("RAG_PORT", "8000"))
    log_path = LOG_DIR / "service.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    with log_path.open("a", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        import app

        pipeline = app.Pipeline()
    print(f"[serve] pipeline loaded in {time.perf_counter() - started:.1f}s (mode={pipeline.mode})", file=sys.stderr, flush=True)

    started = time.perf_counter()
    try:
        pipeline.warm_up()
        print(f"[serve] model warm in {time.perf_counter() - started:.1f}s", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"[serve] model warm-up failed ({exc}); continuing, first answer will load the model", file=sys.stderr, flush=True)

    service = Service(pipeline, log_path)
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"[serve] listening on http://{host}:{port}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
