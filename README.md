# Arbos

<p align="center">
  Arbos is a <a href="https://ghuntley.com/loop/">Ralph-loop</a> combined with a Telegram bot.<br>
  It loops a goal through a coding agent CLI, with configurable primary and fallback providers.
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
| Main or Fallback | **Codex** | `gpt-5.3-codex` | `codex login` |
| Main or Fallback | **Anthropic** | `claude-sonnet-4-6` | `claude login` |
| Main or Fallback | **OpenRouter** | `stepfun/step-3.5-flash:free` | API key |
| Main or Fallback | **OpenCode** | `minimax-m2.5-free` | API key |
| Main or Fallback | **Cursor** | `composer-2-fast` | `agent login` |
| Main or Fallback | **Chutes** | `moonshotai/Kimi-K2.5-TEE` | API key |

Arbos lets you choose both:

- the main provider with `PROVIDER=...`
- the fallback provider with `FALLBACK_PROVIDER=...`

Supported values are `codex`, `anthropic`, `openrouter`, `opencode`, `cursor`, and `chutes`.

## Requirements

- [Codex CLI](https://developers.openai.com/codex/) if you use `codex` as main or fallback provider
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) if you use `anthropic` as main or fallback provider
- [OpenCode CLI](https://opencode.ai) if you use `opencode` as main or fallback provider
- [Cursor](https://cursor.com) (installed and logged in) if you use `cursor` as main or fallback provider
- [Telegram Bot token](https://core.telegram.org/bots#how-do-i-create-a-bot)
- API keys if you use `openrouter`, `opencode`, or `chutes`
- Python 3.10+, `pm2`
- **[agcli](https://github.com/unconst/agcli)** (optional but recommended on the `bittensor` branch): Rust 1.75+ and `cargo install --git https://github.com/unconst/agcli` — Bittensor wallet / subnet / chain CLI. `.arbos-launch.sh` prepends `~/.cargo/bin` to `PATH` so the agent sees `agcli` when run under pm2.

## Getting started

```sh
# Install Codex CLI if you use PROVIDER=codex or FALLBACK_PROVIDER=codex
npm install -g codex-cli

# Then authenticate once:
codex login

# Install Claude Code CLI if you use PROVIDER=anthropic or FALLBACK_PROVIDER=anthropic
curl -fsSL https://claude.ai/install.sh | bash

# Then authenticate once:
claude login

# Install OpenCode CLI (optional if using PROVIDER=opencode or FALLBACK_PROVIDER=opencode)
curl -fsSL https://opencode.ai/install | bash

# Install Cursor Agent CLI (optional if using PROVIDER=cursor or FALLBACK_PROVIDER=cursor)
curl https://cursor.com/install -fsS | bash
# Then authenticate once (browser login):
agent login
# Or use CURSOR_API_KEY in .env for key-based auth

# Bittensor / agcli (optional; required for on-chain tooling in prompts on branch bittensor)
# rustup: https://rustup.rs — then:
# cargo install --git https://github.com/unconst/agcli
# ./tools/check_agcli.sh

git clone https://github.com/JulAius/arbos_genesis.git
cd arbos_genesis
cp .env.example .env
# Edit .env:
# - choose one PROVIDER
# - choose one FALLBACK_PROVIDER
# - fill only the credentials you actually need
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

1. Each **step** is a single agent CLI invocation with full tool access
2. Steps run back-to-back on success, with exponential backoff on failure
3. `STATE.md` is the only memory between steps — if it's not written there, it's forgotten
4. The Telegram bot relays operator messages and streams agent responses
5. Goal progress is surfaced through the step status/final step message in Telegram
6. SIGINT/SIGTERM are handled gracefully — no crash restarts

## Configuration

See `.env.example` for the full version. The important rule is:

1. Choose exactly one main provider with `PROVIDER=...`
2. Choose exactly one fallback provider with `FALLBACK_PROVIDER=...`
3. Set the matching model variables
4. Fill only the credentials required by those choices

Example:

```env
PROVIDER=codex
CODEX_MODEL=gpt-5.3-codex

FALLBACK_PROVIDER=opencode
FALLBACK_MODEL=minimax-m2.5-free
OPENCODE_API_KEY=...

TAU_BOT_TOKEN=...
TELEGRAM_OWNER_ID=...
AUTO_PUSH=true
GITHUB_TOKEN=ghp_...
```

Other valid combinations:

- `PROVIDER=anthropic` with `FALLBACK_PROVIDER=openrouter`
- `PROVIDER=codex` with `FALLBACK_PROVIDER=codex`
- `PROVIDER=opencode` with `FALLBACK_PROVIDER=codex`
- `PROVIDER=cursor` with `FALLBACK_PROVIDER=openrouter`
- `PROVIDER=chutes` with `FALLBACK_PROVIDER=opencode`

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
