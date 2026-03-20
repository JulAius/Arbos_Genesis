# Arbos (Bittensor)

<p align="center">
  <a href="https://ghuntley.com/loop/">Ralph-loop</a> + Telegram bot. This branch adds <strong>Bittensor</strong> tooling, <strong>public group Q&amp;A</strong>, and the <strong>Chi</strong> knowledge pack.<br>
  Upstream: <a href="https://github.com/JulAius/Arbos_Genesis">JulAius/Arbos_Genesis</a> — clone with <code>-b bittensor</code> for this variant.
</p>

## What this branch adds

| Area | Details |
|------|---------|
| **Chain CLIs** | [agcli](https://github.com/unconst/agcli) (Rust, `~/.cargo/bin`) and [btcli](https://github.com/opentensor/btcli) (Python, install in **`.venv`**). `.arbos-launch.sh` sets `PATH` so both work under pm2. |
| **Wallet lockdown** | Shims in `tools/shims/` block `agcli … wallet` and `btcli` `wallet` / `w` / `wallets`; real binaries stay at `~/.cargo/bin/agcli` and `.venv/bin/btcli` if called without shims. |
| **Chi knowledge** | Submodule `external/Chi` → YAML in `external/Chi/knowledge/`. **Context only**—agents still **run `agcli` / `btcli`** (and docs/web) for real answers; Chi is not the end state. |
| **Data providers** | CLI tools `taostats` (network analytics, miner reports) and `taomarketcap` (TAO price, volume, market cap). Set `TAOSTATS_API_KEY` / `TAOMARKETCAP_API_KEY` in `.env`. Knowledge: `data_providers/knowledge/`. |
| **Telegram** | **`TELEGRAM_PUBLIC_CHAT_IDS`** / **`TELEGRAM_WORKSPACE_GROUP_IDS`**: **members** invoke the agent with **`/arbos`** + question (voice/photo/file need a **caption** starting with `/arbos …`). **Operators** keep normal messages + full **`/`** commands (`TELEGRAM_OWNER_ID` / `TELEGRAM_OWNER_IDS`). Add command **`arbos`** in [@BotFather](https://t.me/BotFather) → Edit bot → Edit commands. Replies are **final text only** unless **`TELEGRAM_STREAMING_UPDATES=true`**. **`GOALS_BACKGROUND_AUTORUN`** defaults **off** when a bot token and group ids are set. Owner: **`/start` in private** first. |
| **Mission fixe** | **`GOAL_TELEGRAM_BITTENSOR.md`** + **`TELEGRAM_QA_FIXED_GOAL=true`** → **`context/goals/1/GOAL.md`** : une mission stable — répondre avec **tous les outils nécessaires**, **spécialisé Bittensor** et **tout l’écosystème** (même texte que le flux **`/arbos`**). **`/start 1`** aligne la boucle Ralph. |
| **Checks** | `./tools/check_agcli.sh`, `./tools/check_btcli.sh`, `./tools/check_data_providers.sh` |
| **Chat log** | **`context/chat/by_user/<id>/`** = fil personnel (réponse alignée sur l’historique de ce user). **`context/chat/group/<chat_id>/`** = miroir **salon** (tous les membres) pour le **contexte** seulement. **`context/chat/*.jsonl`** = journal global Ralph / système. |

`PROMPT.md` documents agent behavior (Chi epistemics, `agcli`/`btcli`, extrinsics → `--help` first).

## The design

Arbos loops a `GOAL.md` through a coding agent step by step; between steps only `STATE.md` persists.

```
                                 ┌────── [GOAL.md] ────────┐
                                 ▼                         │
            ┌──────────┐     ┌───────┐                     │
            │ Telegram │◄───►│ Agent │─────────────────────┘
            └──────────┘     └───────┘
```

Public group messages use a **separate** streaming Q&A path; they do not replace `GOAL.md` unless you wire that in manually.

## Providers

| Priority | Provider | Model (example) | Auth |
|----------|----------|-----------------|------|
| Main or Fallback | **Codex** | `gpt-5.3-codex` | `codex login` |
| Main or Fallback | **Anthropic** | `claude-sonnet-4-6` | `claude login` |
| Main or Fallback | **OpenRouter** | (your model) | API key |
| Main or Fallback | **OpenCode** | `minimax-m2.5-free` | API key |
| Main or Fallback | **Cursor** | `composer-2-fast` | `agent login` |
| Main or Fallback | **Chutes** | `moonshotai/Kimi-K2.5-TEE` | API key |

Set `PROVIDER` and `FALLBACK_PROVIDER` in `.env`. Supported values: `codex`, `anthropic`, `openrouter`, `opencode`, `cursor`, `chutes`.

## Requirements

- One primary + one fallback provider stack (see `.env.example`)
- [Telegram bot token](https://core.telegram.org/bots#how-do-i-create-a-bot), `pm2`, **Python 3.10+**
- **Bittensor (recommended here):** Rust 1.75+ for agcli; `bittensor-cli` in `.venv` via `pip install -e ".[bittensor]"`

## Quick start (bittensor)

```sh
git clone -b bittensor https://github.com/JulAius/Arbos_Genesis.git
cd Arbos_Genesis
git submodule update --init external/Chi

cp .env.example .env
# Edit .env: PROVIDER, FALLBACK_*, tokens, TAU_BOT_TOKEN, TELEGRAM_OWNER_ID
# Optional: TELEGRAM_PUBLIC_CHAT_IDS=-100...  (discussion supergroup if using a channel)
# Optional: TELEGRAM_WORKSPACE_GROUP_IDS=-100...  (Discord-style workspace per supergroup; forum: topic = goal)
# Optional: TELEGRAM_QA_FIXED_GOAL=true — seeds goal #1 from GOAL_TELEGRAM_BITTENSOR.md

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[bittensor]"

# agcli (optional but useful)
# rustup from https://rustup.rs then:
cargo install --git https://github.com/unconst/agcli
./tools/check_agcli.sh
./tools/check_btcli.sh

# Data provider tools (optional)
./tools/check_data_providers.sh

pm2 start .arbos-launch.sh --name arbos
```

1. Open a **private chat** with the bot and send **`/start`** once (registers owner). Arbos writes **`chat_id.txt`** (first line = target for **Restarted.** and Ralph status pings); if **`sendMessage` 400** on boot, check pm2 logs for `telegram=` from Telegram’s API, refresh the id (`tools/telegram_chat_ids.py`), or set **`TELEGRAM_RESTART_PING=false`** to skip the boot ping only.
2. Use **`/goal`**, then **`/start` `<index>`** for the Ralph loop (see commands below).
3. For a **community group**, set `TELEGRAM_PUBLIC_CHAT_IDS`, add the bot, **BotFather → /setprivacy → Disable**, restart pm2.
4. For a **team Ralph workspace** in a supergroup (isolated goals on disk), set **`TELEGRAM_WORKSPACE_GROUP_IDS`** to that group’s id. Prefer **forum** supergroups so each `/goal` creates a **topic** (goal id = `message_thread_id`). **`/clear`** in that chat only wipes that workspace folder.

Install steps for each CLI (Codex, Claude, OpenCode, Cursor) match `.env.example` comments and the upstream README.

## Telegram — operator (owner)

| Command | Description |
|---------|-------------|
| `/start` | Help, or `/start <index>` to run goal #index (workspaces also **auto-start** on `/goal`) |
| `/goal <text>` | Create a goal; **forum** → new topic (first line = title). Workspace groups: loop starts immediately (Discord parity). |
| `/ls` | List goals |
| `/status` [index] | Status (one goal or all) |
| `/pause <index>` | Pause (resume with `/unpause` or `/start`) |
| `/unpause [index]` | Resume; in a forum **goal topic**, index optional |
| `/force [index]` | Run next step immediately (skips inter-step delay) |
| `/delay <index> <delay>` | Delay between steps: seconds, or `2m` / `5min` |
| `/bash <cmd>` | Shell in `context/workspace/<id>/` or repo root (`shell=True`, 120s) |
| `/env` | List keys (prefers **owner DM**); `/env KEY VAL`; `/env -d KEY` |
| `/help` | Contextual help (topic vs main chat) |
| `/model` | In workspace: `workspace.json` model; else queue `.env.pending` |
| `/delete <index>` | Delete goal and its folder |
| `/stop` | Stop all started goals in **this** chat’s workspace (legacy DM/private = all legacy goals) |
| `/clear` | Legacy chat: wipe full `context/`. **Workspace** supergroup: only `context/workspace/<chat_id>/` |
| `/restart` | Touch restart flag (pm2); use outside forum topics |
| `/update` | `git pull` + restart |

## Telegram — canal / groupe (plusieurs membres)

**Objectif du bot dans ces salons :** réponses **précises** sur Bittensor en s’appuyant sur **`agcli` / `btcli`** (et la doc / le web si besoin) ; le pack **Chi** sert seulement de **contexte** (voir `PROMPT.md`).

Renseigne **`TELEGRAM_PUBLIC_CHAT_IDS`** avec les IDs numériques (virgule si plusieurs salons).

### Canal avec commentaires (classique)

Sur Telegram, les abonnés **discutent** sous les posts dans le **groupe de discussion** lié au canal, pas dans le fil du canal lui‑même.

1. Crée le **canal**, active **Commentaires** et le **groupe de discussion** associé.
2. Ajoute le **bot** dans ce **groupe de discussion** (pas seulement dans le canal).
3. [@BotFather](https://t.me/BotFather) → `/setprivacy` → **Disable** pour que le bot voie les messages.
4. Récupère l’ID du **groupe de discussion** (`-100…`) et mets‑le dans `TELEGRAM_PUBLIC_CHAT_IDS`.
5. Redémarre pm2.

### Supergroupe sans canal

1. Crée un supergroupe, ajoute le bot + les membres.
2. Même réglage **privacy** + ID du groupe dans `TELEGRAM_PUBLIC_CHAT_IDS`.

### Règles

- **Membres :** texte ou **vocal** → réponses Bittensor (outils + ton Const-style ; pas conseil financier).
- **Commandes `/` :** **propriétaire** du bot uniquement (voir tableau plus haut).
- **Médias :** photos / fichiers **propriétaire** seulement dans ces salons publics.
- Le propriétaire enregistre le bot avec **`/start` en chat privé** avant toute chose.

## Knowledge base (Chi)

After clone:

```sh
git submodule update --init external/Chi
```

Use **`INDEX.yaml`** to find YAML **for context** only. **Primary grounding:** read-only **`agcli` / `btcli`** (and current docs / web when needed)—not Chi alone.

## How it works

1. Each **step** is one agent CLI invocation with tools.
2. By default, steps run **back-to-back** on success; exponential backoff on repeated failures.
3. **Ralph step control** (only the `/goal` loop; public group chat is already **one reply per message**):
   - **`GOAL_STOP_AFTER_SUCCESS=true`** — after a **successful** step, the goal **terminates** until you **`/start <index>`** again (e.g. after a new message / instruction).
   - **`GOAL_PAUSE_AFTER_EACH_STEP=true`** — après **chaque** étape (succès ou échec), **pause** jusqu’à **`/start <index>`**.
4. Only **`STATE.md`** carries memory between steps for a goal.
5. Telegram streams replies; goal progress also shows in step messages when configured.
6. Graceful shutdown on SIGINT/SIGTERM.

## Configuration

See **`.env.example`**: exactly one `PROVIDER`, one `FALLBACK_PROVIDER`, matching models, and only the secrets you need.

```env
TAU_BOT_TOKEN=...
TELEGRAM_OWNER_ID=...
# TELEGRAM_PUBLIC_CHAT_IDS=-100...
```

## Auto-push

If `AUTO_PUSH=true`, the agent can create `.autopush` to trigger `git commit` + `git push` after a step (see `.env.example`). Excluded: `.env`, `context/`, `logs/`.

---

MIT
