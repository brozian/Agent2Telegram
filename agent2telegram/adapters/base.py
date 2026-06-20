"""Agent adapter abstraction.

Every supported agent is a thin adapter over its command-line tool. The bridge is
agent-agnostic: it only knows ``Adapter.run(prompt, chat_dir, is_continuation)``.

Robustness choices:
  * Commands are run via ``subprocess`` with an **argv list** (never ``shell=True``),
    so a message from Telegram can't inject shell syntax.
  * Each run has a hard timeout; a hung agent is killed, not left to block the bridge.
  * Per-chat continuity is achieved with a per-chat working directory plus the agent's
    own "continue last conversation" flag — no fragile session bookkeeping.
  * Default commands are sensible but **overridable in config**, because three external
    CLIs evolve independently and a good tool shouldn't hard-code brittle assumptions.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AdapterError(Exception):
    pass


class Adapter:
    #: Stable identifier used in config (``agent`` field).
    name: str = ""
    #: Human-friendly label for the setup wizard.
    label: str = ""
    #: Executable that must be on PATH.
    binary: str = ""
    #: argv template for the first message of a conversation. ``{prompt}`` is replaced.
    default_command: list[str] = []
    #: argv template for follow-up messages (continue the conversation). Falls back to
    #: ``default_command`` when empty (i.e. the agent has no continue mode).
    continue_command: list[str] = []

    def __init__(self, *, command: list[str] | None = None,
                 continue_command: list[str] | None = None, timeout: int = 600) -> None:
        self._command = command or self.default_command
        self._continue = continue_command or self.continue_command or self._command
        self._timeout = timeout

    # ---- discovery ---------------------------------------------------------
    @classmethod
    def detect(cls) -> bool:
        """True if the agent's binary is available on PATH."""
        return bool(cls.binary) and shutil.which(cls.binary) is not None

    # ---- execution ---------------------------------------------------------
    def build_argv(self, prompt: str, *, is_continuation: bool) -> list[str]:
        template = self._continue if is_continuation else self._command
        return [prompt if tok == "{prompt}" else tok.replace("{prompt}", prompt) for tok in template]

    def run(self, prompt: str, *, chat_dir: Path, is_continuation: bool) -> str:
        chat_dir.mkdir(parents=True, exist_ok=True)
        argv = self.build_argv(prompt, is_continuation=is_continuation)
        try:
            proc = subprocess.run(
                argv,
                cwd=str(chat_dir),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as e:
            raise AdapterError(
                f"'{self.binary}' not found. Is {self.label or self.name} installed and on PATH?"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise AdapterError(f"{self.label or self.name} timed out after {self._timeout}s.") from e

        out = (proc.stdout or "").strip()
        if proc.returncode != 0 and not out:
            err = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
            raise AdapterError(f"{self.label or self.name} failed: {err[:500]}")
        return self.parse_output(out)

    def parse_output(self, stdout: str) -> str:
        """Hook for adapters whose CLI emits structured output. Default: raw text."""
        return stdout
