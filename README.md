# Agent2Telegram

Talk to your coding agent — **Claude Code**, **Codex**, or **Antigravity** — from **Telegram**.

Agent2Telegram is a tiny, dependency‑free bridge. It long‑polls Telegram for messages from
**you** (and only you), hands each one to the agent CLI of your choice, and sends the reply
back. No public IP, no webhook, no cloud — it runs on your own machine, behind your router.

```
Telegram  ⇄  Agent2Telegram  ⇄  claude / codex / antigravity
```

---

## Why it’s built this way

- **Robust by default** — one bad message never crashes the loop; network errors, Telegram
  flood‑control (`429`), 4096‑char limits and Markdown parse failures are all handled.
- **Secure** — the agent can run code on your machine, so only **allow‑listed Telegram
  users** can drive it. Everyone else is politely refused.
- **Zero install friction** — the core uses **only the Python standard library**. Nothing to
  `pip install` for it to work, which means far fewer “it doesn’t run on my machine” moments.
- **Works behind NAT** — long polling, so no port‑forwarding or domain needed.

---

## Quick start

```bash
# 1) Get the code
git clone https://github.com/petrludwig-collab/Agent2Telegram.git
cd Agent2Telegram

# 2) Run the setup wizard (pick agent → paste token → authorize yourself)
python3 -m agent2telegram setup

# 3) Start the bridge
python3 -m agent2telegram run
```

…or the one‑liner:

```bash
curl -fsSL https://raw.githubusercontent.com/petrludwig-collab/Agent2Telegram/main/install.sh | bash
```

### What the wizard asks
1. **Which agent** — Claude Code, Codex, Antigravity, or a generic CLI. It checks whether the
   binary is on your `PATH`.
2. **Telegram bot token** — create a bot with [@BotFather](https://t.me/BotFather) and paste
   the token. The wizard verifies it live.
3. **Authorize yourself** — send your bot any message; the wizard captures your user id and
   adds it to the allow‑list.

---

## Prerequisites

- **Python 3.10+**
- The agent you want to connect, **installed and logged in**:
  - Claude Code — <https://docs.claude.com/claude-code> (run `claude` once to sign in)
  - Codex — <https://github.com/openai/codex> (run `codex` once to sign in)
  - Antigravity — Google’s agent CLI (set the exact command in config; see below)

The bridge shells out to these tools, so whatever they can do in your terminal, they can do
from Telegram.

---

## Commands (in chat)

| Command | What it does |
|---|---|
| *(any text)* | sent to the agent as a prompt |
| `/reset` | start a fresh conversation |
| `/id` | show your user / chat id (handy for the allow‑list) |
| `/status` | bridge + agent status |
| `/help` | help |

---

## Configuration

Stored at `~/.config/agent2telegram/config.json` (mode `0600`). The token may instead be
provided via the `TELEGRAM_BOT_TOKEN` environment variable to keep it out of the file.

```json
{
  "agent": "claude-code",
  "token": "123456:ABC...",
  "allowed_user_ids": [123456789],
  "agent_timeout": 600,
  "command": null,
  "continue_command": null
}
```

**Custom command** — the default invocation for each agent is overridable, because these CLIs
evolve. Use `{prompt}` where the message should go:

```json
{
  "agent": "codex",
  "command": ["codex", "exec", "--model", "gpt-5.5", "{prompt}"],
  "continue_command": ["codex", "exec", "--last", "{prompt}"]
}
```

Run `python3 -m agent2telegram doctor` to validate everything (config, token, agent binary).

---

## Run it forever (boot + auto‑restart)

```bash
# Prints a systemd unit (Linux) or launchd plist (macOS) to stdout, hints to stderr:
python3 -m agent2telegram service
```

Follow the printed steps. On Linux you’ll typically:

```bash
mkdir -p ~/.config/systemd/user
python3 -m agent2telegram service > ~/.config/systemd/user/agent2telegram.service
systemctl --user enable --now agent2telegram
loginctl enable-linger "$USER"
```

---

## Docker

The image is tiny, but the **agent CLI and its login are not baked in** (auth must stay out of
images). Mount an authenticated agent and your config:

```bash
docker build -t agent2telegram .
docker run -d --name agent2telegram \
  -v "$HOME/.config/agent2telegram:/data" \
  -v "$HOME/.claude:/root/.claude" \      # example: bring your Claude Code login
  agent2telegram
```

---

## Security notes

- **Allow‑list is the only thing between a stranger and code execution on your box.** Keep it
  tight. An unauthorized user gets a refusal and their own id (so you can add them on purpose).
- The bot token is a secret: the config file is `0600`, the token is never logged, and `/status`
  / `doctor` always print it redacted.
- Prompts are passed to the agent as a single `argv` element (never through a shell), so a
  message can’t inject shell syntax.
- Consider running the agent under a dedicated, least‑privileged user.

---

## Development

```bash
python3 -m unittest discover -s tests -v   # zero-dependency test suite
```

## License

MIT — see [LICENSE](LICENSE).
