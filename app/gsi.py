from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from app.gsi_state import GSIStateTracker, GameState


class GSIServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 3000) -> None:
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._listeners: list[Callable[[GameState], None]] = []
        self._connection_listeners: list[Callable[[], None]] = []
        self._state_tracker = GSIStateTracker()
        self.latest_state: GameState | None = None

    def add_listener(self, callback: Callable[[GameState], None]) -> None:
        self._listeners.append(callback)

    def add_connection_listener(self, callback: Callable[[], None]) -> None:
        self._connection_listeners.append(callback)

    def _mark_connected(self) -> None:
        for callback in list(self._connection_listeners):
            try:
                callback()
            except Exception:
                pass

    def _dispatch(self, state: GameState) -> None:
        self.latest_state = state
        for callback in list(self._listeners):
            try:
                callback(state)
            except Exception:
                pass

    def start(self) -> None:
        if self._httpd is not None:
            return

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                outer._mark_connected()
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                    state = outer._state_tracker.state_from_payload(payload)
                    outer._dispatch(state)
                    body = b'{"ok": true}'
                    self.send_response(200)
                except Exception as exc:
                    body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
                    self.send_response(400)

                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args) -> None:
                return

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._httpd = None
