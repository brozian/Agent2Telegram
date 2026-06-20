#!/usr/bin/env bash
# Agent2Telegram one-command installer.
# Usage:  curl -fsSL <raw-url>/install.sh | bash      (or run it from a clone)
# It checks Python, installs the package for the current user, and launches setup.
set -euo pipefail

REPO="https://github.com/petrludwig-collab/Agent2Telegram.git"
NEED_PY_MAJOR=3
NEED_PY_MINOR=10

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# 1) Python check
PY="$(command -v python3 || true)"
[ -n "$PY" ] || err "python3 not found. Install Python ${NEED_PY_MAJOR}.${NEED_PY_MINOR}+ first."
"$PY" - <<'PYEOF' || err "Python ${NEED_PY_MAJOR}.${NEED_PY_MINOR}+ required."
import sys
sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)
PYEOF
say "Using $("$PY" --version)"

# 2) Get the code (clone if we're not already inside it)
if [ -f "pyproject.toml" ] && grep -q "agent2telegram" pyproject.toml 2>/dev/null; then
  SRC="$(pwd)"
  say "Installing from current directory"
else
  command -v git >/dev/null || err "git not found (needed to fetch the project)."
  SRC="${HOME}/.agent2telegram-src"
  if [ -d "$SRC/.git" ]; then say "Updating $SRC"; git -C "$SRC" pull --ff-only
  else say "Cloning into $SRC"; git clone --depth 1 "$REPO" "$SRC"; fi
fi

# 3) Install for the current user (no sudo, no virtualenv required)
say "Installing the package"
"$PY" -m pip install --user --upgrade "$SRC" 2>/dev/null \
  || "$PY" -m pip install --user --break-system-packages --upgrade "$SRC"

# 4) Launch the setup wizard
say "Starting setup…"
exec "$PY" -m agent2telegram setup
