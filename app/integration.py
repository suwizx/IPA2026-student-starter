"""Part 4 student implementation."""

import logging

from app.core import read_request_file, validate_request
from app.dispatcher import dispatch_request
from app.request_handler import validate_webex_envelope

log = logging.getLogger(__name__)


def process_request(mentioned_people, attachment_path, bot_person_id):
    """Envelope check -> parse YAML once -> validate -> dispatch."""
    error = validate_webex_envelope(
        mentioned_people,
        attachment_path,
        bot_person_id,
    )
    if error is not None:
        return error

    data, error = read_request_file(attachment_path)
    if error is not None:
        return error

    validation = validate_request(data)
    if validation.get("status") != "ok":
        return validation

    try:
        return dispatch_request(data)
    except Exception:  # noqa: BLE001 - always answer in the response contract
        log.exception("dispatch failed")
        return {"status": "error", "result": "backend_failed"}
