"""Generate an OS service unit so the bridge starts on boot and restarts on crash.

Supports systemd (Linux) and launchd (macOS). The unit file is printed to **stdout**
(so it can be redirected to a file) while the install hints go to **stderr** — the classic
Unix split that lets you do:

    python -m agent2telegram service > ~/.config/systemd/user/agent2telegram.service

We never write to system paths ourselves: no sudo, and the user reviews what will run.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .config import config_path


def _python() -> str:
    return sys.executable or "python3"


def systemd_unit() -> str:
    return f"""[Unit]
Description=Agent2Telegram bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={_python()} -m agent2telegram run
Restart=always
RestartSec=5
Environment=AGENT2TELEGRAM_CONFIG={config_path()}

[Install]
WantedBy=default.target
"""


def launchd_plist() -> str:
    home = Path.home()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.agent2telegram.bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_python()}</string><string>-m</string><string>agent2telegram</string><string>run</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>AGENT2TELEGRAM_CONFIG</key><string>{config_path()}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>{home}/Library/Logs/agent2telegram.log</string>
  <key>StandardOutPath</key><string>{home}/Library/Logs/agent2telegram.log</string>
</dict>
</plist>
"""


def print_instructions() -> int:
    def hint(msg: str) -> None:
        print(msg, file=sys.stderr)

    if sys.platform == "darwin":
        target = Path.home() / "Library/LaunchAgents/com.agent2telegram.bridge.plist"
        print(launchd_plist())                       # stdout: the unit
        hint("# launchd plist printed above. Install with:")
        hint(f"#   {_python()} -m agent2telegram service > {target}")
        hint(f"#   launchctl load {target}")
    elif shutil.which("systemctl"):
        target = Path.home() / ".config/systemd/user/agent2telegram.service"
        print(systemd_unit())
        hint("# systemd unit printed above. Install with:")
        hint(f"#   mkdir -p {target.parent}")
        hint(f"#   {_python()} -m agent2telegram service > {target}")
        hint("#   systemctl --user enable --now agent2telegram")
        hint("#   loginctl enable-linger $USER   # keep running after logout")
    else:
        print(systemd_unit())
        hint("# No systemd/launchd detected — run 'python -m agent2telegram run' under your")
        hint("# own supervisor, or use the Docker image (see README).")
    return 0
