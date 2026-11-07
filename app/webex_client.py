"""Part 4 student implementation."""

import os

import requests

TIMEOUT = 10

WEBEX_API_BASE = "https://webexapis.com/v1"


class WebexClient:
    def __init__(self, token=None, session=None):
        self.token = token or os.environ.get("WEBEX_BOT_TOKEN")
        if not self.token:
            raise PermissionError("WEBEX_BOT_TOKEN is not set")
        self.session = session or requests.Session()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get_me(self):
        """GET /people/me ใช้ตอนเริ่มโปรแกรมเพื่อหา personId ของบอท"""
        response = self.session.get(
            f"{WEBEX_API_BASE}/people/me",
            headers=self.headers,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def get_message(self, message_id):
        response = self.session.get(
            f"{WEBEX_API_BASE}/messages/{message_id}",
            headers=self.headers,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def download_file(self, file_url):
        response = self.session.get(
            file_url,
            headers=self.headers,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.content

    def send_message(self, room_id, text):
        response = self.session.post(
            f"{WEBEX_API_BASE}/messages",
            headers=self.headers,
            json={"roomId": room_id, "text": text},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
