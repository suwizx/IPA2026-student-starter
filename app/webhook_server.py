"""Part 4 student implementation."""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integration import process_request
from app.webex_client import WEBEX_API_BASE, WebexClient

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 1_000_000


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        data = event.get("data")
        if not isinstance(data, dict):
            return None
        message_id = data.get("id")
        if not isinstance(message_id, str) or not message_id:
            return None

        if data.get("personId") == self.bot_person_id:
            return None

        message = self.client.get_message(message_id)
        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        if not room_id:
            return None

        result = self._process(message)
        self.client.send_message(room_id, json.dumps(result))
        return result

    def _process(self, message):
        files = message.get("files") or []
        mentioned_people = message.get("mentionedPeople")

        if len(files) > 1:
            return {"status": "error", "result": "multiple_attachments"}

        try:
            if not files:
                return self.processor(mentioned_people, None, self.bot_person_id)

            content = self.client.download_file(files[0])
            with TemporaryDirectory() as directory:
                path = Path(directory) / "request.yaml"
                path.write_bytes(content)
                return self.processor(mentioned_people, path, self.bot_person_id)
        except Exception:
            log.exception("request processing failed")
            return {"status": "error", "result": "backend_failed"}


def make_http_handler(submit_event):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            log.info("%s - %s", self.address_string(), format % args)

        def _send_json(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

        def _path(self):
            return self.path.split("?", 1)[0]

        def _not_found(self):
            self._send_json(404, {"status": "error", "result": "not_found"})

        def do_GET(self):
            if self._path() == "/health":
                self._send_json(200, {"status": "ok", "result": "healthy"})
            else:
                self._not_found()

        def do_POST(self):
            if self._path() != "/webhook":
                self._not_found()
                return

            invalid = {"status": "error", "result": "invalid_event"}

            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send_json(400, invalid)
                return
            if length < 1 or length > MAX_BODY_BYTES:
                self._send_json(400, invalid)
                return

            try:
                event = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, invalid)
                return
            if not isinstance(event, dict):
                self._send_json(400, invalid)
                return

            submit_event(event)
            self._send_json(200, {"status": "ok", "result": "accepted"})

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _not_found

    return Handler


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = WebexClient()
    bot_person_id = client.get_me()["id"]
    handler = WebexEventHandler(client, bot_person_id)

    executor = ThreadPoolExecutor(max_workers=1)

    def run(event):
        try:
            handler.handle_event(event)
        except Exception:
            log.exception("event handling failed")

    def submit_event(event):
        executor.submit(run, event)

    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8000"))

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    log.info(
        "bot %s listening on %s:%s (API %s)", bot_person_id, host, port, WEBEX_API_BASE
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        executor.shutdown(wait=False)


if __name__ == "__main__":
    main()
