"""``agent2telegram update`` — pull the latest code and restart the running bridge(s).

Mirrors the bridge's install story: the source lives in ``~/.agent2telegram-src`` (the clone the
installer made). We ``git pull`` it, reinstall if it was pip-installed, then restart every running
bridge **on the new code** — preserving each bridge's own ``--config`` so a multi-bridge install
keeps all of its bots. No re-setup, no token re-entry.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import agent2telegram


def _src() -> Path:
    return Path.home() / ".agent2telegram-src"


def _running_bridges() -> list[tuple[str, str | None]]:
    """Each running bridge as (pid, --config path or None). Uses ``ps`` for the full command line
    so it works the same on Linux and macOS."""
    try:
        pids = subprocess.run(["pgrep", "-f", "agent2telegram run"],
                              capture_output=True, text=True).stdout.split()
    except OSError:
        return []
    out = []
    for pid in pids:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", pid],
                             capture_output=True, text=True).stdout.strip()
        if "agent2telegram run" not in cmd:
            continue
        cfg = None
        toks = cmd.split()
        if "--config" in toks:
            i = toks.index("--config")
            if i + 1 < len(toks):
                cfg = toks[i + 1]
        out.append((pid, cfg))
    return out


def _restart(bridges: list[tuple[str, str | None]], src: Path) -> int:
    state = Path.home() / ".local" / "state" / "agent2telegram"
    state.mkdir(parents=True, exist_ok=True)
    log = open(state / "run.log", "a")
    # Run from the refreshed source even if not pip-installed (harmless when it is).
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    restarted = 0
    for pid, cfg in bridges:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (OSError, ValueError):
            pass
        argv = [sys.executable, "-m", "agent2telegram", "run"] + (["--config", cfg] if cfg else [])
        subprocess.Popen(argv, env=env, stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
        restarted += 1
    return restarted


def _backfill_usernames() -> None:
    """Fill in each bridge config's bot @username (non-secret) so other tools — e.g. the Agents
    Monitoring dashboard — can show a 't.me/<bot>' link without ever touching the token."""
    from .config import config_path, load, save
    from .telegram import TelegramClient
    d = config_path().parent
    if not d.is_dir():
        return
    for p in sorted(d.glob("*.json")):
        try:
            cfg = load(p)
        except Exception:
            continue
        if cfg.bot_username:
            continue
        try:
            me = TelegramClient(cfg.token).get_me()
            if me.get("username"):
                cfg.bot_username = me["username"]
                save(cfg, p)
        except Exception:
            pass


def run() -> int:
    src = _src()
    if not (src / ".git").is_dir():
        print(f"No source clone at {src}. Re-run the installer, or update manually "
              "(git pull / pip install -U).")
        return 1
    r = subprocess.run(["git", "-C", str(src), "pull", "--ff-only"], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip()[:400] or "(no output)")
    if r.returncode != 0:
        return 1
    # If running from a pip install (not straight from this clone), reinstall the refreshed code.
    if str(src.resolve()) not in str(Path(agent2telegram.__file__).resolve()):
        if subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", str(src)],
                          capture_output=True).returncode != 0:
            subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                            "--break-system-packages", "--upgrade", str(src)], capture_output=True)
    _backfill_usernames()
    bridges = _running_bridges()
    if bridges:
        n = _restart(bridges, src)
        print(f"✓ Updated and restarted {n} bridge(s) on the new code.")
    else:
        print("✓ Updated. No running bridge found — start one with:  agent2telegram run")
    return 0
