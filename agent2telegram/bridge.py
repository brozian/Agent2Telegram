"""The bridge: poll Telegram, dispatch each message to the agent, send the reply back.

Concurrency model
-----------------
A single poller thread reads updates and enqueues them. Each chat gets its own worker
thread and queue, so:
  * messages from the *same* chat are processed strictly in order (the agent is never
    hit twice concurrently for one conversation), and
  * different chats run in parallel.

The poller never blocks on a slow agent, so Telegram long-polling keeps flowing and the
bot stays responsive (e.g. to ``/status``) even while a long task runs elsewhere.
"""
from __future__ import annotations

import json
import logging
import queue
import signal
import threading
from pathlib import Path

from . import __version__, adapters
from .config import Config, _state_dir
from .telegram import TelegramClient

log = logging.getLogger("agent2telegram.bridge")

_HELP = (
    "🤖 *Agent2Telegram*\n"
    "Send me a message and I'll pass it to the connected agent.\n\n"
    "Commands:\n"
    "/id — show your Telegram IDs (for the allow-list)\n"
    "/reset — start a fresh conversation\n"
    "/status — bridge status\n"
    "/help — this help"
)


class Bridge:
    def __init__(self, cfg: Config, *, client: TelegramClient | None = None) -> None:
        self.cfg = cfg
        self.tg = client or TelegramClient(cfg.token)
        self.adapter = adapters.build(cfg)
        self._allowed = set(cfg.allowed_user_ids)
        self._stop = threading.Event()
        self._workers: dict[int, "_ChatWorker"] = {}
        self._workers_lock = threading.Lock()
        self._offset_file = _state_dir() / "offset"
        self._started_chats: set[int] = set()   # which chats already have a live conversation

    # ---- lifecycle ---------------------------------------------------------
    def run(self) -> None:
        me = self.tg.get_me()
        log.info("Connected as @%s — agent=%s, authorized users=%s",
                 me.get("username"), self.cfg.agent, sorted(self._allowed) or "(none!)")
        if not self._allowed:
            log.warning("No allowed_user_ids configured — the bot will refuse everyone. "
                        "Message the bot and check /id, then add your id to the config.")
        self._install_signal_handlers()
        offset = self._load_offset()
        while not self._stop.is_set():
            try:
                updates = self.tg.get_updates(offset, timeout=self.cfg.poll_timeout)
            except Exception as e:                       # never let the loop die
                log.error("getUpdates failed: %s", e)
                self._stop.wait(3)
                continue
            for upd in updates:
                offset = max(offset, upd["update_id"] + 1)
                try:
                    self._dispatch(upd)
                except Exception as e:
                    log.exception("dispatch error: %s", e)
            self._save_offset(offset)
        self._shutdown()

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self._stop.set())
            except ValueError:
                pass  # not in main thread (e.g. tests) — caller drives _stop

    def _shutdown(self) -> None:
        log.info("Shutting down…")
        with self._workers_lock:
            for w in self._workers.values():
                w.stop()
        for w in list(self._workers.values()):
            w.join(timeout=5)

    # ---- dispatch ----------------------------------------------------------
    def _dispatch(self, update: dict) -> None:
        msg = update.get("message")
        if not msg or "text" not in msg:
            return
        chat_id = msg["chat"]["id"]
        user = msg.get("from", {})
        user_id = user.get("id")
        text = msg["text"].strip()

        if text.startswith("/"):
            if self._handle_command(chat_id, user_id, text):
                return

        if user_id not in self._allowed:
            log.warning("Refused message from unauthorized user %s (%s)", user_id, user.get("username"))
            self.tg.send_message(
                chat_id,
                "⛔ You're not authorized to use this bot.\n"
                f"Your user id is `{user_id}` — ask the owner to add it.",
                parse_mode="Markdown",
            )
            return

        self._enqueue(chat_id, text)

    def _handle_command(self, chat_id: int, user_id: int | None, text: str) -> bool:
        cmd = text.split()[0].lstrip("/").split("@")[0].lower()
        if cmd in ("start", "help"):
            self.tg.send_message(chat_id, _HELP, parse_mode="Markdown")
            return True
        if cmd == "id":
            self.tg.send_message(
                chat_id, f"user id: `{user_id}`\nchat id: `{chat_id}`", parse_mode="Markdown")
            return True
        if cmd == "status":
            authed = "✅" if user_id in self._allowed else "⛔ (not authorized)"
            self.tg.send_message(
                chat_id,
                f"🤖 Agent2Telegram v{__version__}\nagent: {self.cfg.agent}\nyou: {authed}",
            )
            return True
        if cmd == "reset":
            if user_id in self._allowed:
                self._reset_chat(chat_id)
                self.tg.send_message(chat_id, "🔄 Fresh conversation started.")
            return True
        return False  # not a known command → treat as a normal prompt

    # ---- per-chat workers --------------------------------------------------
    def _enqueue(self, chat_id: int, text: str) -> None:
        with self._workers_lock:
            worker = self._workers.get(chat_id)
            if worker is None:
                worker = _ChatWorker(chat_id, self)
                self._workers[chat_id] = worker
                worker.start()
        worker.submit(text)

    def chat_dir(self, chat_id: int) -> Path:
        return self.cfg.path_workdir() / str(chat_id)

    def _reset_chat(self, chat_id: int) -> None:
        import shutil
        self._started_chats.discard(chat_id)
        d = self.chat_dir(chat_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    def process(self, chat_id: int, text: str) -> None:
        """Run the agent for one message and reply. Runs inside a chat worker thread."""
        self.tg.send_chat_action(chat_id, "typing")
        is_cont = chat_id in self._started_chats
        try:
            reply = self.adapter.run(text, chat_dir=self.chat_dir(chat_id), is_continuation=is_cont)
            self._started_chats.add(chat_id)
        except Exception as e:
            log.error("agent run failed for chat %s: %s", chat_id, e)
            self.tg.send_message(chat_id, f"⚠️ Agent error: {e}")
            return
        self.tg.send_message(chat_id, reply or "(the agent returned no output)")

    # ---- offset persistence ------------------------------------------------
    def _load_offset(self) -> int:
        try:
            return int(json.loads(self._offset_file.read_text())["offset"])
        except Exception:
            return 0

    def _save_offset(self, offset: int) -> None:
        try:
            self._offset_file.parent.mkdir(parents=True, exist_ok=True)
            self._offset_file.write_text(json.dumps({"offset": offset}))
        except OSError as e:
            log.warning("could not persist offset: %s", e)


class _ChatWorker(threading.Thread):
    """Serializes processing for a single chat."""

    def __init__(self, chat_id: int, bridge: Bridge) -> None:
        super().__init__(daemon=True, name=f"chat-{chat_id}")
        self.chat_id = chat_id
        self.bridge = bridge
        self.q: queue.Queue[str | None] = queue.Queue()

    def submit(self, text: str) -> None:
        self.q.put(text)

    def stop(self) -> None:
        self.q.put(None)

    def run(self) -> None:
        while True:
            text = self.q.get()
            if text is None:
                return
            try:
                self.bridge.process(self.chat_id, text)
            except Exception as e:  # belt and braces: a worker must never die silently
                log.exception("worker %s crashed handling a message: %s", self.chat_id, e)
