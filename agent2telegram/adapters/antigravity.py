"""Adapter for Google's Antigravity agent CLI (``antigravity``).

Antigravity is newer and its CLI surface is still moving, so the default command here is
a best-effort guess: ``antigravity run "<prompt>"``. If your build differs, override it in
config without touching code:

    "command": ["antigravity", "<your>", "<flags>", "{prompt}"]

Run ``antigravity --help`` to see the exact non-interactive invocation, then set it.
"""
from __future__ import annotations

from .base import Adapter


class AntigravityAdapter(Adapter):
    name = "antigravity"
    label = "Antigravity"
    binary = "antigravity"
    default_command = ["antigravity", "run", "{prompt}"]
    continue_command = ["antigravity", "run", "--continue", "{prompt}"]
