"""A small, robust Telegram Bot API client built on the standard library only.

Why no `python-telegram-bot`? Fewer dependencies means fewer install failures on a
stranger's machine — which is the whole point of this project. We only need a handful
of methods and we want full control over retries and flood-control handling.

Transport notes:
  * We use long polling (``getUpdates``), so the host needs no public IP / webhook —
    it works behind NAT, a home router, or a strict firewall.
  * Every call retries with exponential backoff on transient network/5xx errors and
    honours Telegram's ``429 retry_after`` flood control.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("agent2telegram.telegram")

API_ROOT = "https://api.telegram.org"
#: Telegram rejects text messages longer than 4096 UTF-16 code units. We keep a margin.
MAX_MESSAGE_LEN = 4000


def split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    """Split *text* into Telegram-sized chunks, preferring paragraph then line then
    word boundaries, and hard-splitting only as a last resort. Pure function — tested."""
    text = text or ""
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        # Prefer the latest natural boundary inside the window.
        for sep in ("\n\n", "\n", " "):
            cut = window.rfind(sep)
            if cut > limit * 0.5:        # only if it doesn't waste too much of the window
                break
        else:
            cut = limit                  # no good boundary: hard cut
        cut = cut if cut > 0 else limit
        chunks.append(remaining[:cut].rstrip("\n"))
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token: str, *, max_retries: int = 5, opener=None) -> None:
        if not token or ":" not in token:
            raise TelegramError("Invalid bot token.")
        self._token = token
        self._max_retries = max_retries
        # `opener` is injectable so tests can run without touching the network.
        self._opener = opener or urllib.request.build_opener()

    # ---- low-level ---------------------------------------------------------
    def _call(self, method: str, params: dict | None = None, *, timeout: float = 65) -> dict:
        url = f"{API_ROOT}/bot{self._token}/{method}"
        data = urllib.parse.urlencode(params or {}, doseq=True).encode()
        attempt = 0
        while True:
            attempt += 1
            try:
                req = urllib.request.Request(url, data=data, method="POST")
                with self._opener.open(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                if not body.get("ok"):
                    raise TelegramError(f"{method}: {body.get('description', 'unknown error')}")
                return body["result"]
            except urllib.error.HTTPError as e:
                retry_after = self._retry_after(e)
                if retry_after is not None:
                    log.warning("Flood control on %s, waiting %ss", method, retry_after)
                    time.sleep(retry_after + 0.5)
                    continue                         # do not count flood waits as failures
                if e.code >= 500 and attempt <= self._max_retries:
                    self._backoff(attempt)
                    continue
                raise TelegramError(f"{method}: HTTP {e.code} {e.reason}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                if attempt <= self._max_retries:
                    self._backoff(attempt)
                    continue
                raise TelegramError(f"{method}: {e}") from e

    @staticmethod
    def _retry_after(err: urllib.error.HTTPError) -> int | None:
        if err.code != 429:
            return None
        try:
            payload = json.loads(err.read().decode("utf-8"))
            return int(payload.get("parameters", {}).get("retry_after", 1))
        except Exception:
            return int(err.headers.get("Retry-After", 1) or 1)

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(2 ** attempt, 30))

    # ---- high-level --------------------------------------------------------
    def get_me(self) -> dict:
        return self._call("getMe", timeout=15)

    def get_updates(self, offset: int, *, timeout: int = 50) -> list[dict]:
        # Network timeout must exceed the long-poll timeout, else we'd cancel mid-poll.
        return self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": json.dumps(["message"])},
            timeout=timeout + 15,
        )

    def get_file_path(self, file_id: str) -> str:
        return self._call("getFile", {"file_id": file_id}, timeout=20)["file_path"]

    def download(self, file_path: str, *, timeout: float = 120) -> bytes:
        """Download a file the bot has access to (returned by getFile)."""
        url = f"{API_ROOT}/file/bot{self._token}/{file_path}"
        last = None
        for attempt in range(1, 4):
            try:
                with self._opener.open(urllib.request.Request(url), timeout=timeout) as resp:
                    return resp.read()
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                self._backoff(attempt)
        raise TelegramError(f"download failed: {last}")

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            self._call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=15)
        except TelegramError:
            pass  # purely cosmetic; never let it break a turn

    def send_message(self, chat_id: int, text: str, *, parse_mode: str | None = None) -> None:
        for chunk in split_message(text) or ["(empty response)"]:
            params = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"}
            if parse_mode:
                params["parse_mode"] = parse_mode
            try:
                self._call("sendMessage", params)
            except TelegramError as e:
                # Markdown that Telegram can't parse is a common failure — retry as plain text.
                if parse_mode:
                    log.warning("send failed with parse_mode=%s, retrying as plain text: %s", parse_mode, e)
                    self._call("sendMessage", {k: v for k, v in params.items() if k != "parse_mode"})
                else:
                    raise
