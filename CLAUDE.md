# Arbos Bittensor — Instructions Claude Code

## Projet
Bot Telegram Bittensor dans `arbos.py` (~5700 lignes). Architecture : monolith avec goal system, workspace isolation, DM isolation, ephemeral goals.

## Auto-amélioration — Deux niveaux

### 1. Findings opérateur (`.claude/FINDINGS.md`)
Bugs, patterns, fixes du code `arbos.py`. Utilisé par les skills Claude Code (`/audit`, `/fix`, etc.).

### 2. Findings runtime (`context/workspace/<cid>/FINDINGS.md`)
Connaissances techniques découvertes par le bot pendant ses interactions (parsing, auth, endpoints, workarounds).
- **Injecté automatiquement** dans le prompt de CHAQUE agent (Cursor, Claude Code, Codex, OpenCode) via `load_prompt()`
- **Auto-incrémenté** : les ephemeral goals `/arbos` écrivent dans STATE.md → `_harvest_ephemeral_knowledge()` dédup + append au FINDINGS.md du workspace
- **Format** : une ligne `- finding` par entrée

**IMPORTANT :** Quand tu découvres un workaround technique, ajoute-le dans le `FINDINGS.md` du workspace concerné, PAS dans `.claude/FINDINGS.md`.

## Skills disponibles
- `/audit` — Audit approfondi, compare avec FINDINGS.md, met à jour
- `/fix [bug-name]` — Corrige les bugs de FINDINGS.md par priorité
- `/improve [domain]` — Amélioration ciblée (dm-routing, concurrency, crash-recovery, streaming, cleanup, prompt)
- `/push` — Commit + push (arbos.py + .claude/ seulement)
- `/status` — État rapide : git, syntaxe, bugs ouverts, taille
- `/trace [flow]` — Trace un flux de bout en bout pour vérifier la cohérence

## Conventions
- **3-way dispatch** : `workspace_id == 0` (legacy), `> 0` (DM), `< 0` (workspace group)
- **Lock discipline** : `_goals_lock` pour les maps, `_claude_semaphore` pour les agents
- **Syntaxe check** : toujours `python3 -c "import py_compile; py_compile.compile('arbos.py', doraise=True)"` après modification
- **Commit style** : anglais, conventional commits (feat/fix/refactor/chore)
- **Ne pas commiter** : context/chat/, context/*/goals/*/STATE.md, logs runtime

## Structure des contextes
```
context/
├── goals/           # Legacy CLI goals (workspace_id=0)
├── workspace/<cid>/ # Workspace groups (cid < 0)
│   ├── goals/<idx>/ # GOAL.md, STATE.md, INBOX.md, runs/
│   ├── GOAL_TELEGRAM_BITTENSOR.md  # Mission template
│   ├── FINDINGS.md  # Runtime findings (auto-incrémenté, injecté dans prompt)
│   └── workspace.json
├── chat/            # Chat logs + DM goals (cid > 0)
│   ├── by_user/<uid>/  # Per-user chatlog
│   ├── group/<cid>/    # Per-group chatlog
│   └── <cid>/goals/<idx>/  # DM goals (workspace_id > 0)
└── tools/           # Shared tools & data providers
```
