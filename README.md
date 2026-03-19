# Arbos

<p align="center">
  Arbos is a <a href="https://ghuntley.com/loop/">Ralph-loop</a> combined with a Telegram bot.<br>
  It loops a goal through Claude Code, powered by Anthropic with a configurable fallback (OpenRouter or OpenCode).
</p>

## The Design

Arbos loops a `GOAL.md` through a coding agent, step after step, with no memory between steps except `STATE.md`.

```
                                 ┌────── [GOAL.md] ────────┐
                                 ▼                         │
            ┌──────────┐     ┌───────┐                     │
            │ Telegram │◄───►│ Agent │─────────────────────┘
            └──────────┘     └───────┘
```

## Providers

| Priority | Provider | Model | Auth |
|----------|----------|-------|------|
| Primary | **Anthropic** | `claude-sonnet-4-6` | Claude Code Pro (OAuth) |
| Fallback A | **OpenRouter** | `stepfun/step-3.5-flash:free` | API key |
| Fallback B | **OpenCode** | `minimax-m2.5-free` | OpenCode API key |

When the Anthropic quota is exceeded, Arbos automatically switches to the configured fallback. Set `FALLBACK_PROVIDER=openrouter` or `FALLBACK_PROVIDER=opencode` in `.env`. At each new step, it retries Anthropic first.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code): `curl -fsSL https://claude.ai/install.sh | bash` — then `claude login` (Pro auth)
- [Telegram Bot token](https://core.telegram.org/bots#how-do-i-create-a-bot)
- Fallback: [OpenRouter API key](https://openrouter.ai) or [OpenCode CLI](https://opencode.ai) (`curl -fsSL https://opencode.ai/install | bash`) + API key
- Python 3.10+, `pm2`

## Getting started

```sh
# Install Claude Code CLI (required)
curl -fsSL https://claude.ai/install.sh | bash

# Install OpenCode CLI (optional, for FALLBACK_PROVIDER=opencode)
curl -fsSL https://opencode.ai/install | bash

git clone https://github.com/JulAius/arbos_genesis.git
cd arbos_genesis
cp .env.example .env
# Edit .env with your tokens
python3 -m venv .venv && source .venv/bin/activate
pip install -r <(grep -oP '"\K[^"]+' pyproject.toml | head -20) 2>/dev/null || pip install requests httpx uvicorn fastapi pyTelegramBotAPI python-dotenv cryptography
pm2 start .arbos-launch.sh --name arbos
```

## Usage

Send `/goal` to your Telegram bot:

```
/goal
Build a trading system that predicts BTC direction on a 15-minute horizon.
```

### Telegram commands

| Command | Description |
|---------|-------------|
| `/goal <text>` | Set the goal for a slot |
| `/status` | Show current goals and step counts |
| `/pause` / `/resume` | Pause/resume a goal |
| `/restart` | Restart the process via pm2 |
| `/update` | Git pull and restart |
| `/clear` | Reset context and state |

## How it works

1. Each **step** is a single `claude -p` invocation with full tool access
2. Steps run back-to-back on success, with exponential backoff on failure
3. `STATE.md` is the only memory between steps — if it's not written there, it's forgotten
4. The Telegram bot relays operator messages and streams agent responses
5. SIGINT/SIGTERM are handled gracefully — no crash restarts

## Configuration

See `.env.example` for all options:

```env
PROVIDER=anthropic              # primary provider
CLAUDE_MODEL=claude-sonnet-4-6  # primary model

# Fallback A: OpenRouter (Claude Code CLI + OpenRouter)
FALLBACK_PROVIDER=openrouter
FALLBACK_MODEL=stepfun/step-3.5-flash:free
OPENROUTER_API_KEY=sk-or-...    # required for openrouter fallback

# Fallback B: OpenCode (config from .env — opencode.json optional)
FALLBACK_PROVIDER=opencode
FALLBACK_MODEL=minimax-m2.5-free
OPENCODE_API_KEY=...             # required for opencode fallback

TAU_BOT_TOKEN=...               # Telegram bot token
TELEGRAM_OWNER_ID=...           # your Telegram user ID
AUTO_PUSH=true                  # enable agent-triggered auto-push
GITHUB_TOKEN=ghp_...            # GitHub token for auto-push
```

## Auto-push

When `AUTO_PUSH=true`, the agent can trigger a git push by creating a `.autopush` file. This keeps the decision logic in the goal/prompt, not hardcoded in arbos.py.

**How it works:**
1. The agent decides when changes are worth pushing (profitable results, working code, etc.)
2. The agent writes `touch .autopush` or `echo "commit message" > .autopush`
3. After the step, Arbos detects the flag → `git add` → `git commit` → `git push`
4. The flag is consumed (deleted) after processing

The commit message is the content of `.autopush`, or a default `auto: step N goal #X` if empty.

Excluded from auto-push: `.env`, `context/`, `logs/`.

---

MIT
