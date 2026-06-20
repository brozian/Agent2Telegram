"""Adapter for OpenAI's Codex CLI (``codex``).

Uses the non-interactive subcommand: ``codex exec "<prompt>"``. Continuity is handled by
running each chat in its own working directory; pass ``--last`` (resume last session) on
follow-ups where supported. Both commands are overridable in config if your Codex build
uses different flags.

Install / auth: https://github.com/openai/codex  (run ``codex`` once to sign in).
"""
from __future__ import annotations

from .base import Adapter


class CodexAdapter(Adapter):
    name = "codex"
    label = "Codex"
    binary = "codex"
    default_command = ["codex", "exec", "{prompt}"]
    # `codex exec --last` continues the most recent session in the working directory.
    continue_command = ["codex", "exec", "--last", "{prompt}"]
