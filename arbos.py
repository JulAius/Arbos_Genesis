import base64
import json
import os
import selectors
import signal
import subprocess
import sys
import time
import threading
import uuid
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

import hashlib
import re

from dotenv import load_dotenv
import httpx
import requests
import uvicorn
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

WORKING_DIR = Path(__file__).parent
PROMPT_FILE = WORKING_DIR / "PROMPT.md"
CONTEXT_DIR = WORKING_DIR / "context"
GOALS_DIR = CONTEXT_DIR / "goals"
GOALS_JSON = CONTEXT_DIR / "goals.json"
WORKSPACES_DIR = CONTEXT_DIR / "workspace"
CHATLOG_DIR = CONTEXT_DIR / "chat"
FILES_DIR = CONTEXT_DIR / "files"
RESTART_FLAG = WORKING_DIR / ".restart"
CHAT_ID_FILE = WORKING_DIR / "chat_id.txt"
ENV_ENC_FILE = WORKING_DIR / ".env.enc"

# ── Encrypted .env ───────────────────────────────────────────────────────────

def _derive_fernet_key(passphrase: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=b"arbos-env-v1", iterations=200_000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def _encrypt_env_file(bot_token: str):
    """Encrypt .env → .env.enc and delete the plaintext file."""
    env_path = WORKING_DIR / ".env"
    plaintext = env_path.read_bytes()
    f = Fernet(_derive_fernet_key(bot_token))
    ENV_ENC_FILE.write_bytes(f.encrypt(plaintext))
    os.chmod(str(ENV_ENC_FILE), 0o600)
    env_path.unlink()


def _decrypt_env_content(bot_token: str) -> str:
    """Decrypt .env.enc and return plaintext (never written to disk)."""
    f = Fernet(_derive_fernet_key(bot_token))
    return f.decrypt(ENV_ENC_FILE.read_bytes()).decode()


def _load_encrypted_env(bot_token: str) -> bool:
    """Decrypt .env.enc, load into os.environ. Returns True on success."""
    if not ENV_ENC_FILE.exists():
        return False
    try:
        content = _decrypt_env_content(bot_token)
    except InvalidToken:
        return False
    for line in content.splitlines():
        line = line.split("#")[0].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    return True


def _save_to_encrypted_env(key: str, value: str):
    """Add/update a single key in the encrypted env file."""
    bot_token = os.environ.get("TAU_BOT_TOKEN", "")
    if not bot_token or not ENV_ENC_FILE.exists():
        return
    try:
        content = _decrypt_env_content(bot_token)
    except InvalidToken:
        return
    lines = content.splitlines()
    updated = False
    for i, line in enumerate(lines):
        stripped = line.split("#")[0].strip()
        if stripped.startswith(f"{key}="):
            lines[i] = f"{key}='{value}'"
            updated = True
            break
    if not updated:
        lines.append(f"{key}='{value}'")
    f = Fernet(_derive_fernet_key(bot_token))
    ENV_ENC_FILE.write_bytes(f.encrypt("\n".join(lines).encode()))
    os.environ[key] = value


ENV_PENDING_FILE = CONTEXT_DIR / ".env.pending"


def _init_env():
    """Load environment from .env (plaintext) or .env.enc (encrypted)."""
    env_path = WORKING_DIR / ".env"

    if env_path.exists():
        load_dotenv(env_path)
        return

    bot_token = os.environ.get("TAU_BOT_TOKEN", "")
    if ENV_ENC_FILE.exists() and bot_token:
        if _load_encrypted_env(bot_token):
            return
        print("ERROR: failed to decrypt .env.enc — wrong TAU_BOT_TOKEN?", file=sys.stderr)
        sys.exit(1)

    if ENV_ENC_FILE.exists() and not bot_token:
        print("ERROR: .env.enc exists but TAU_BOT_TOKEN not set.", file=sys.stderr)
        print("Pass it as an env var: TAU_BOT_TOKEN=xxx python arbos.py", file=sys.stderr)
        sys.exit(1)


def _process_pending_env():
    """Pick up env vars the operator agent wrote to .env.pending and persist them."""
    with _pending_env_lock:
        if not ENV_PENDING_FILE.exists():
            return
        content = ENV_PENDING_FILE.read_text().strip()
        ENV_PENDING_FILE.unlink(missing_ok=True)
        if not content:
            return

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            os.environ[k] = v

        env_path = WORKING_DIR / ".env"
        if env_path.exists():
            with open(env_path, "a") as f:
                f.write("\n" + content + "\n")
        elif ENV_ENC_FILE.exists():
            bot_token = os.environ.get("TAU_BOT_TOKEN", "")
            if bot_token:
                try:
                    existing = _decrypt_env_content(bot_token)
                except InvalidToken:
                    existing = ""
                new_content = existing.rstrip() + "\n" + content + "\n"
                enc = Fernet(_derive_fernet_key(bot_token))
                ENV_ENC_FILE.write_bytes(enc.encrypt(new_content.encode()))

        _reload_env_secrets()
        _log(f"loaded pending env vars from .env.pending")


_init_env()

# ── Redaction ────────────────────────────────────────────────────────────────

_SECRET_KEY_WORDS = {"KEY", "SECRET", "TOKEN", "PASSWORD", "SEED", "CREDENTIAL"}

_SECRET_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'sk_[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'sk-proj-[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'sk-or-v1-[a-fA-F0-9]{20,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{20,}'),
    re.compile(r'gho_[a-zA-Z0-9]{20,}'),
    re.compile(r'hf_[a-zA-Z0-9]{20,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'cpk_[a-zA-Z0-9._\-]{20,}'),
    re.compile(r'crsr_[a-zA-Z0-9]{20,}'),
    re.compile(r'dckr_pat_[a-zA-Z0-9_\-]{10,}'),
    re.compile(r'sn\d+_[a-zA-Z0-9_]{10,}'),
    re.compile(r'tpn-[a-zA-Z0-9_\-]{10,}'),
    re.compile(r'wandb_v\d+_[a-zA-Z0-9]{10,}'),
    re.compile(r'basilica_[a-zA-Z0-9]{20,}'),
    re.compile(r'MT[A-Za-z0-9]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]{20,}'),
]


def _load_env_secrets() -> set[str]:
    """Build redaction blocklist from env vars whose names suggest secrets."""
    secrets = set()
    for key, val in os.environ.items():
        if len(val) < 16:
            continue
        key_upper = key.upper()
        if any(w in key_upper for w in _SECRET_KEY_WORDS):
            secrets.add(val)
    return secrets


_env_secrets: set[str] = _load_env_secrets()


def _reload_env_secrets():
    global _env_secrets
    _env_secrets = _load_env_secrets()


def _get_env_lines_src() -> tuple[list[str], str]:
    """Return (.env lines, 'plain'|'enc'|'none') for list/edit/delete (Discord /env parity)."""
    env_path = WORKING_DIR / ".env"
    if env_path.exists():
        return env_path.read_text().splitlines(), "plain"
    tok = os.environ.get("TAU_BOT_TOKEN", "")
    if ENV_ENC_FILE.exists() and tok:
        try:
            return _decrypt_env_content(tok).splitlines(), "enc"
        except InvalidToken:
            pass
    return [], "none"


def _write_env_lines(lines: list[str], source: str):
    env_path = WORKING_DIR / ".env"
    if source == "plain":
        env_path.write_text("\n".join(lines).rstrip() + "\n")
    elif source == "enc":
        tok = os.environ.get("TAU_BOT_TOKEN", "")
        if not tok:
            raise RuntimeError("TAU_BOT_TOKEN required to update .env.enc")
        enc = Fernet(_derive_fernet_key(tok))
        ENV_ENC_FILE.write_bytes(enc.encrypt(("\n".join(lines).rstrip() + "\n").encode()))


def _list_env_keys_arbos() -> list[str]:
    lines, _ = _get_env_lines_src()
    keys: list[str] = []
    for line in lines:
        stripped = line.split("#")[0].strip()
        if "=" in stripped:
            keys.append(stripped.split("=", 1)[0].strip())
    return keys


def _delete_env_key_arbos(key: str):
    lines, src = _get_env_lines_src()
    if src == "none":
        raise RuntimeError("No .env or .env.enc")
    new_lines = [
        ln for ln in lines
        if not ln.split("#")[0].strip().startswith(f"{key}=")
    ]
    _write_env_lines(new_lines, src)
    os.environ.pop(key, None)


def _workspace_json_path(workspace_id: int) -> Path:
    return WORKSPACES_DIR / str(workspace_id) / "workspace.json"


def _read_workspace_model(workspace_id: int) -> str | None:
    if not workspace_id:
        return None
    p = _workspace_json_path(workspace_id)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        m = d.get("model")
        if isinstance(m, str) and m.strip():
            return m.strip()
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return None


def _redact_secrets(text: str) -> str:
    """Strip known secrets and common key patterns from outgoing text."""
    for secret in _env_secrets:
        if secret in text:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
MAX_CONCURRENT = int(os.environ.get("CLAUDE_MAX_CONCURRENT", "4"))
PROVIDER = os.environ.get("PROVIDER", "chutes")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8089"))
PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "600"))
CHUTES_API_KEY = os.environ.get("CHUTES_API_KEY", "")

if PROVIDER == "anthropic":
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    LLM_API_KEY = ""
    LLM_BASE_URL = ""
    COST_PER_M_INPUT = float(os.environ.get("COST_PER_M_INPUT", "3.00"))
    COST_PER_M_OUTPUT = float(os.environ.get("COST_PER_M_OUTPUT", "15.00"))
    CHUTES_ROUTING_AGENT = CLAUDE_MODEL
    CHUTES_ROUTING_BOT = CLAUDE_MODEL
elif PROVIDER == "openrouter":
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "stepfun/step-3.5-flash:free")
    LLM_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    LLM_BASE_URL = "https://openrouter.ai/api"
    COST_PER_M_INPUT = float(os.environ.get("COST_PER_M_INPUT", "5.00"))
    COST_PER_M_OUTPUT = float(os.environ.get("COST_PER_M_OUTPUT", "25.00"))
    CHUTES_ROUTING_AGENT = CLAUDE_MODEL
    CHUTES_ROUTING_BOT = CLAUDE_MODEL
elif PROVIDER == "codex":
    CLAUDE_MODEL = os.environ.get("CODEX_MODEL", os.environ.get("CLAUDE_MODEL", "gpt-5.3-codex"))
    LLM_API_KEY = ""
    LLM_BASE_URL = ""
    COST_PER_M_INPUT = float(os.environ.get("COST_PER_M_INPUT", "0"))
    COST_PER_M_OUTPUT = float(os.environ.get("COST_PER_M_OUTPUT", "0"))
    CHUTES_ROUTING_AGENT = CLAUDE_MODEL
    CHUTES_ROUTING_BOT = CLAUDE_MODEL
elif PROVIDER == "opencode":
    CLAUDE_MODEL = os.environ.get("OPENCODE_MODEL", os.environ.get("CLAUDE_MODEL", "minimax-m2.5-free"))
    LLM_API_KEY = os.environ.get("OPENCODE_API_KEY", "")
    LLM_BASE_URL = ""
    COST_PER_M_INPUT = float(os.environ.get("COST_PER_M_INPUT", "0"))
    COST_PER_M_OUTPUT = float(os.environ.get("COST_PER_M_OUTPUT", "0"))
    CHUTES_ROUTING_AGENT = CLAUDE_MODEL
    CHUTES_ROUTING_BOT = CLAUDE_MODEL
elif PROVIDER == "cursor":
    CLAUDE_MODEL = os.environ.get("CURSOR_MODEL", os.environ.get("CLAUDE_MODEL", "composer-2-fast"))
    LLM_API_KEY = os.environ.get("CURSOR_API_KEY", "")
    LLM_BASE_URL = ""
    COST_PER_M_INPUT = float(os.environ.get("COST_PER_M_INPUT", "0"))
    COST_PER_M_OUTPUT = float(os.environ.get("COST_PER_M_OUTPUT", "0"))
    CHUTES_ROUTING_AGENT = CLAUDE_MODEL
    CHUTES_ROUTING_BOT = CLAUDE_MODEL
else:
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "moonshotai/Kimi-K2.5-TEE")
    CHUTES_BASE_URL = os.environ.get("CHUTES_BASE_URL", "https://llm.chutes.ai/v1")
    LLM_API_KEY = CHUTES_API_KEY
    LLM_BASE_URL = CHUTES_BASE_URL
    CHUTES_POOL = os.environ.get(
        "CHUTES_POOL",
        "moonshotai/Kimi-K2.5-TEE,zai-org/GLM-5-TEE,MiniMaxAI/MiniMax-M2.5-TEE,zai-org/GLM-4.7-TEE",
    )
    CHUTES_ROUTING_AGENT = os.environ.get("CHUTES_ROUTING_AGENT", f"{CHUTES_POOL}:throughput")
    CHUTES_ROUTING_BOT = os.environ.get("CHUTES_ROUTING_BOT", f"{CHUTES_POOL}:latency")
    COST_PER_M_INPUT = float(os.environ.get("COST_PER_M_INPUT", "0.14"))
    COST_PER_M_OUTPUT = float(os.environ.get("COST_PER_M_OUTPUT", "0.60"))
IS_ROOT = os.getuid() == 0
MAX_RETRIES = int(os.environ.get("CLAUDE_MAX_RETRIES", "5"))
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "3600"))

FALLBACK_PROVIDER = os.environ.get("FALLBACK_PROVIDER", "openrouter")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "stepfun/step-3.5-flash:free")
if FALLBACK_PROVIDER == "openrouter":
    FALLBACK_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
elif FALLBACK_PROVIDER == "cursor":
    FALLBACK_API_KEY = os.environ.get("CURSOR_API_KEY", "")
else:
    FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", "")
FALLBACK_BASE_URL = "https://openrouter.ai/api" if FALLBACK_PROVIDER == "openrouter" else os.environ.get("FALLBACK_BASE_URL", "")

AUTO_PUSH = os.environ.get("AUTO_PUSH", "").lower() in ("1", "true", "yes")
GOAL_PAUSE_AFTER_EACH_STEP = os.environ.get("GOAL_PAUSE_AFTER_EACH_STEP", "").lower() in (
    "1",
    "true",
    "yes",
)
GOAL_STOP_AFTER_SUCCESS = os.environ.get("GOAL_STOP_AFTER_SUCCESS", "").lower() in (
    "1",
    "true",
    "yes",
)
TELEGRAM_QA_FIXED_GOAL = os.environ.get("TELEGRAM_QA_FIXED_GOAL", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
AUTO_PUSH_REMOTE = os.environ.get("AUTO_PUSH_REMOTE", "origin")
AUTO_PUSH_BRANCH = os.environ.get("AUTO_PUSH_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

_provider_lock = threading.Lock()
_using_fallback = False

_tls = threading.local()
_log_lock = threading.Lock()
_chatlog_lock = threading.Lock()
_outbox_lock = threading.Lock()
_pending_env_lock = threading.Lock()
_shutdown = threading.Event()
_claude_semaphore = threading.Semaphore(MAX_CONCURRENT)
_step_count = 0
_token_usage = {"input": 0, "output": 0}
_token_lock = threading.Lock()
_child_procs: set[subprocess.Popen] = set()
_child_procs_lock = threading.Lock()


# ── Multi-goal state ────────────────────────────────────────────────────────


@dataclass
class GoalState:
    index: int
    summary: str = ""
    delay: int = 0
    started: bool = False
    paused: bool = False
    force_next: bool = False
    step_count: int = 0
    goal_hash: str = ""
    last_run: str = ""
    last_finished: str = ""
    thread: threading.Thread | None = field(default=None, repr=False)
    wake: threading.Event = field(default_factory=threading.Event, repr=False)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)


_goals: dict[int, GoalState] = {}
_goals_lock = threading.Lock()

# Telegram “Discord-like” workspaces: one map per supergroup chat_id (negative int).
_tg_workspace_goals: dict[int, dict[int, GoalState]] = {}


def _goal_dir(index: int, workspace_id: int = 0) -> Path:
    if workspace_id == 0:
        return GOALS_DIR / str(index)
    return WORKSPACES_DIR / str(workspace_id) / "goals" / str(index)


def _goals_json_path(workspace_id: int) -> Path:
    if workspace_id == 0:
        return GOALS_JSON
    return WORKSPACES_DIR / str(workspace_id) / "goals.json"


def _tg_goals_map(workspace_id: int) -> dict[int, GoalState]:
    if workspace_id not in _tg_workspace_goals:
        _tg_workspace_goals[workspace_id] = {}
    return _tg_workspace_goals[workspace_id]


def _goal_file(index: int, workspace_id: int = 0) -> Path:
    return _goal_dir(index, workspace_id) / "GOAL.md"


def _state_file(index: int, workspace_id: int = 0) -> Path:
    return _goal_dir(index, workspace_id) / "STATE.md"


def _inbox_file(index: int, workspace_id: int = 0) -> Path:
    return _goal_dir(index, workspace_id) / "INBOX.md"


def _outbox_file(index: int, workspace_id: int = 0) -> Path:
    if index:
        return _goal_dir(index, workspace_id) / "OUTBOX.md"
    return CONTEXT_DIR / "OUTBOX.md"


def _goal_runs_dir(index: int, workspace_id: int = 0) -> Path:
    return _goal_dir(index, workspace_id) / "runs"


def _step_msg_file(index: int, workspace_id: int = 0) -> Path:
    return _goal_dir(index, workspace_id) / ".step_msg"


def _goal_ctx_rel_path(goal_index: int, workspace_id: int = 0) -> str:
    if workspace_id == 0:
        return f"context/goals/{goal_index}/"
    return f"context/workspace/{workspace_id}/goals/{goal_index}/"


def _serialize_goal_entry(gs: GoalState) -> dict[str, Any]:
    return {
        "summary": gs.summary,
        "delay": gs.delay,
        "started": gs.started,
        "paused": gs.paused,
        "force_next": gs.force_next,
        "step_count": gs.step_count,
        "goal_hash": gs.goal_hash,
        "last_run": gs.last_run,
        "last_finished": gs.last_finished,
    }


def _save_goals(workspace_id: int = 0):
    """Persist goal metadata for legacy (0) or a Telegram workspace supergroup. Caller must hold _goals_lock."""
    if workspace_id == 0:
        goals_map = _goals
        jf = GOALS_JSON
    else:
        goals_map = _tg_goals_map(workspace_id)
        jf = _goals_json_path(workspace_id)
    data = {str(idx): _serialize_goal_entry(gs) for idx, gs in goals_map.items()}
    jf.parent.mkdir(parents=True, exist_ok=True)
    jf.write_text(json.dumps(data, indent=2))


def _load_goals_json_into(workspace_id: int, goals_map: dict[int, GoalState]):
    jf = _goals_json_path(workspace_id)
    if not jf.exists():
        return
    try:
        data = json.loads(jf.read_text())
    except (json.JSONDecodeError, OSError):
        return
    for idx_str, info in data.items():
        idx = int(idx_str)
        if not _goal_file(idx, workspace_id).exists():
            continue
        goals_map[idx] = GoalState(
            index=idx,
            summary=info.get("summary", ""),
            delay=info.get("delay", 0),
            started=info.get("started", False),
            paused=info.get("paused", False),
            force_next=info.get("force_next", False),
            step_count=info.get("step_count", 0),
            goal_hash=info.get("goal_hash", ""),
            last_run=info.get("last_run", ""),
            last_finished=info.get("last_finished", ""),
        )


def _load_goals():
    """Load goal metadata: legacy context/goals + configured Telegram workspace dirs."""
    global _goals
    _load_goals_json_into(0, _goals)
    allowed = _telegram_workspace_group_ids_from_env()
    if not allowed or not WORKSPACES_DIR.exists():
        return
    for ws_dir in sorted(WORKSPACES_DIR.iterdir()):
        if not ws_dir.is_dir():
            continue
        try:
            ws_id = int(ws_dir.name)
        except ValueError:
            continue
        if ws_id not in allowed:
            continue
        jf = ws_dir / "goals.json"
        if not jf.exists() and not (ws_dir / "goals").exists():
            continue
        gmap = _tg_goals_map(ws_id)
        _load_goals_json_into(ws_id, gmap)


def _total_registered_goals() -> int:
    n = len(_goals)
    for g in _tg_workspace_goals.values():
        n += len(g)
    return n


TELEGRAM_QA_GOAL_TEMPLATE = WORKING_DIR / "GOAL_TELEGRAM_BITTENSOR.md"


def _telegram_qa_fixed_goal_markdown() -> str:
    if TELEGRAM_QA_GOAL_TEMPLATE.is_file():
        return TELEGRAM_QA_GOAL_TEMPLATE.read_text().strip()
    return (
        "# Mission fixe — Telegram Bittensor\n\n"
        "À chaque demande : répondre avec **tous les outils nécessaires**, **spécialisé Bittensor** et l’**écosystème complet** "
        "(CLI, docs, web, Chi en contexte seulement). **`/arbos` :** réponse **en français**. "
        "Voir **`GOAL_TELEGRAM_BITTENSOR.md`** pour le texte de référence.\n"
    )


def _ensure_telegram_qa_fixed_goal():
    """Seed goal #1 from GOAL_TELEGRAM_BITTENSOR.md when TELEGRAM_QA_FIXED_GOAL is set."""
    if not TELEGRAM_QA_FIXED_GOAL:
        return
    idx = 1
    gdir = _goal_dir(idx)
    gdir.mkdir(parents=True, exist_ok=True)
    _goal_runs_dir(idx).mkdir(parents=True, exist_ok=True)
    gf = _goal_file(idx)
    body = _telegram_qa_fixed_goal_markdown()
    if not gf.exists() or not gf.read_text().strip():
        gf.write_text(body.rstrip() + "\n")
        _log(f"TELEGRAM_QA_FIXED_GOAL: seeded context/goals/{idx}/GOAL.md from template")
    if not _state_file(idx).exists():
        _state_file(idx).write_text("")
    if not _inbox_file(idx).exists():
        _inbox_file(idx).write_text("")
    summary = "Bittensor : outils complets + écosystème (mission fixe)"
    with _goals_lock:
        if idx not in _goals:
            _goals[idx] = GoalState(index=idx, summary=summary)
            _save_goals()
            _log(f"TELEGRAM_QA_FIXED_GOAL: registered goal #{idx} in goals.json")


def _format_last_time(iso_ts: str) -> str:
    if not iso_ts:
        return "never"
    try:
        dt = datetime.fromisoformat(iso_ts)
        secs = (datetime.now() - dt).total_seconds()
        if secs < 60:
            return f"{int(secs)}s ago"
        if secs < 3600:
            return f"{int(secs / 60)}m ago"
        if secs < 86400:
            return f"{int(secs / 3600)}h ago"
        return f"{int(secs / 86400)}d ago"
    except (ValueError, TypeError):
        return "unknown"


def _goal_status_label(gs: GoalState) -> str:
    if gs.started and not gs.paused:
        return "running"
    if gs.started and gs.paused:
        return "paused"
    return "stopped"


def _file_log(msg: str):
    fh = getattr(_tls, "log_fh", None)
    if fh:
        with _log_lock:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"{ts}  {_redact_secrets(msg)}\n")
            fh.flush()


def _log(msg: str, *, blank: bool = False):
    safe = _redact_secrets(msg)
    if blank:
        print(flush=True)
    print(safe, flush=True)
    _file_log(safe)


def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def _reset_tokens():
    with _token_lock:
        _token_usage["input"] = 0
        _token_usage["output"] = 0


def _get_tokens() -> tuple[int, int]:
    with _token_lock:
        return _token_usage["input"], _token_usage["output"]


def fmt_tokens(inp: int, out: int, elapsed: float = 0) -> str:
    def _k(n: int) -> str:
        return f"{n / 1000:.1f}k" if n >= 1000 else str(n)
    tps = ""
    if elapsed > 0 and out > 0:
        tps = f" | {out / elapsed:.0f} t/s"
    cost = (inp * COST_PER_M_INPUT + out * COST_PER_M_OUTPUT) / 1_000_000
    cost_str = f" | ${cost:.4f}" if cost >= 0.0001 else ""
    return f"{_k(inp)} in / {_k(out)} out{tps}{cost_str}"


# ── Prompt helpers ───────────────────────────────────────────────────────────

def load_prompt(goal_index: int, consume_inbox: bool = False, goal_step: int = 0, workspace_id: int = 0) -> str:
    """Build full prompt: PROMPT.md + goal's GOAL/STATE/INBOX + chatlog."""
    parts = []
    if PROMPT_FILE.exists():
        text = PROMPT_FILE.read_text().strip()
        if text:
            parts.append(text)
    gf = _goal_file(goal_index, workspace_id)
    if gf.exists():
        goal_text = gf.read_text().strip()
        if goal_text:
            header = f"## Goal #{goal_index} (step {goal_step})" if goal_step else f"## Goal #{goal_index}"
            rel = _goal_ctx_rel_path(goal_index, workspace_id)
            parts.append(
                f"{header}\n\n{goal_text}\n\nYour context files are in {rel} (STATE.md, INBOX.md, runs/).",
            )
    sf = _state_file(goal_index, workspace_id)
    if sf.exists():
        state_text = sf.read_text().strip()
        if state_text:
            parts.append(f"## State\n\n{state_text}")
    inf = _inbox_file(goal_index, workspace_id)
    if inf.exists():
        inbox_text = inf.read_text().strip()
        if inbox_text:
            parts.append(f"## Inbox\n\n{inbox_text}")
        if consume_inbox:
            inf.write_text("")
    chatlog = load_chatlog()
    if chatlog:
        parts.append(chatlog)
    return "\n\n".join(parts)


def make_run_dir(goal_index: int = 0, workspace_id: int = 0) -> Path:
    if goal_index:
        runs_dir = _goal_runs_dir(goal_index, workspace_id)
    else:
        runs_dir = GOALS_DIR / "_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _rolling_chatlog_append_locked(base: Path, record: dict) -> None:
    """Append one JSON line under ``base/``; rotate tiny files. Caller must hold ``_chatlog_lock``."""
    max_file_size = 4000
    max_files = 50
    base.mkdir(parents=True, exist_ok=True)
    existing = sorted(base.glob("*.jsonl"))
    current: Path | None = None
    if existing and existing[-1].stat().st_size < max_file_size:
        current = existing[-1]
    if current is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        current = base / f"{ts}.jsonl"
    with open(current, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    all_files = sorted(base.glob("*.jsonl"))
    for old in all_files[:-max_files]:
        old.unlink(missing_ok=True)


def log_chat(
    role: str,
    text: str,
    *,
    telegram_user_id: int | None = None,
    telegram_shared_room_id: int | None = None,
):
    """Append to per-user log and/or shared group log and/or global legacy log.

    - ``by_user/<id>/`` when ``telegram_user_id`` is set.
    - ``group/<chat_id>/`` when ``telegram_shared_room_id`` is set (same lines, tagged with ``from_user_id``).
    - ``context/chat/*.jsonl`` only when both user and room are unset (Ralph / system).
    """
    ts = datetime.now().isoformat()
    text_red = _redact_secrets(text[:1000])
    with _chatlog_lock:
        CHATLOG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"role": role, "text": text_red, "ts": ts}
        if telegram_user_id is not None:
            _rolling_chatlog_append_locked(CHATLOG_DIR / "by_user" / str(telegram_user_id), rec)
        else:
            _rolling_chatlog_append_locked(CHATLOG_DIR, rec)
        if telegram_shared_room_id is not None:
            gr = {**rec}
            if telegram_user_id is not None:
                gr["from_user_id"] = telegram_user_id
            _rolling_chatlog_append_locked(
                CHATLOG_DIR / "group" / str(telegram_shared_room_id),
                gr,
            )


def load_chatlog_group(max_chars: int = 3000, *, telegram_chat_id: int) -> str:
    """Recent bot/user turns mirrored from this Telegram group (all members)."""
    root = CHATLOG_DIR / "group" / str(telegram_chat_id)
    header = f"## Salon Telegram (chat_id={telegram_chat_id} — tous les membres, ordre récent)\n\n"
    if not root.exists():
        return ""
    files = sorted(root.glob("*.jsonl"))
    if not files:
        return ""

    lines: list[str] = []
    total = 0
    for f in reversed(files):
        for raw in reversed(f.read_text().strip().splitlines()):
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            uid = msg.get("from_user_id", "?")
            entry = f"[{msg.get('ts', '?')[:16]}] uid={uid} {msg['role']}: {msg['text']}"
            if total + len(entry) > max_chars:
                lines.reverse()
                return header + "\n".join(lines)
            lines.append(entry)
            total += len(entry) + 1

    lines.reverse()
    if not lines:
        return ""
    return header + "\n".join(lines)


def load_chatlog(max_chars: int = 8000, *, telegram_user_id: int | None = None) -> str:
    """Load recent Telegram chat history (per-user dir or global legacy log)."""
    if telegram_user_id is not None:
        root = CHATLOG_DIR / "by_user" / str(telegram_user_id)
        header = f"## Recent Telegram chat (user_id={telegram_user_id})\n\n"
    else:
        root = CHATLOG_DIR
        header = "## Recent Telegram chat (global)\n\n"

    if not root.exists():
        return ""
    files = sorted(root.glob("*.jsonl"))
    if not files:
        return ""

    lines: list[str] = []
    total = 0
    for f in reversed(files):
        for raw in reversed(f.read_text().strip().splitlines()):
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            entry = f"[{msg.get('ts', '?')[:16]}] {msg['role']}: {msg['text']}"
            if total + len(entry) > max_chars:
                lines.reverse()
                return header + "\n".join(lines)
            lines.append(entry)
            total += len(entry) + 1

    lines.reverse()
    if not lines:
        return ""
    return header + "\n".join(lines)


# ── Step update helpers ──────────────────────────────────────────────────────


def _telegram_read_chat_id_file() -> str:
    """First non-empty, non-comment line from chat_id.txt (extra lines / notes must not break sends)."""
    if not CHAT_ID_FILE.exists():
        return ""
    for line in CHAT_ID_FILE.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def _telegram_api_chat_id(chat_id: str) -> int | str:
    """Numeric ids as int for sendMessage (Telegram accepts str too; int avoids odd 400s)."""
    s = (chat_id or "").strip()
    if not s:
        return s
    if s.startswith("-") and s[1:].isdigit():
        return int(s)
    if s.isdigit():
        return int(s)
    return s


def _log_telegram_request_error(where: str, exc: BaseException) -> None:
    base = str(exc)[:500]
    extra = ""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            j = resp.json()
            extra = f" | telegram={j.get('description', resp.text[:400])}"
        except Exception:
            extra = f" | body={resp.text[:400]!r}"
    _log(f"{where}: {base}{extra}")


def _step_update_target() -> tuple[str, str] | None:
    token = os.getenv("TAU_BOT_TOKEN")
    if not token:
        _log("step update skipped: TAU_BOT_TOKEN not set")
        return None
    if not CHAT_ID_FILE.exists():
        _log("step update skipped: chat_id.txt not found")
        return None
    chat_id = _telegram_read_chat_id_file()
    if not chat_id:
        _log("step update skipped: empty chat_id.txt")
        return None
    return token, chat_id


def _telegram_step_target(workspace_id: int = 0) -> tuple[str, str] | None:
    """Telegram (token, chat_id) for goal-step status messages: DM/file chat_id or workspace supergroup id."""
    token = os.getenv("TAU_BOT_TOKEN")
    if not token:
        _log("step update skipped: TAU_BOT_TOKEN not set")
        return None
    if workspace_id != 0:
        return token, str(workspace_id)
    return _step_update_target()


def _md_to_telegram_html(text: str) -> str:
    """Convert standard Markdown (from LLM output) to Telegram-compatible HTML.

    Handles: **bold**, *italic*, `code`, ```code blocks```, [links](url).
    Escapes <, >, & in plain text. Falls through gracefully on edge cases.
    """
    import html as _html

    result = []
    i = 0
    n = len(text)

    while i < n:
        # Fenced code blocks: ```...```
        if text[i:i+3] == '```':
            end = text.find('```', i + 3)
            if end != -1:
                block = text[i+3:end]
                # Strip optional language hint on first line
                if block and block[0] != '\n' and '\n' in block:
                    first_nl = block.index('\n')
                    lang = block[:first_nl].strip()
                    code = block[first_nl+1:]
                    if lang and lang.isalpha():
                        result.append(f'<pre><code class="language-{_html.escape(lang)}">{_html.escape(code)}</code></pre>')
                    else:
                        result.append(f'<pre>{_html.escape(block)}</pre>')
                else:
                    result.append(f'<pre>{_html.escape(block.strip(chr(10)))}</pre>')
                i = end + 3
                continue
            # No closing ``` — treat as plain text
            result.append(_html.escape('```'))
            i += 3
            continue

        # Inline code: `...`
        if text[i] == '`':
            end = text.find('`', i + 1)
            if end != -1 and '\n' not in text[i+1:end]:
                result.append(f'<code>{_html.escape(text[i+1:end])}</code>')
                i = end + 1
                continue

        # Bold: **...**
        if text[i:i+2] == '**':
            end = text.find('**', i + 2)
            if end != -1:
                inner = _md_to_telegram_html(text[i+2:end])
                result.append(f'<b>{inner}</b>')
                i = end + 2
                continue

        # Italic: *...*  (single, not double)
        if text[i] == '*' and (i + 1 < n and text[i+1] != '*'):
            end = text.find('*', i + 1)
            if end != -1 and text[end-1:end+1] != '**':
                inner = _md_to_telegram_html(text[i+1:end])
                result.append(f'<i>{inner}</i>')
                i = end + 1
                continue

        # Links: [text](url)
        if text[i] == '[':
            bracket_end = text.find(']', i + 1)
            if bracket_end != -1 and bracket_end + 1 < n and text[bracket_end + 1] == '(':
                paren_end = text.find(')', bracket_end + 2)
                if paren_end != -1:
                    link_text = _html.escape(text[i+1:bracket_end])
                    url = text[bracket_end+2:paren_end]
                    result.append(f'<a href="{_html.escape(url)}">{link_text}</a>')
                    i = paren_end + 1
                    continue

        # Plain character — escape HTML
        result.append(_html.escape(text[i]))
        i += 1

    return ''.join(result)


def _send_telegram_text(text: str, *, chat_id: int | None = None, target: tuple[str, str] | None = None) -> bool:
    if target is None and chat_id is not None:
        token = os.getenv("TAU_BOT_TOKEN")
        target = (token, str(chat_id)) if token else None
    target = target or _step_update_target()
    if not target:
        return False
    token, chat_id_raw = target
    cid = _telegram_api_chat_id(chat_id_raw)
    text = _redact_secrets(text)
    html_text = _md_to_telegram_html(text)[:4000]
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": html_text, "parse_mode": "HTML"},
            timeout=15,
        )
        if response.status_code == 400:
            # Malformed HTML — fallback to plain text
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "text": text[:4000]},
                timeout=15,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        _log_telegram_request_error("telegram send failed", exc)
        return False
    log_chat("bot", text[:1000])
    _log("telegram message sent")
    return True


def _send_telegram_new(text: str, *, target: tuple[str, str] | None = None) -> int | None:
    """Send a new Telegram message and return its message_id."""
    target = target or _step_update_target()
    if not target:
        return None
    token, chat_id_raw = target
    cid = _telegram_api_chat_id(chat_id_raw)
    text = _redact_secrets(text)
    html_text = _md_to_telegram_html(text)[:4000]
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": html_text, "parse_mode": "HTML"},
            timeout=15,
        )
        if response.status_code == 400:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "text": text[:4000]},
                timeout=15,
            )
        response.raise_for_status()
        log_chat("bot", text[:1000])
        return response.json().get("result", {}).get("message_id")
    except requests.RequestException as exc:
        _log_telegram_request_error("telegram send failed", exc)
        return None


def _edit_telegram_text(message_id: int, text: str, *, target: tuple[str, str] | None = None) -> bool:
    """Edit an existing Telegram message."""
    target = target or _step_update_target()
    if not target:
        return False
    token, chat_id_raw = target
    cid = _telegram_api_chat_id(chat_id_raw)
    text = _redact_secrets(text)
    html_text = _md_to_telegram_html(text)[:4000]
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={"chat_id": cid, "message_id": message_id, "text": html_text, "parse_mode": "HTML"},
            timeout=15,
        )
        if not resp.ok:
            desc = (resp.json() if resp.content else {}).get("description", "")
            if "message is not modified" not in desc:
                _log(f"telegram edit failed: {resp.status_code} {desc[:80]}")
            return "message is not modified" in desc
        return True
    except requests.RequestException as exc:
        _log_telegram_request_error("telegram edit failed", exc)
        return False


def _send_telegram_document(file_path: str, caption: str = "", *, target: tuple[str, str] | None = None) -> bool:
    """Send a file as a Telegram document."""
    target = target or _step_update_target()
    if not target:
        return False
    token, chat_id_raw = target
    cid = _telegram_api_chat_id(chat_id_raw)
    caption = _redact_secrets(caption)[:1024]
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": cid, "caption": caption},
                files={"document": (Path(file_path).name, f)},
                timeout=60,
            )
        response.raise_for_status()
        _log(f"telegram document sent: {Path(file_path).name}")
        log_chat("bot", f"[sent file: {Path(file_path).name}] {caption}")
        return True
    except requests.RequestException as exc:
        _log_telegram_request_error("telegram document send failed", exc)
        return False


def _send_telegram_photo(file_path: str, caption: str = "", *, target: tuple[str, str] | None = None) -> bool:
    """Send an image as a Telegram photo (compressed)."""
    target = target or _step_update_target()
    if not target:
        return False
    token, chat_id_raw = target
    cid = _telegram_api_chat_id(chat_id_raw)
    caption = _redact_secrets(caption)[:1024]
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": cid, "caption": caption},
                files={"photo": (Path(file_path).name, f)},
                timeout=60,
            )
        response.raise_for_status()
        _log(f"telegram photo sent: {Path(file_path).name}")
        log_chat("bot", f"[sent photo: {Path(file_path).name}] {caption}")
        return True
    except requests.RequestException as exc:
        _log_telegram_request_error("telegram photo send failed", exc)
        return False


def _queue_operator_text(text: str, goal_index: int = 0):
    outbox = _outbox_file(goal_index)
    outbox.parent.mkdir(parents=True, exist_ok=True)
    content = _redact_secrets(text).strip()
    if not content:
        return
    with _outbox_lock:
        existing = outbox.read_text().strip() if outbox.exists() else ""
        merged = f"{existing}\n\n{content}".strip() if existing else content
        outbox.write_text(merged)


def _flush_operator_outbox(goal_index: int = 0, *, target: tuple[str, str] | None = None) -> bool:
    outbox = _outbox_file(goal_index)
    sending = outbox.with_name(outbox.name + ".sending")

    with _outbox_lock:
        if sending.exists():
            sending.unlink(missing_ok=True)
        if not outbox.exists():
            return False
        pending = outbox.read_text().strip()
        if not pending:
            outbox.unlink(missing_ok=True)
            return False
        outbox.replace(sending)

    text = sending.read_text().strip()
    if not text:
        sending.unlink(missing_ok=True)
        return False

    if _send_telegram_text(text, target=target):
        sending.unlink(missing_ok=True)
        return True

    with _outbox_lock:
        existing = outbox.read_text().strip() if outbox.exists() else ""
        merged = f"{text}\n\n{existing}".strip() if existing else text
        outbox.write_text(merged)
        sending.unlink(missing_ok=True)
    return False


def _download_telegram_file(bot, file_id: str, filename: str) -> Path:
    """Download a file from Telegram and save it to FILES_DIR."""
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    save_path = FILES_DIR / filename
    # avoid overwriting: append a suffix if the file already exists
    if save_path.exists():
        stem, suffix = save_path.stem, save_path.suffix
        ts = datetime.now().strftime("%H%M%S")
        save_path = FILES_DIR / f"{stem}_{ts}{suffix}"
    save_path.write_bytes(downloaded)
    _log(f"saved telegram file: {save_path.name} ({len(downloaded)} bytes)")
    return save_path


# ── Chutes proxy (Anthropic Messages API → OpenAI Chat Completions) ──────────

_proxy_app = FastAPI(title="Chutes Proxy")


def _convert_tools_to_openai(anthropic_tools: list[dict]) -> list[dict]:
    out = []
    for t in anthropic_tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


def _convert_messages_to_openai(
    messages: list[dict], system: str | list | None = None
) -> list[dict]:
    out: list[dict] = []

    if system:
        if isinstance(system, list):
            text_parts = [b["text"] for b in system if b.get("type") == "text"]
            system = "\n\n".join(text_parts)
        if system:
            out.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            out.append({"role": role, "content": str(content)})
            continue

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []
        image_parts: list[dict] = []

        for block in content:
            btype = block.get("type", "")

            if btype == "text":
                text_parts.append(block["text"])

            elif btype == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

            elif btype == "tool_result":
                result_content = block.get("content", "")
                if isinstance(result_content, list):
                    result_content = "\n".join(
                        b.get("text", "") for b in result_content if b.get("type") == "text"
                    )
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": block["tool_use_id"],
                    "content": str(result_content),
                })

            elif btype == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    image_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{source.get('media_type', 'image/png')};base64,{source['data']}"
                        },
                    })

        if role == "assistant":
            oai_msg: dict[str, Any] = {"role": "assistant"}
            if text_parts:
                oai_msg["content"] = "\n".join(text_parts)
            else:
                oai_msg["content"] = None
            if tool_calls:
                oai_msg["tool_calls"] = tool_calls
            out.append(oai_msg)

        elif role == "user":
            if tool_results:
                for tr in tool_results:
                    out.append(tr)
            if text_parts or image_parts:
                if image_parts:
                    content_blocks = [{"type": "text", "text": t} for t in text_parts] + image_parts
                    out.append({"role": "user", "content": content_blocks})
                elif text_parts:
                    out.append({"role": "user", "content": "\n".join(text_parts)})
        else:
            out.append({"role": role, "content": "\n".join(text_parts) if text_parts else ""})

    return out


def _build_openai_request(body: dict, *, routing: str = "agent") -> dict:
    routing_model = CHUTES_ROUTING_BOT if routing == "bot" else CHUTES_ROUTING_AGENT
    oai: dict[str, Any] = {
        "model": routing_model,
        "messages": _convert_messages_to_openai(
            body.get("messages", []),
            system=body.get("system"),
        ),
    }
    if "max_tokens" in body:
        oai["max_tokens"] = body["max_tokens"]
    if body.get("tools"):
        oai["tools"] = _convert_tools_to_openai(body["tools"])
        oai["tool_choice"] = "auto"
    if body.get("temperature") is not None:
        oai["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        oai["top_p"] = body["top_p"]
    if body.get("stream"):
        oai["stream"] = True
        oai["stream_options"] = {"include_usage": True}
    return oai


def _openai_response_to_anthropic(oai_resp: dict, model: str) -> dict:
    choice = oai_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    finish = choice.get("finish_reason", "stop")

    content_blocks: list[dict] = []
    if message.get("content"):
        content_blocks.append({"type": "text", "text": message["content"]})
    for tc in (message.get("tool_calls") or []):
        try:
            args = json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, KeyError):
            args = {}
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
            "name": tc["function"]["name"],
            "input": args,
        })

    if finish == "tool_calls":
        stop_reason = "tool_use"
    elif finish == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    usage = oai_resp.get("usage", {})
    return {
        "id": oai_resp.get("id", f"msg_{uuid.uuid4().hex}"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks or [{"type": "text", "text": ""}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_openai_to_anthropic(oai_response: httpx.Response, model: str):
    msg_id = f"msg_{uuid.uuid4().hex}"
    yield _sse_event("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "model": model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    })

    block_idx = 0
    in_text_block = False
    tool_calls_accum: dict[int, dict] = {}
    stop_reason = "end_turn"
    usage = {"input_tokens": 0, "output_tokens": 0}
    logged_stream_model = False

    async for line in oai_response.aiter_lines():
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        if not logged_stream_model and chunk.get("model"):
            _log(f"proxy: stream model={chunk['model']}")
            logged_stream_model = True

        if chunk.get("usage"):
            u = chunk["usage"]
            usage["input_tokens"] = u.get("prompt_tokens", usage["input_tokens"])
            usage["output_tokens"] = u.get("completion_tokens", usage["output_tokens"])

        choices = chunk.get("choices", [])
        if not choices:
            continue

        delta = choices[0].get("delta", {})
        finish = choices[0].get("finish_reason")

        if finish == "tool_calls":
            stop_reason = "tool_use"
        elif finish == "length":
            stop_reason = "max_tokens"
        elif finish == "stop":
            stop_reason = "end_turn"

        if delta.get("content"):
            if not in_text_block:
                yield _sse_event("content_block_start", {
                    "type": "content_block_start",
                    "index": block_idx,
                    "content_block": {"type": "text", "text": ""},
                })
                in_text_block = True
            yield _sse_event("content_block_delta", {
                "type": "content_block_delta",
                "index": block_idx,
                "delta": {"type": "text_delta", "text": delta["content"]},
            })

        if delta.get("tool_calls"):
            if in_text_block:
                yield _sse_event("content_block_stop", {
                    "type": "content_block_stop", "index": block_idx,
                })
                block_idx += 1
                in_text_block = False
            for tc in delta["tool_calls"]:
                tc_idx = tc.get("index", 0)
                if tc_idx not in tool_calls_accum:
                    tool_calls_accum[tc_idx] = {
                        "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": "",
                        "block_idx": block_idx,
                    }
                    yield _sse_event("content_block_start", {
                        "type": "content_block_start",
                        "index": block_idx,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_calls_accum[tc_idx]["id"],
                            "name": tool_calls_accum[tc_idx]["name"],
                            "input": {},
                        },
                    })
                    block_idx += 1
                args_chunk = tc.get("function", {}).get("arguments", "")
                if args_chunk:
                    tool_calls_accum[tc_idx]["arguments"] += args_chunk
                    yield _sse_event("content_block_delta", {
                        "type": "content_block_delta",
                        "index": tool_calls_accum[tc_idx]["block_idx"],
                        "delta": {"type": "input_json_delta", "partial_json": args_chunk},
                    })

    with _token_lock:
        _token_usage["input"] += usage["input_tokens"]
        _token_usage["output"] += usage["output_tokens"]

    if in_text_block:
        yield _sse_event("content_block_stop", {
            "type": "content_block_stop", "index": block_idx,
        })
    for tc in tool_calls_accum.values():
        yield _sse_event("content_block_stop", {
            "type": "content_block_stop", "index": tc["block_idx"],
        })

    yield _sse_event("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": usage["output_tokens"]},
    })
    yield _sse_event("message_stop", {"type": "message_stop"})


def _chutes_headers() -> dict:
    return {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }


@_proxy_app.get("/health")
async def _proxy_health():
    return {"status": "ok"}


@_proxy_app.get("/")
async def _proxy_root():
    return {
        "proxy": "chutes",
        "pool": CHUTES_POOL,
        "agent_routing": CHUTES_ROUTING_AGENT,
        "bot_routing": CHUTES_ROUTING_BOT,
        "status": "running",
    }


_CONTEXT_LENGTH_RE = re.compile(
    r"maximum context length is (\d+) tokens.*?(\d+) output tokens.*?(\d+) input tokens",
    re.DOTALL,
)
PROXY_MAX_RETRIES = 3


def _parse_context_length_error(error_msg: str) -> tuple[int, int, int] | None:
    """Extract (context_limit, requested_output, input_tokens) from a context-length 400."""
    m = _CONTEXT_LENGTH_RE.search(error_msg)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def _maybe_reduce_max_tokens(oai_request: dict, error_msg: str) -> bool:
    """If the error is a context-length overflow, reduce max_tokens to fit. Returns True if adjusted."""
    parsed = _parse_context_length_error(error_msg)
    if not parsed:
        return False
    ctx_limit, _req_output, input_tokens = parsed
    headroom = ctx_limit - input_tokens
    if headroom < 1024:
        return False
    new_max = max(1024, headroom - 64)
    old_max = oai_request.get("max_tokens", 0)
    if new_max >= old_max:
        return False
    oai_request["max_tokens"] = new_max
    _log(f"proxy: reduced max_tokens {old_max} -> {new_max} (ctx_limit={ctx_limit}, input={input_tokens})")
    return True


@_proxy_app.post("/v1/messages")
async def _proxy_messages(request: Request):
    body = await request.json()
    stream = body.get("stream", False)
    model = body.get("model", CLAUDE_MODEL)
    routing = "bot" if model == "bot" else "agent"
    oai_request = _build_openai_request(body, routing=routing)
    routing_label = CHUTES_ROUTING_BOT if routing == "bot" else CHUTES_ROUTING_AGENT

    if stream:
        last_error_msg = ""
        for attempt in range(1, PROXY_MAX_RETRIES + 1):
            try:
                client = httpx.AsyncClient(timeout=httpx.Timeout(PROXY_TIMEOUT))
                resp = await client.send(
                    client.build_request(
                        "POST", f"{CHUTES_BASE_URL}/chat/completions",
                        json=oai_request, headers=_chutes_headers(),
                    ),
                    stream=True,
                )
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    await resp.aclose()
                    await client.aclose()
                    last_error_msg = error_body.decode()[:500]
                    _log(f"proxy: chutes returned {resp.status_code} (attempt {attempt}/{PROXY_MAX_RETRIES}): {last_error_msg[:300]}")

                    if resp.status_code == 400 and _maybe_reduce_max_tokens(oai_request, last_error_msg):
                        continue
                    if attempt < PROXY_MAX_RETRIES:
                        continue

                    return JSONResponse(status_code=502, content={
                        "type": "error", "error": {
                            "type": "api_error",
                            "message": f"Chutes routing failed ({resp.status_code}): {last_error_msg[:300]}",
                        },
                    })

                async def generate(resp=resp, cl=client):
                    try:
                        _log(f"proxy: streaming [{routing}] via {routing_label}")
                        async for event in _stream_openai_to_anthropic(resp, model):
                            yield event
                    finally:
                        await resp.aclose()
                        await cl.aclose()

                return StreamingResponse(
                    generate(), media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )
            except httpx.TimeoutException:
                try:
                    await client.aclose()
                except Exception:
                    pass
                last_error_msg = f"timed out after {PROXY_TIMEOUT}s"
                _log(f"proxy: {last_error_msg} (attempt {attempt}/{PROXY_MAX_RETRIES})")
                if attempt < PROXY_MAX_RETRIES:
                    continue
                return JSONResponse(status_code=502, content={
                    "type": "error", "error": {
                        "type": "api_error",
                        "message": f"Chutes routing {last_error_msg}",
                    },
                })
            except Exception as exc:
                try:
                    await client.aclose()
                except Exception:
                    pass
                last_error_msg = str(exc)[:300]
                _log(f"proxy: error (attempt {attempt}/{PROXY_MAX_RETRIES}): {last_error_msg}")
                if attempt < PROXY_MAX_RETRIES:
                    continue
                return JSONResponse(status_code=502, content={
                    "type": "error", "error": {
                        "type": "api_error",
                        "message": f"Chutes routing error: {last_error_msg}",
                    },
                })

    else:
        oai_request.pop("stream", None)
        oai_request.pop("stream_options", None)
        last_error_msg = ""
        for attempt in range(1, PROXY_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(PROXY_TIMEOUT)) as client:
                    resp = await client.post(
                        f"{CHUTES_BASE_URL}/chat/completions",
                        json=oai_request, headers=_chutes_headers(),
                    )
                if resp.status_code != 200:
                    last_error_msg = resp.text[:500]
                    _log(f"proxy: chutes returned {resp.status_code} (attempt {attempt}/{PROXY_MAX_RETRIES}): {last_error_msg[:300]}")

                    if resp.status_code == 400 and _maybe_reduce_max_tokens(oai_request, last_error_msg):
                        continue
                    if attempt < PROXY_MAX_RETRIES:
                        continue

                    return JSONResponse(status_code=502, content={
                        "type": "error", "error": {
                            "type": "api_error",
                            "message": f"Chutes routing failed ({resp.status_code}): {last_error_msg[:300]}",
                        },
                    })
                oai_data = resp.json()
                actual_model = oai_data.get("model", "?")
                u = oai_data.get("usage", {})
                if u:
                    with _token_lock:
                        _token_usage["input"] += u.get("prompt_tokens", 0)
                        _token_usage["output"] += u.get("completion_tokens", 0)
                _log(f"proxy: response [{routing}] via {routing_label} model={actual_model}")
                return JSONResponse(content=_openai_response_to_anthropic(oai_data, model))
            except httpx.TimeoutException:
                last_error_msg = f"timed out after {PROXY_TIMEOUT}s"
                _log(f"proxy: {last_error_msg} (attempt {attempt}/{PROXY_MAX_RETRIES})")
                if attempt < PROXY_MAX_RETRIES:
                    continue
                return JSONResponse(status_code=502, content={
                    "type": "error", "error": {
                        "type": "api_error",
                        "message": f"Chutes routing {last_error_msg}",
                    },
                })
            except Exception as exc:
                last_error_msg = str(exc)[:300]
                _log(f"proxy: error (attempt {attempt}/{PROXY_MAX_RETRIES}): {last_error_msg}")
                if attempt < PROXY_MAX_RETRIES:
                    continue
                return JSONResponse(status_code=502, content={
                    "type": "error", "error": {
                        "type": "api_error",
                        "message": f"Chutes routing error: {last_error_msg}",
                    },
                })


@_proxy_app.post("/v1/messages/count_tokens")
async def _proxy_count_tokens(request: Request):
    body = await request.json()
    rough = sum(len(json.dumps(m)) for m in body.get("messages", [])) // 4
    rough += len(json.dumps(body.get("tools", []))) // 4
    rough += len(str(body.get("system", ""))) // 4
    return JSONResponse(content={"input_tokens": max(rough, 1)})


def _start_proxy():
    """Run the Chutes translation proxy in-process on a background thread."""
    config = uvicorn.Config(
        _proxy_app, host="127.0.0.1", port=PROXY_PORT, log_level="warning",
    )
    server = uvicorn.Server(config)
    server.run()


# ── Provider failover ────────────────────────────────────────────────────────

_QUOTA_PATTERNS = re.compile(
    r"rate.limit|rate_limit|429|quota|credit|billing|overloaded|"
    r"exceeded.*limit|too many requests|insufficient|capacity|"
    r"hit.*limit|resets \d|"
    r"not logged in|authentication_failed|please run /login|"
    r"authentication_error|oauth token has expired|401",
    re.IGNORECASE,
)


def _is_quota_error(stderr_output: str) -> bool:
    return bool(_QUOTA_PATTERNS.search(stderr_output))


def _switch_to_fallback():
    global _using_fallback
    with _provider_lock:
        if _using_fallback:
            return
        _using_fallback = True
    _log(f"quota exceeded — switching to fallback: {FALLBACK_PROVIDER}/{FALLBACK_MODEL}")
    if FALLBACK_PROVIDER != "opencode":
        _write_claude_settings()


def _try_primary():
    global _using_fallback
    with _provider_lock:
        if not _using_fallback:
            return
        _using_fallback = False
    _log(f"trying primary provider: {PROVIDER}/{CLAUDE_MODEL}")
    _write_claude_settings()


# ── Agent runner ─────────────────────────────────────────────────────────────

def _active_provider() -> str:
    return FALLBACK_PROVIDER if _using_fallback else PROVIDER


def _active_model() -> str:
    return FALLBACK_MODEL if _using_fallback else CLAUDE_MODEL


def _effective_model(workspace_id: int = 0) -> str:
    """Per-workspace override in context/workspace/<id>/workspace.json (Discord /model parity)."""
    m = _read_workspace_model(workspace_id)
    if m:
        return m
    return _active_model()


def _uses_claude_cli(provider: str) -> bool:
    return provider in ("anthropic", "openrouter", "chutes")


def _check_codex_login(label: str = "codex") -> None:
    try:
        status = subprocess.run(
            ["codex", "login", "status"],
            cwd=WORKING_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        _log(f"WARNING: {label} login check failed: {str(exc)[:120]}")
        return

    if status.returncode == 0:
        _log(f"{label} auth: {status.stdout.strip()}")
    else:
        _log(f"WARNING: {label} auth missing — run `codex login` or `codex login --device-auth`")


def _check_cursor_login() -> None:
    try:
        status = subprocess.run(
            ["agent", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        _log(f"WARNING: cursor agent not found: {str(exc)[:120]}")
        return

    _ansi = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
    if status.returncode == 0:
        info = _ansi.sub('', status.stdout or status.stderr).strip()
        _log(f"cursor agent: {info[:80]}")
    else:
        _log("WARNING: cursor agent not authenticated — run `agent login`")

def _claude_cmd(
    prompt: str, extra_flags: list[str] | None = None, model: str | None = None,
) -> list[str]:
    cmd = ["claude", "-p", prompt]
    if not IS_ROOT:
        cmd.append("--dangerously-skip-permissions")
    cmd.extend(["--output-format", "stream-json", "--verbose"])
    if extra_flags:
        cmd.extend(extra_flags)
    else:
        m = model if model is not None else _active_model()
        if m:
            cmd.extend(["--model", m])
    return cmd


def _codex_cmd(
    prompt: str, model: str | None = None, cwd: Path | None = None,
) -> list[str]:
    root = cwd or WORKING_DIR
    return [
        "codex", "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd", str(root),
        "--model", model or _active_model(),
        "--skip-git-repo-check",
        prompt,
    ]


def _cursor_cmd(prompt: str, model: str | None = None, cwd: Path | None = None) -> list[str]:
    root = cwd or WORKING_DIR
    cmd = [
        "agent",
        "--print",
        "--yolo",
        "--trust",
        "--output-format", "stream-json",
        "--workspace", str(root),
    ]
    m = model if model is not None else _active_model()
    if m:
        cmd.extend(["--model", m])
    cmd.append(prompt)
    return cmd


def _extract_prompt(cmd: list[str]) -> str:
    if cmd and cmd[0] == "codex" and len(cmd) > 1:
        return cmd[-1]
    if "-p" in cmd:
        idx = cmd.index("-p")
        if idx + 1 < len(cmd):
            return cmd[idx + 1]
    return ""


def _write_claude_settings():
    """Point Claude Code at the active provider."""
    settings_dir = WORKING_DIR / ".claude"
    settings_dir.mkdir(exist_ok=True)

    provider = _active_provider()
    model = _active_model()

    if not _uses_claude_cli(provider):
        _log(f"skipping .claude/settings.local.json for provider={provider}")
        return

    if provider == "anthropic":
        env_block = {}
        target_label = "pro-auth (native)"
    elif provider == "openrouter":
        api_key = FALLBACK_API_KEY if _using_fallback else LLM_API_KEY
        base_url = FALLBACK_BASE_URL if _using_fallback else LLM_BASE_URL
        env_block = {
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_AUTH_TOKEN": api_key,
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        target_label = base_url
    else:
        proxy_url = f"http://127.0.0.1:{PROXY_PORT}"
        env_block = {
            "ANTHROPIC_API_KEY": "chutes-proxy",
            "ANTHROPIC_BASE_URL": proxy_url,
            "ANTHROPIC_AUTH_TOKEN": "",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        target_label = proxy_url

    settings = {
        "model": model,
        "permissions": {
            "allow": [
                "Agent(*)", "AskUserQuestion(*)", "Bash(*)", "CronCreate(*)",
                "CronDelete(*)", "CronList(*)", "Edit(*)", "EnterPlanMode(*)",
                "EnterWorktree(*)", "ExitPlanMode(*)", "ExitWorktree(*)",
                "Glob(*)", "Grep(*)", "ListMcpResourcesTool(*)", "LSP(*)",
                "NotebookEdit(*)", "Read(*)", "ReadMcpResourceTool(*)",
                "Skill(*)", "TaskCreate(*)", "TaskGet(*)", "TaskList(*)",
                "TaskOutput(*)", "TaskStop(*)", "TaskUpdate(*)",
                "TodoWrite(*)", "ToolSearch(*)", "WebFetch(*)",
                "WebSearch(*)", "Write(*)"
            ],
        },
        "env": env_block,
    }
    (settings_dir / "settings.local.json").write_text(json.dumps(settings, indent=2))
    _log(f"wrote .claude/settings.local.json (provider={provider}, model={model}, target={target_label})")


def _claude_env(goal_index: int = 0, workspace_id: int = 0) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("TAU_BOT_TOKEN", None)
    if goal_index:
        env["ARBOS_GOAL_INDEX"] = str(goal_index)
    if workspace_id:
        env["ARBOS_WORKSPACE_ID"] = str(workspace_id)

    provider = _active_provider()

    if provider == "anthropic":
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_BASE_URL", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    elif provider == "openrouter":
        api_key = FALLBACK_API_KEY if _using_fallback else LLM_API_KEY
        base_url = FALLBACK_BASE_URL if _using_fallback else LLM_BASE_URL
        env["ANTHROPIC_API_KEY"] = ""
        env["ANTHROPIC_BASE_URL"] = base_url
        env["ANTHROPIC_AUTH_TOKEN"] = api_key
    else:
        env["ANTHROPIC_API_KEY"] = "chutes-proxy"
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{PROXY_PORT}"
        env["ANTHROPIC_AUTH_TOKEN"] = ""
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_claude_once(cmd, env, on_text=None, on_activity=None, cwd: Path | None = None):
    """Run a single claude subprocess, return (returncode, result_text, raw_lines, stderr).

    on_text: optional callback(accumulated_text) fired as assistant text streams in.
    on_activity: optional callback(status_str) fired on tool use and other activity.
    Kills the process if no output is received for CLAUDE_TIMEOUT seconds.
    """
    run_cwd = cwd if cwd is not None else WORKING_DIR
    proc = subprocess.Popen(
        cmd, cwd=run_cwd, env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    with _child_procs_lock:
        _child_procs.add(proc)

    active_provider = _active_provider()
    result_text = ""
    complete_texts: list[str] = []
    streaming_tokens: list[str] = []
    raw_lines: list[str] = []
    timed_out = False
    last_activity = time.monotonic()

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    try:
        while True:
            ready = sel.select(timeout=min(CLAUDE_TIMEOUT, 30))
            if not ready:
                if time.monotonic() - last_activity > CLAUDE_TIMEOUT:
                    _log(f"claude timeout: no output for {CLAUDE_TIMEOUT}s, killing pid={proc.pid}")
                    proc.kill()
                    timed_out = True
                    break
                if proc.poll() is not None:
                    break
                continue
            line = proc.stdout.readline()
            if not line:
                break
            last_activity = time.monotonic()
            raw_lines.append(line)
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type", "")
            if etype == "assistant":
                msg = evt.get("message", {})
                for block in msg.get("content", []):
                    btype = block.get("type", "")
                    if btype == "text" and block.get("text"):
                        if evt.get("model_call_id"):
                            complete_texts.append(block["text"])
                            streaming_tokens.clear()
                        else:
                            streaming_tokens.append(block["text"])
                            if on_text:
                                on_text("".join(streaming_tokens))
                    elif btype == "tool_use" and on_activity:
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        on_activity(_format_tool_activity(tool_name, tool_input))
                if active_provider == "openrouter":
                    u = msg.get("usage", {})
                    if u:
                        with _token_lock:
                            _token_usage["input"] += u.get("input_tokens", 0)
                            _token_usage["output"] += u.get("output_tokens", 0)
            elif etype == "item.completed":
                item = evt.get("item", {})
                if item.get("type") == "agent_message" and item.get("text"):
                    complete_texts.append(item["text"])
                    streaming_tokens.clear()
                    if on_text:
                        on_text(item["text"])
            elif etype == "result":
                result_text = evt.get("result", "")
                if active_provider == "openrouter":
                    u = evt.get("usage", {})
                    if u:
                        with _token_lock:
                            _token_usage["input"] += u.get("input_tokens", 0)
                            _token_usage["output"] += u.get("output_tokens", 0)
    finally:
        sel.unregister(proc.stdout)
        sel.close()

    if not result_text:
        if complete_texts:
            result_text = complete_texts[-1]
        elif streaming_tokens:
            result_text = "".join(streaming_tokens)

    if timed_out:
        stderr_output = "(timed out)"
    else:
        stderr_output = proc.stderr.read() if proc.stderr else ""

    returncode = proc.wait()
    with _child_procs_lock:
        _child_procs.discard(proc)
    return returncode, result_text, raw_lines, stderr_output


# ── Cursor runner ────────────────────────────────────────────────────────────

def _cursor_activity(evt: dict) -> str | None:
    """Extract a human-readable activity label from a cursor tool_call event."""
    if evt.get("subtype") != "started":
        return None
    tool_call = evt.get("tool_call", {})
    for tool_type, tool_data in tool_call.items():
        if not isinstance(tool_data, dict):
            continue
        label = _CURSOR_TOOL_LABELS.get(tool_type, tool_type)
        args = tool_data.get("args", {})
        desc = (tool_data.get("description") or
                args.get("command") or
                args.get("path") or
                args.get("query") or
                args.get("url") or "")
        if desc:
            return f"{label}: {str(desc)[:80]}"
        return f"{label}..."
    return None


def _run_cursor_once(cmd, env, on_text=None, on_activity=None, cwd: Path | None = None):
    """Run a single cursor agent subprocess, return (returncode, result_text, raw_lines, stderr).

    Parses Cursor's stream-json format:
      type=assistant  → accumulate text from message.content[].text
      type=tool_call  → fire on_activity
      type=result     → final result text + token usage
    """
    run_cwd = cwd if cwd is not None else WORKING_DIR
    proc = subprocess.Popen(
        cmd, cwd=run_cwd, env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    with _child_procs_lock:
        _child_procs.add(proc)

    result_text = ""
    accumulated_text = ""
    raw_lines: list[str] = []
    timed_out = False
    last_activity = time.monotonic()

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    try:
        while True:
            ready = sel.select(timeout=min(CLAUDE_TIMEOUT, 30))
            if not ready:
                if time.monotonic() - last_activity > CLAUDE_TIMEOUT:
                    _log(f"cursor timeout: no output for {CLAUDE_TIMEOUT}s, killing pid={proc.pid}")
                    proc.kill()
                    timed_out = True
                    break
                if proc.poll() is not None:
                    break
                continue
            line = proc.stdout.readline()
            if not line:
                break
            last_activity = time.monotonic()
            raw_lines.append(line)
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = evt.get("type", "")

            if etype == "assistant":
                content = evt.get("message", {}).get("content", [])
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        accumulated_text += part.get("text", "")
                if on_text and accumulated_text:
                    on_text(accumulated_text)

            elif etype == "tool_call":
                if on_activity and evt.get("subtype") == "started":
                    activity = _cursor_activity(evt)
                    if activity:
                        on_activity(activity)

            elif etype == "result":
                result_text = evt.get("result", accumulated_text)
                usage = evt.get("usage", {})
                if usage:
                    with _token_lock:
                        _token_usage["input"] += usage.get("inputTokens", 0)
                        _token_usage["output"] += usage.get("outputTokens", 0)

    finally:
        sel.unregister(proc.stdout)
        sel.close()

    if not result_text:
        result_text = accumulated_text

    if timed_out:
        stderr_output = "(timed out)"
    else:
        stderr_output = proc.stderr.read() if proc.stderr else ""

    returncode = proc.wait()
    with _child_procs_lock:
        _child_procs.discard(proc)
    return returncode, result_text, raw_lines, stderr_output


# ── OpenCode runner ──────────────────────────────────────────────────────────

def _opencode_cmd(model: str | None = None) -> list[str]:
    m = model or _active_model()
    cmd = ["opencode", "run", "--format", "json"]
    if m:
        cmd.extend(["-m", f"opencode/{m}"])
    return cmd


def _codex_activity(evt: dict[str, Any]) -> str | None:
    if evt.get("type") == "turn.started":
        return "thinking..."
    item = evt.get("item", {})
    if not isinstance(item, dict):
        return None
    item_type = item.get("type", "")
    if item_type in ("agent_message", "reasoning", ""):
        return None
    label = item.get("title") or item.get("name") or item.get("command") or item_type.replace("_", " ")
    return str(label)[:80] if label else None


def _run_codex_once(cmd, env, on_text=None, on_activity=None, cwd: Path | None = None):
    """Run a single codex subprocess, return (returncode, result_text, raw_lines, stderr)."""
    run_cwd = cwd if cwd is not None else WORKING_DIR
    proc = subprocess.Popen(
        cmd, cwd=run_cwd, env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    with _child_procs_lock:
        _child_procs.add(proc)

    result_text = ""
    complete_texts: list[str] = []
    raw_lines: list[str] = []
    timed_out = False
    last_activity = time.monotonic()

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    try:
        while True:
            ready = sel.select(timeout=min(CLAUDE_TIMEOUT, 30))
            if not ready:
                if time.monotonic() - last_activity > CLAUDE_TIMEOUT:
                    _log(f"codex timeout: no output for {CLAUDE_TIMEOUT}s, killing pid={proc.pid}")
                    proc.kill()
                    timed_out = True
                    break
                if proc.poll() is not None:
                    break
                continue
            line = proc.stdout.readline()
            if not line:
                break
            last_activity = time.monotonic()
            raw_lines.append(line)
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            status = _codex_activity(evt)
            if status and on_activity:
                on_activity(status)

            etype = evt.get("type", "")
            if etype == "item.completed":
                item = evt.get("item", {})
                if item.get("type") == "agent_message" and item.get("text"):
                    result_text = item["text"]
                    complete_texts.append(result_text)
                    if on_text:
                        on_text(result_text)
            elif etype == "turn.completed":
                usage = evt.get("usage", {})
                if usage:
                    with _token_lock:
                        _token_usage["input"] += usage.get("input_tokens", 0)
                        _token_usage["output"] += usage.get("output_tokens", 0)
            elif etype == "error" and evt.get("message"):
                result_text = evt["message"]
    finally:
        sel.unregister(proc.stdout)
        sel.close()

    if not result_text and complete_texts:
        result_text = complete_texts[-1]

    if timed_out:
        stderr_output = "(timed out)"
    else:
        stderr_output = proc.stderr.read() if proc.stderr else ""

    returncode = proc.wait()
    with _child_procs_lock:
        _child_procs.discard(proc)
    return returncode, result_text, raw_lines, stderr_output


def _run_opencode_once(cmd, env, on_text=None, on_activity=None, prompt: str = "", cwd: Path | None = None):
    """Run a single opencode subprocess, return (returncode, result_text, raw_lines, stderr).

    Parses OpenCode's JSON stream format: step_start, text, tool_use, step_finish.
    The prompt is sent via stdin (opencode reads from pipe).
    """
    run_cwd = cwd if cwd is not None else WORKING_DIR
    proc = subprocess.Popen(
        cmd, cwd=run_cwd, env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    with _child_procs_lock:
        _child_procs.add(proc)

    if proc.stdin and prompt:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass

    result_text = ""
    complete_texts: list[str] = []
    raw_lines: list[str] = []
    timed_out = False
    last_activity = time.monotonic()

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    try:
        while True:
            ready = sel.select(timeout=min(CLAUDE_TIMEOUT, 30))
            if not ready:
                if time.monotonic() - last_activity > CLAUDE_TIMEOUT:
                    _log(f"opencode timeout: no output for {CLAUDE_TIMEOUT}s, killing pid={proc.pid}")
                    proc.kill()
                    timed_out = True
                    break
                if proc.poll() is not None:
                    break
                continue
            line = proc.stdout.readline()
            if not line:
                break
            last_activity = time.monotonic()
            raw_lines.append(line)
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type", "")
            part = evt.get("part", {})

            if etype == "text":
                text = part.get("text", "")
                if text:
                    complete_texts.append(text)
                    if on_text:
                        on_text(text)

            elif etype == "tool_use":
                tool = part.get("tool", "")
                state = part.get("state", {})
                if on_activity and state.get("status") == "completed":
                    inp = state.get("input", {})
                    desc = inp.get("command", "") or inp.get("path", "") or str(inp)[:80]
                    on_activity(f"{tool}: {desc[:80]}")

            elif etype == "step_finish":
                tokens = part.get("tokens", {})
                with _token_lock:
                    _token_usage["input"] += tokens.get("input", 0)
                    _token_usage["output"] += tokens.get("output", 0)

    finally:
        sel.unregister(proc.stdout)
        sel.close()

    result_text = "\n\n".join(complete_texts) if complete_texts else ""

    if timed_out:
        stderr_output = "(timed out)"
    else:
        stderr_output = proc.stderr.read() if proc.stderr else ""

    returncode = proc.wait()
    with _child_procs_lock:
        _child_procs.discard(proc)
    return returncode, result_text, raw_lines, stderr_output


def run_agent(cmd: list[str], phase: str, output_file: Path,
              on_text=None, on_activity=None, goal_index: int = 0, workspace_id: int = 0,
              agent_cwd: Path | None = None) -> subprocess.CompletedProcess:
    _claude_semaphore.acquire()
    try:
        returncode, result_text, raw_lines, stderr_output = 1, "", [], "no attempts made"
        ac = agent_cwd
        if ac is None:
            ac = _goal_dir(goal_index, workspace_id) if goal_index else WORKING_DIR
        ac.mkdir(parents=True, exist_ok=True)
        wm = _effective_model(workspace_id)

        for attempt in range(1, MAX_RETRIES + 1):
            active_provider = _active_provider()
            use_opencode = active_provider == "opencode"
            use_codex = active_provider == "codex"
            use_cursor = active_provider == "cursor"

            if use_opencode:
                prompt_text = _extract_prompt(cmd)
                active_cmd = _opencode_cmd(wm)
                env = os.environ.copy()
                env.pop("TAU_BOT_TOKEN", None)
                env["PYTHONUNBUFFERED"] = "1"
                # Inject OpenCode config from .env (no opencode.json needed)
                opencode_config = {
                    "model": f"opencode/{wm}",
                    "small_model": f"opencode/{wm}",
                    "autoupdate": os.environ.get("OPENCODE_AUTOUPDATE", "false").lower() == "true",
                    "snapshot": os.environ.get("OPENCODE_SNAPSHOT", "false").lower() == "true",
                }
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps(opencode_config)
                engine = "opencode"
            elif use_codex:
                prompt_text = _extract_prompt(cmd)
                active_cmd = _codex_cmd(prompt_text, model=wm, cwd=ac)
                env = os.environ.copy()
                env.pop("TAU_BOT_TOKEN", None)
                env["PYTHONUNBUFFERED"] = "1"
                engine = "codex"
            elif use_cursor:
                prompt_text = _extract_prompt(cmd)
                active_cmd = _cursor_cmd(prompt_text, model=wm, cwd=ac)
                env = os.environ.copy()
                env.pop("TAU_BOT_TOKEN", None)
                env["PYTHONUNBUFFERED"] = "1"
                if LLM_API_KEY:
                    env["CURSOR_API_KEY"] = LLM_API_KEY
                engine = "cursor"
            else:
                prompt_text = ""
                active_cmd = cmd
                env = _claude_env(goal_index=goal_index, workspace_id=workspace_id)
                engine = "claude"

            flags = " ".join(a for a in active_cmd if a.startswith("-"))
            _log(f"{phase}: starting (attempt={attempt}, engine={engine}) flags=[{flags}]")
            t0 = time.monotonic()

            if use_opencode:
                returncode, result_text, raw_lines, stderr_output = _run_opencode_once(
                    active_cmd, env, on_text=on_text, on_activity=on_activity, prompt=prompt_text,
                    cwd=ac,
                )
            elif use_codex:
                returncode, result_text, raw_lines, stderr_output = _run_codex_once(
                    active_cmd, env, on_text=on_text, on_activity=on_activity, cwd=ac,
                )
            elif use_cursor:
                returncode, result_text, raw_lines, stderr_output = _run_cursor_once(
                    active_cmd, env, on_text=on_text, on_activity=on_activity, cwd=ac,
                )
            else:
                returncode, result_text, raw_lines, stderr_output = _run_claude_once(
                    active_cmd, env, on_text=on_text, on_activity=on_activity, cwd=ac,
                )
            elapsed = time.monotonic() - t0

            output_file.write_text(_redact_secrets("".join(raw_lines)))
            _log(f"{phase}: finished rc={returncode} {fmt_duration(elapsed)}")

            combined_err = f"{stderr_output} {result_text}"
            if returncode != 0 and (stderr_output.strip() or _is_quota_error(combined_err)):
                if stderr_output.strip():
                    _log(f"{phase}: stderr {stderr_output.strip()[:300]}")
                if _is_quota_error(combined_err) and not _using_fallback:
                    _log(f"{phase}: quota/rate-limit detected, switching to fallback")
                    _switch_to_fallback()
                    continue
                if attempt < MAX_RETRIES:
                    delay = min(2 ** attempt, 30)
                    _log(f"{phase}: retrying in {delay}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(delay)
                    continue

            return subprocess.CompletedProcess(
                args=cmd, returncode=returncode,
                stdout=result_text, stderr=stderr_output,
            )

        _log(f"{phase}: all {MAX_RETRIES} retries exhausted")
        output_file.write_text(_redact_secrets("".join(raw_lines)))
        return subprocess.CompletedProcess(
            args=cmd, returncode=returncode,
            stdout=result_text, stderr=stderr_output,
        )
    finally:
        _claude_semaphore.release()


def extract_text(result: subprocess.CompletedProcess) -> str:
    output = result.stdout or ""
    if not output.strip():
        output = result.stderr or "(no output)"
    return output


def run_step(prompt: str, step_number: int, goal_index: int = 0, goal_step: int = 0, workspace_id: int = 0) -> bool:
    run_dir = make_run_dir(goal_index=goal_index, workspace_id=workspace_id)
    t0 = time.monotonic()

    log_file = run_dir / "logs.txt"
    _tls.log_fh = open(log_file, "a", encoding="utf-8")

    smf = _step_msg_file(goal_index, workspace_id) if goal_index else CONTEXT_DIR / ".step_msg"

    target = _telegram_step_target(workspace_id)
    step_label = f"Goal #{goal_index} Step {goal_step}" if goal_index else f"Step {step_number}"
    step_msg_id: int | None = None
    step_msg_text = ""
    last_edit = 0.0

    if target:
        step_msg_id = _send_telegram_new(f"{step_label}: starting...", target=target)
        if step_msg_id:
            smf.parent.mkdir(parents=True, exist_ok=True)
            smf.write_text(json.dumps({
                "msg_id": step_msg_id, "text": f"{step_label}: starting...",
            }))
    else:
        smf.unlink(missing_ok=True)

    def _edit_step_msg(text: str, *, force: bool = False):
        nonlocal last_edit, step_msg_text
        if not step_msg_id or not target:
            return
        now = time.time()
        if not force and now - last_edit < 3.0:
            return
        step_msg_text = text
        _edit_telegram_text(step_msg_id, text, target=target)
        try:
            smf.parent.mkdir(parents=True, exist_ok=True)
            smf.write_text(json.dumps({"msg_id": step_msg_id, "text": text}))
        except OSError as e:
            _log(f"step message write failed: {e}")
        last_edit = now

    _reset_tokens()

    _last_activity = [""]
    _heartbeat_stop = threading.Event()

    def _on_activity(status: str):
        _last_activity[0] = status
        elapsed_s = time.monotonic() - t0
        inp, out = _get_tokens()
        tok = f" | {fmt_tokens(inp, out, elapsed_s)}" if (inp or out) else ""
        _edit_step_msg(f"{step_label} ({fmt_duration(elapsed_s)}{tok})\n{status}")

    def _heartbeat():
        while not _heartbeat_stop.wait(timeout=5):
            elapsed_s = time.monotonic() - t0
            inp, out = _get_tokens()
            tok = f" | {fmt_tokens(inp, out, elapsed_s)}" if (inp or out) else ""
            status = _last_activity[0] or "working..."
            _edit_step_msg(f"{step_label} ({fmt_duration(elapsed_s)}{tok})\n{status}", force=True)

    success = False
    try:
        _log(f"run dir {run_dir}")

        preview = prompt[:200] + ("…" if len(prompt) > 200 else "")
        _log(f"prompt preview: {preview}")

        _log(f"goal #{goal_index} step {goal_step}: executing")

        threading.Thread(target=_heartbeat, daemon=True).start()

        _gdir = _goal_dir(goal_index, workspace_id)
        _gdir.mkdir(parents=True, exist_ok=True)
        result = run_agent(
            _claude_cmd(prompt, model=_effective_model(workspace_id)),
            phase=f"goal#{goal_index}",
            output_file=run_dir / "output.txt",
            on_activity=_on_activity,
            goal_index=goal_index,
            workspace_id=workspace_id,
            agent_cwd=_gdir,
        )

        rollout_text = _redact_secrets(extract_text(result))
        (run_dir / "rollout.md").write_text(rollout_text)
        _log(f"rollout saved ({len(rollout_text)} chars)")

        elapsed = time.monotonic() - t0
        success = result.returncode == 0
        _log(f"step {'succeeded' if success else 'failed'} in {fmt_duration(elapsed)}")
        return success
    finally:
        _heartbeat_stop.set()
        fh = getattr(_tls, "log_fh", None)
        if fh:
            fh.close()
            _tls.log_fh = None
        try:
            elapsed = fmt_duration(time.monotonic() - t0)
            rollout = (run_dir / "rollout.md").read_text() if (run_dir / "rollout.md").exists() else ""
            status = "done" if success else "failed"

            agent_text = ""
            if smf.exists():
                try:
                    state = json.loads(smf.read_text())
                    saved = state.get("text", "")
                    prefix = f"{step_label}: starting..."
                    if saved != prefix and not saved.startswith(f"{step_label} ("):
                        agent_text = saved
                except (json.JSONDecodeError, KeyError):
                    pass

            elapsed_s = time.monotonic() - t0
            inp, out = _get_tokens()
            tok = f" | {fmt_tokens(inp, out, elapsed_s)}" if (inp or out) else ""
            parts = [f"{step_label} ({elapsed}, {status}{tok})"]
            if agent_text:
                parts.append(agent_text)
            if rollout.strip():
                parts.append(rollout.strip()[:3500])
            final = "\n\n".join(parts)

            _edit_step_msg(final, force=True)
            log_chat("bot", final[:1000])
            smf.unlink(missing_ok=True)
        except Exception as exc:
            _log(f"step message finalize failed: {str(exc)[:120]}")


# ── Auto-push on profitable results ──────────────────────────────────────────

def _auto_push_if_profitable(step_num: int, goal_index: int = 1):
    """Push changes to GitHub when the agent requests it via .autopush flag."""
    if not AUTO_PUSH:
        return

    autopush_flag = WORKING_DIR / ".autopush"
    if not autopush_flag.exists():
        return

    flag_msg = autopush_flag.read_text().strip()
    autopush_flag.unlink(missing_ok=True)

    try:
        subprocess.run(
            ["git", "add", "-A",
             "--", ".", ":!.env", ":!.env.*", ":!context/", ":!logs/"],
            cwd=WORKING_DIR, capture_output=True, text=True, timeout=10,
        )

        status = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=WORKING_DIR, capture_output=True, text=True, timeout=10,
        )
        if not status.stdout.strip():
            _log("auto-push: nothing to commit")
            return

        msg = flag_msg or f"auto: step {step_num} goal #{goal_index}"

        r = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=WORKING_DIR, capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            _log(f"auto-push: commit failed: {r.stderr.strip()[:200]}")
            return

        push_env = os.environ.copy()
        if GITHUB_TOKEN:
            push_env["GIT_ASKPASS"] = "echo"
            push_env["GIT_TERMINAL_PROMPT"] = "0"
            remote_url = subprocess.run(
                ["git", "remote", "get-url", AUTO_PUSH_REMOTE],
                cwd=WORKING_DIR, capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if remote_url.startswith("https://github.com/"):
                auth_url = remote_url.replace("https://github.com/", f"https://x-access-token:{GITHUB_TOKEN}@github.com/")
                push_target = [auth_url, AUTO_PUSH_BRANCH]
            else:
                push_target = [AUTO_PUSH_REMOTE, AUTO_PUSH_BRANCH]
        else:
            push_target = [AUTO_PUSH_REMOTE, AUTO_PUSH_BRANCH]

        r = subprocess.run(
            ["git", "push"] + push_target,
            cwd=WORKING_DIR, capture_output=True, text=True, timeout=30,
            env=push_env,
        )
        if r.returncode != 0:
            _log(f"auto-push: push failed: {_redact_secrets(r.stderr.strip()[:200])}")
            return

        _log(f"auto-push: pushed ({msg})")
    except Exception as exc:
        _log(f"auto-push error: {str(exc)[:200]}")


# ── Agent loop ───────────────────────────────────────────────────────────────


def _goal_loop(workspace_id: int, index: int):
    """Run the agent loop for a single goal (legacy workspace_id=0 or Telegram supergroup id)."""
    global _step_count

    with _goals_lock:
        goals_map = _goals if workspace_id == 0 else _tg_goals_map(workspace_id)
        gs = goals_map.get(index)
    if not gs:
        return

    failures = 0
    gf = _goal_file(index, workspace_id)
    tg_notify = workspace_id if workspace_id else None
    ws_tag = f" ws={workspace_id}" if workspace_id else ""

    while not gs.stop_event.is_set():
        if not gf.exists() or not gf.read_text().strip():
            if gs.goal_hash:
                _log(f"goal #{index}{ws_tag} cleared after {gs.step_count} steps")
                gs.goal_hash = ""
                gs.step_count = 0
            gs.wake.wait(timeout=5)
            gs.wake.clear()
            continue

        if gs.paused:
            gs.wake.wait(timeout=5)
            gs.wake.clear()
            continue

        current_goal = gf.read_text().strip()
        current_hash = hashlib.sha256(current_goal.encode()).hexdigest()[:16]
        if current_hash != gs.goal_hash:
            if gs.goal_hash:
                _log(f"goal #{index}{ws_tag} changed after {gs.step_count} steps on previous goal")
            gs.goal_hash = current_hash
            gs.step_count = 0
            _log(f"goal #{index}{ws_tag} new [{current_hash}]: {current_goal[:100]}")

        _step_count += 1
        gs.step_count += 1
        gs.last_run = datetime.now().isoformat()
        with _goals_lock:
            _save_goals(workspace_id)

        if _using_fallback:
            _try_primary()

        _log(f"Goal #{index}{ws_tag} Step {gs.step_count} (global step {_step_count})", blank=True)

        prompt = load_prompt(
            goal_index=index, consume_inbox=True, goal_step=gs.step_count, workspace_id=workspace_id,
        )
        if not prompt:
            gs.wake.wait(timeout=5)
            gs.wake.clear()
            continue

        _log(f"goal #{index}{ws_tag}: prompt={len(prompt)} chars")

        success = run_step(
            prompt, _step_count, goal_index=index, goal_step=gs.step_count, workspace_id=workspace_id,
        )

        gs.last_finished = datetime.now().isoformat()
        with _goals_lock:
            _save_goals(workspace_id)

        if success:
            failures = 0
            _auto_push_if_profitable(gs.step_count, goal_index=index)
        else:
            failures += 1
            _log(f"goal #{index}{ws_tag}: failure #{failures}")

        gs.wake.clear()

        if success and GOAL_STOP_AFTER_SUCCESS:
            with _goals_lock:
                gs.started = False
                gs.paused = False
                _save_goals(workspace_id)
            failures = 0
            _log(
                f"goal #{index}{ws_tag}: stopped after successful step (GOAL_STOP_AFTER_SUCCESS); "
                f"/start {index} when ready for the next step",
            )
            _send_telegram_text(
                f"Goal #{index}: reply sent — goal finished for now. Send /start {index} after your next message.",
                chat_id=tg_notify,
            )
            gs.stop_event.set()
            break

        if GOAL_PAUSE_AFTER_EACH_STEP:
            with _goals_lock:
                gs.paused = True
                _save_goals(workspace_id)
            failures = 0
            _log(
                f"goal #{index}{ws_tag}: auto-paused after step (GOAL_PAUSE_AFTER_EACH_STEP); "
                f"/start {index} to run the next step",
            )
            _send_telegram_text(
                f"Goal #{index}: step finished — loop paused. Send /start {index} for the next step.",
                chat_id=tg_notify,
            )
            continue

        with _goals_lock:
            skip_wait = gs.force_next
            if skip_wait:
                gs.force_next = False
                _save_goals(workspace_id)
        if skip_wait:
            _log(f"goal #{index}{ws_tag}: forced — skipping delay")
            continue

        step_delay = gs.delay + int(os.environ.get("AGENT_DELAY", "0"))
        if failures:
            backoff = min(2 ** failures, 120)
            step_delay += backoff
            _log(f"goal #{index}{ws_tag}: waiting {step_delay}s (failure backoff + delay)")
            gs.wake.wait(timeout=step_delay)
        elif step_delay > 0:
            _log(f"goal #{index}{ws_tag}: waiting {step_delay}s (delay)")
            gs.wake.wait(timeout=step_delay)

    _log(f"goal #{index}{ws_tag} loop exited")


def _goal_manager_tick_map(goals_map: dict[int, GoalState], workspace_id: int):
    for idx, gs in list(goals_map.items()):
        if gs.started and not gs.paused and gs.thread is None:
            gs.stop_event.clear()
            name = f"goal-{idx}" if workspace_id == 0 else f"goal-w{workspace_id}-{idx}"
            t = threading.Thread(
                target=_goal_loop, args=(workspace_id, idx), daemon=True, name=name,
            )
            gs.thread = t
            t.start()
            _log(f"goal #{idx} thread spawned (workspace {workspace_id})")
        elif gs.started and gs.paused and gs.thread is not None:
            pass
        elif not gs.started and gs.thread is not None:
            gs.stop_event.set()
            gs.wake.set()
        if gs.thread is not None and not gs.thread.is_alive():
            gs.thread = None


def _goal_manager():
    """Monitor goals (legacy + Telegram workspaces) and spawn/stop goal threads."""
    while not _shutdown.is_set():
        with _goals_lock:
            _goal_manager_tick_map(_goals, 0)
            for ws_id, gmap in list(_tg_workspace_goals.items()):
                _goal_manager_tick_map(gmap, ws_id)
        _shutdown.wait(timeout=2)


def _summarize_goal(text: str) -> str:
    """Generate a one-line summary of a goal via LLM. Falls back to truncation."""
    try:
        if PROVIDER == "codex":
            CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
            prompt = (
                "Summarize the user's goal in 8 words or fewer. "
                "Reply with ONLY the summary.\n\n"
                f"{text[:500]}"
            )
            result = run_agent(
                _codex_cmd(prompt, model=os.environ.get("CODEX_SUMMARY_MODEL", CLAUDE_MODEL)),
                phase="summarize",
                output_file=CONTEXT_DIR / "summary_output.txt",
            )
            summary = extract_text(result).strip().strip('"\'.')
            if result.returncode == 0 and summary:
                return summary[:80]
            raise RuntimeError(result.stderr.strip() or "empty Codex summary")
        if PROVIDER == "anthropic":
            or_key = os.environ.get("OPENROUTER_API_KEY", "")
            if FALLBACK_PROVIDER == "opencode" and or_key:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"}
                model = "stepfun/step-3.5-flash:free"
            elif FALLBACK_BASE_URL and FALLBACK_API_KEY:
                url = f"{FALLBACK_BASE_URL}/v1/chat/completions"
                headers = {"Authorization": f"Bearer {FALLBACK_API_KEY}", "Content-Type": "application/json"}
                model = FALLBACK_MODEL
            else:
                raise RuntimeError("no API endpoint for summarization")
        elif PROVIDER == "openrouter":
            url = f"{LLM_BASE_URL}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
            model = CLAUDE_MODEL
        elif PROVIDER in ("opencode", "cursor"):
            # No REST API — try fallback provider if it has an HTTP endpoint
            if FALLBACK_PROVIDER == "openrouter" and FALLBACK_API_KEY:
                url = f"{FALLBACK_BASE_URL}/v1/chat/completions"
                headers = {"Authorization": f"Bearer {FALLBACK_API_KEY}", "Content-Type": "application/json"}
                model = FALLBACK_MODEL
            elif FALLBACK_BASE_URL and FALLBACK_API_KEY:
                url = f"{FALLBACK_BASE_URL}/v1/chat/completions"
                headers = {"Authorization": f"Bearer {FALLBACK_API_KEY}", "Content-Type": "application/json"}
                model = FALLBACK_MODEL
            else:
                raise RuntimeError(f"goal summarization via {PROVIDER} CLI is not supported and no fallback API configured")
        else:
            url = f"{CHUTES_BASE_URL}/chat/completions"
            headers = _chutes_headers()
            model = CHUTES_ROUTING_BOT

        resp = requests.post(url, json={
            "model": model,
            "max_tokens": 50,
            "messages": [
                {"role": "system", "content": "Summarize the user's goal in 8 words or fewer. Reply with ONLY the summary."},
                {"role": "user", "content": text[:500]},
            ],
        }, headers=headers, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content") or ""
                summary = content.strip().strip('"\'.')
                if summary:
                    return summary[:80]
    except Exception as exc:
        _log(f"summarize failed: {str(exc)[:100]}")

    first_line = text[:60].split('\n')[0].strip()
    return first_line + ("..." if len(text) > 60 else "")


def transcribe_voice(file_path: str, fmt: str = "ogg") -> str:
    """Transcribe audio via Chutes Whisper Large V3 STT endpoint."""
    try:
        with open(file_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            "https://chutes-whisper-large-v3.chutes.ai/transcribe",
            headers={
                "Authorization": f"Bearer {CHUTES_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"language": None, "audio_b64": b64_audio},
            timeout=90,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = data.get("text", "") if isinstance(data, dict) else str(data)
            if text.strip():
                _log(f"whisper transcription ok ({len(text)} chars)")
                return text.strip()
            return "(voice transcription returned empty — send text instead)"
        _log(f"whisper STT failed: status={resp.status_code} body={resp.text[:200]}")
        return "(voice transcription unavailable — send text instead)"
    except Exception as exc:
        _log(f"transcription failed: {str(exc)[:200]}")
        return "(voice transcription unavailable — send text instead)"


# ── Telegram bot ─────────────────────────────────────────────────────────────

def _recent_context(max_chars: int = 6000) -> str:
    """Collect recent rollouts across all goals."""
    parts: list[str] = []
    total = 0
    all_runs: list[tuple[str, Path]] = []
    for idx, gs in sorted(_goals.items()):
        runs_dir = _goal_runs_dir(idx, 0)
        if not runs_dir.exists():
            continue
        for d in runs_dir.iterdir():
            if d.is_dir():
                all_runs.append((f"goal#{idx}/{d.name}", d))
    for ws_id, gmap in sorted(_tg_workspace_goals.items()):
        for idx, gs in sorted(gmap.items()):
            runs_dir = _goal_runs_dir(idx, ws_id)
            if not runs_dir.exists():
                continue
            for d in runs_dir.iterdir():
                if d.is_dir():
                    all_runs.append((f"ws{ws_id}/goal#{idx}/{d.name}", d))
    all_runs.sort(key=lambda x: x[1].name, reverse=True)
    for label, run_dir in all_runs:
        f = run_dir / "rollout.md"
        if f.exists():
            content = f.read_text()[:2000]
            hdr = f"\n--- rollout.md ({label}) ---\n"
            if total + len(hdr) + len(content) > max_chars:
                return "".join(parts)
            parts.append(hdr + content)
            total += len(hdr) + len(content)
        if total > max_chars:
            break
    return "".join(parts)


def _build_operator_prompt(
    user_text: str,
    *,
    telegram_workspace_id: int = 0,
    active_topic_goal: int | None = None,
    arbos_reply_french: bool = False,
    telegram_user_id: int | None = None,
    telegram_room_id: int | None = None,
) -> str:
    """Build prompt for the CLI agent to handle any operator request."""
    _model_env_key = {"cursor": "CURSOR_MODEL", "codex": "CODEX_MODEL", "opencode": "OPENCODE_MODEL"}.get(_active_provider(), "CLAUDE_MODEL")

    if telegram_workspace_id:
        wid = telegram_workspace_id
        ws_glob = f"context/workspace/{wid}/goals/<index>/"
        multi_goal_block = (
            "## Multi-goal system (Telegram workspace)\n\n"
            f"This chat is a **Telegram supergroup workspace** (chat id `{wid}`). "
            f"Goals live under **`{ws_glob}`** (same layout as legacy: GOAL.md, STATE.md, INBOX.md, runs/). "
            "In **forum** supergroups, `/goal` creates a **topic**; the goal index equals Telegram `message_thread_id`. "
            "Commands from this chat only affect goals in this workspace.\n\n"
            "## Available operations\n\n"
            f"- **Message a goal's agent**: append to `context/workspace/{wid}/goals/<index>/INBOX.md`.\n"
            f"- **Update a goal's state**: write to `context/workspace/{wid}/goals/<index>/STATE.md`.\n"
        )
    else:
        multi_goal_block = (
            "## Multi-goal system\n\n"
            "Goals are indexed and stored in `context/goals/<index>/`. Each goal has its own GOAL.md, STATE.md, INBOX.md, and runs/.\n"
            "Goal management is handled via Telegram commands (/goal, /start, /stop, /pause, /delete, /delay, /ls, /status).\n"
            "To modify a specific goal's context, write to `context/goals/<index>/STATE.md` or `context/goals/<index>/INBOX.md`.\n\n"
            "## Available operations\n\n"
            "- **Message a goal's agent**: append a timestamped line to `context/goals/<index>/INBOX.md`.\n"
            "- **Update a goal's state**: write to `context/goals/<index>/STATE.md`.\n"
        )

    parts = [
        "You are the operator interface for Arbos, a coding agent running in a loop via pm2.\n"
        "The operator communicates with you through Telegram. Be concise and direct.\n"
        "When the operator asks you to do something, do it by modifying the relevant files.\n"
        "When the operator asks a question, answer from the available context.\n\n"
        f"## Runtime\n\nActive provider: `{_active_provider()}`, model: `{_active_model()}`\n"
        "To change the model at runtime, write `KEY='value'` to `context/.env.pending` "
        f"(current key: `{_model_env_key}`).\n\n"
        "## Security\n\n"
        "NEVER read, output, or reveal the contents of `.env`, `.env.enc`, or any secret/key/token values.\n"
        "Do not include API keys, passwords, seed phrases, or credentials in any response.\n"
        "If asked to show secrets, refuse. The .env file is encrypted; do not attempt to decrypt it.\n\n"
        f"{multi_goal_block}"
        "- **Set system prompt**: write to `PROMPT.md`.\n"
        "- **Set env variable**: write `KEY='VALUE'` lines (one per line) to `context/.env.pending`. They are picked up automatically and persisted.\n"
        "- **View logs**: read files under each goal's `runs/<timestamp>/` (rollout.md, logs.txt).\n"
        "- **Modify code & restart**: edit code files, then run `touch .restart`.\n"
        "- **Send follow-up**: the operator interface answers directly in Telegram; goal steps do not send separate outbox messages.\n"
        "- **Send file to operator**: run `python arbos.py sendfile path/to/file [--caption 'text'] [--photo]`.\n"
        "- **Received files**: operator-sent files are saved in `context/files/` and their path is shown in the message.",
    ]

    goals_section: list[str] = []
    if _goals:
        for idx in sorted(_goals.keys()):
            gs = _goals[idx]
            status = _goal_status_label(gs)
            gf = _goal_file(idx, 0)
            goal_text = gf.read_text().strip()[:200] if gf.exists() else "(empty)"
            sf = _state_file(idx, 0)
            state_text = sf.read_text().strip()[:200] if sf.exists() else "(empty)"
            goals_section.append(
                f"### Legacy goal #{idx} [{status}] (delay: {gs.delay}s, step {gs.step_count})\n"
                f"{goal_text}\nState: {state_text}",
            )
    if telegram_workspace_id:
        gmap = _tg_goals_map(telegram_workspace_id)
        w = telegram_workspace_id
        for idx in sorted(gmap.keys()):
            gs = gmap[idx]
            status = _goal_status_label(gs)
            gf = _goal_file(idx, w)
            goal_text = gf.read_text().strip()[:200] if gf.exists() else "(empty)"
            sf = _state_file(idx, w)
            state_text = sf.read_text().strip()[:200] if sf.exists() else "(empty)"
            goals_section.append(
                f"### Workspace `{w}` goal #{idx} [{status}] (delay: {gs.delay}s, step {gs.step_count})\n"
                f"{goal_text}\nState: {state_text}",
            )

    if goals_section:
        parts.append("## Goals\n" + "\n\n".join(goals_section))
    else:
        parts.append("## Goals\n(no goals set)")

    if active_topic_goal is not None and telegram_workspace_id:
        rel = _goal_ctx_rel_path(active_topic_goal, telegram_workspace_id)
        parts.append(
            "## Current Telegram topic\n\n"
            f"This message is in a **forum topic** mapped to **goal #{active_topic_goal}** "
            f"(files under `{rel}`). Prefer that goal when the operator's request is about this thread.\n",
        )

    if telegram_room_id is not None:
        room_log = load_chatlog_group(max_chars=2800, telegram_chat_id=telegram_room_id)
        if room_log:
            parts.append(
                room_log
                + "\n\n## Telegram (salon partagé vs opérateur)\n"
                + "Above: **all members** interacting with the bot in this group. Below: **this operator's** personal "
                + "thread. Address **Operator message** using the **personal** section; use the salon block only for "
                + "context (what others asked).\n",
            )
    user_log = load_chatlog(max_chars=4000, telegram_user_id=telegram_user_id)
    if user_log:
        parts.append(user_log)

    context = _recent_context(max_chars=4000)
    if context:
        parts.append(f"## Recent activity\n{context}")
    parts.append(_chi_knowledge_section(compact=True))
    if arbos_reply_french:
        parts.append(
            "## Language (Telegram /arbos)\n\n"
            "This request used **`/arbos`**. **Answer the user in French** — input may be in any language, but the "
            "reply shown in Telegram must be **French** (technical terms like TAO, subnet, CLI flags may stay as usual).\n",
        )
    parts.append(f"## Operator message\n{user_text}")

    return "\n\n".join(parts)


def _chi_knowledge_section(*, compact: bool) -> str:
    """Point agents at unconst/Chi YAML knowledge (git submodule under external/Chi)."""
    kdir = WORKING_DIR / "external" / "Chi" / "knowledge"
    rel = "external/Chi/knowledge"
    url = "https://github.com/unconst/Chi/tree/main/knowledge"
    _workflow = (
        "**Chi is not an end state**—only **background context** (terms, routes via `INDEX.yaml`, mental models). "
        "For anything substantive about the network, **default to tools**: read-only `agcli` / `btcli`, plus WebSearch "
        "or official docs when needed. Use Chi to orient, then **prove or refine** with CLI output / live sources; "
        "say what came from Chi vs what came from tools."
    )
    _epistemic = (
        "YAML can be **stale**; chain, hyperparams, and CLIs **change**—never treat Chi as sufficient on its own."
    )
    if not kdir.is_dir():
        return (
            "## Chi knowledge base\n"
            f"Not on disk (`{rel}/`). Initialize: `git submodule update --init external/Chi` "
            f"— sources: [{url}]({url}).\n"
            f"{_workflow} {_epistemic}\n\n"
        )
    if compact:
        return (
            "## Chi knowledge base\n"
            f"YAML in **`{rel}/`** ([Chi/knowledge]({url})); optional **Read** via `{rel}/INDEX.yaml`. "
            f"{_workflow} {_epistemic}\n\n"
        )
    return (
        "## Curated knowledge ([Chi](https://github.com/unconst/Chi))\n"
        f"Topic packs under **`{rel}/`** — use **`INDEX.yaml`** only to **pick** files for context. "
        f"{_workflow} {_epistemic}\n\n"
    )


def _telegram_public_chat_ids_from_env() -> set[int]:
    raw = os.environ.get("TELEGRAM_PUBLIC_CHAT_IDS", "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            _log(f"TELEGRAM_PUBLIC_CHAT_IDS: skipped invalid entry {part!r}")
    return out


def _telegram_workspace_group_ids_from_env() -> set[int]:
    """Supergroup IDs that use `context/workspace/<chat_id>/` (Discord channel–style isolation)."""
    raw = os.environ.get("TELEGRAM_WORKSPACE_GROUP_IDS", "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            _log(f"TELEGRAM_WORKSPACE_GROUP_IDS: skipped invalid entry {part!r}")
    return out


def _goals_background_autorun_default() -> bool:
    """When False, goal threads are not auto-started at process boot (wait for /start)."""
    raw = os.environ.get("GOALS_BACKGROUND_AUTORUN", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    token = os.getenv("TAU_BOT_TOKEN", "").strip()
    has_scope = bool(
        _telegram_public_chat_ids_from_env() or _telegram_workspace_group_ids_from_env(),
    )
    return not (token and has_scope)


def _stop_all_ralph_goal_autorun():
    """Force every registered goal to stopped/paused=false and persist (Telegram Q&A idle until /start)."""
    with _goals_lock:
        for gs in _goals.values():
            gs.started = False
            gs.paused = False
        for _wid, gmap in list(_tg_workspace_goals.items()):
            for gs in gmap.values():
                gs.started = False
                gs.paused = False
        _save_goals(0)
        for wid in list(_tg_workspace_goals.keys()):
            _save_goals(wid)


def _telegram_send_final_chunks(
    bot, chat_id: int, text: str, send_kw: dict[str, Any],
    *,
    telegram_user_id: int | None = None,
    telegram_shared_room_id: int | None = None,
):
    """Send one or more Telegram messages (4096 limit per message)."""
    max_len = 4096
    body = text.strip() or "(no output)"
    body = _redact_secrets(body)
    for i in range(0, len(body), max_len):
        chunk = body[i : i + max_len]
        bot.send_message(chat_id, chunk, **send_kw)
        log_chat(
            "bot",
            chunk[:1000],
            telegram_user_id=telegram_user_id,
            telegram_shared_room_id=telegram_shared_room_id,
        )


def _arbos_user_state_path(group_id: int, user_id: int) -> Path:
    """Path to per-user STATE.md within a Telegram group."""
    p = CHATLOG_DIR / "group" / str(group_id) / "state" / f"{user_id}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _build_public_bittensor_prompt(
    user_text: str,
    user_label: str,
    chat_title: str | None,
    *,
    telegram_user_id: int | None = None,
    telegram_room_id: int | None = None,
) -> str:
    """Prompt for `/arbos`: fixed goal from file + per-user STATE.md + full toolkit."""
    room = chat_title or "this chat"
    chi = _chi_knowledge_section(compact=False)

    # Fixed goal from GOAL_TELEGRAM_BITTENSOR.md
    goal_text = _telegram_qa_fixed_goal_markdown()

    # Per-user persistent state
    state_text = ""
    state_path: Path | None = None
    if telegram_user_id is not None and telegram_room_id is not None:
        state_path = _arbos_user_state_path(telegram_room_id, telegram_user_id)
        if state_path.exists():
            state_text = state_path.read_text().strip()

    # Group chatlog (all members)
    group_ctx = ""
    if telegram_room_id is not None:
        g = load_chatlog_group(max_chars=2800, telegram_chat_id=telegram_room_id)
        if g:
            group_ctx = (
                "## Contexte salon (tous les membres — ce qu'ils ont demandé au bot)\n\n"
                f"{g}\n\n"
                "**Consigne :** tu **vois** ce que d'autres utilisateurs ont posé. Tu **réponds** au **membre courant** "
                f"({user_label}) : enchaîne sur **son** historique personnel ci‑dessous et sur "
                "**## Message**. Ne mélange pas les fils : la continuité est celle du **user_id** de ce tour.\n\n"
                "---\n\n"
            )

    # Per-user chatlog history
    hist = ""
    if telegram_user_id is not None:
        _h = load_chatlog(max_chars=3200, telegram_user_id=telegram_user_id)
        if _h:
            hist = _h + "\n\n"

    # State update instruction
    state_instruction = ""
    if state_path is not None:
        state_instruction = (
            f"\n\n## Mise à jour de l'état utilisateur\n\n"
            f"**Après avoir répondu**, écris (ou écrase) le fichier `{state_path}` avec un résumé concis "
            f"du contexte de **{user_label}** : niveau Bittensor, sujets récurrents, préférences, points clés "
            f"de la conversation. Ce fichier est relu à **chaque prochain `/arbos`** de cet utilisateur — "
            f"garde-le court et actionnable (< 300 mots). Si le fichier existe déjà, mets-le à jour en "
            f"intégrant les nouvelles informations de ce tour."
        )

    user_state_section = (
        f"## État utilisateur ({user_label})\n\n{state_text}\n\n"
        if state_text else ""
    )

    return (
        f"You are the **public Bittensor assistant** in « {room} » — shared Telegram **discussion / supergroup**.\n\n"
        "## Mission (goal fixe)\n\n"
        f"{goal_text}\n\n"
        f"{chi}"
        f"{user_state_section}"
        "## Langue\n"
        "**Réponse obligatoire en français.** Même si le message utilisateur est dans une autre langue, rédige toute la réponse en français "
        "(termes techniques anglais usuels : OK).\n\n"
        "## Requêtes lourdes (multi-subnets, scans larges)\n"
        "Pour toute requête qui couvre de nombreux subnets ou implique de nombreux appels CLI "
        "(ex. « top 5 miners sur les 128 subnets », « coldkey la plus répandue »), **écris un script Python** "
        "dans `/tmp/` et exécute-le avec Bash — ne fais **pas** 128 appels CLI individuels inline. "
        "Le script peut utiliser `subprocess`, `asyncio`, ou des threads pour paralléliser. "
        "Présente les résultats sous forme de tableau ou liste structurée.\n\n"
        "## Security\n"
        "Never read or echo `.env`, API keys, mnemonics, or coldkeys.\n\n"
        f"{group_ctx}"
        f"{hist}"
        f"## Message (demande actuelle de {user_label})\n{user_text}"
        f"{state_instruction}"
    )


_TOOL_LABELS = {
    "Bash": "running",
    "Read": "reading",
    "Write": "writing",
    "Edit": "editing",
    "Glob": "searching",
    "Grep": "locating",
    "WebFetch": "downloading",
    "WebSearch": "browsing",
    "TodoWrite": "planning",
    "Task": "executing",
    "Agent": "executing",
}

_CURSOR_TOOL_LABELS = {
    "shellToolCall": "running",
    "fileReadTool": "reading",
    "fileWriteTool": "writing",
    "fileEditTool": "editing",
    "listDirectoryTool": "listing",
    "searchTool": "searching",
    "webSearchTool": "browsing",
    "webFetchTool": "fetching",
    "createFileTool": "creating",
    "deleteFileTool": "deleting",
}


def _format_tool_activity(tool_name: str, tool_input: dict) -> str:
    label = _TOOL_LABELS.get(tool_name, tool_name)
    detail = ""
    if tool_name == "Bash":
        detail = (tool_input.get("command") or "")[:80]
    elif tool_name in ("Read", "Write", "Edit"):
        detail = (tool_input.get("file_path") or tool_input.get("path") or "")
        if detail:
            detail = detail.rsplit("/", 1)[-1]
    elif tool_name == "Glob":
        detail = (tool_input.get("pattern") or tool_input.get("glob") or "")[:60]
    elif tool_name == "Grep":
        detail = (tool_input.get("pattern") or tool_input.get("regex") or "")[:60]
    elif tool_name == "WebFetch":
        detail = (tool_input.get("url") or "")[:60]
    elif tool_name == "WebSearch":
        detail = (tool_input.get("query") or tool_input.get("search_term") or "")[:60]
    elif tool_name == "Task":
        detail = (tool_input.get("description") or "")[:60]

    if detail:
        return f"{label}: {detail}"
    return f"{label}..."


def run_agent_streaming(
    bot, prompt: str, chat_id: int, message_thread_id: int | None = None,
    workspace_id: int = 0,
    telegram_log_user_id: int | None = None,
    telegram_log_room_id: int | None = None,
) -> str:
    """Run agent CLI for Telegram: by default one final reply only; live edits if TELEGRAM_STREAMING_UPDATES=1."""
    stream_live = os.environ.get("TELEGRAM_STREAMING_UPDATES", "").lower() in (
        "1",
        "true",
        "yes",
    )
    send_kw: dict[str, Any] = {}
    if message_thread_id is not None:
        send_kw["message_thread_id"] = message_thread_id
    msg = None
    current_text = ""
    activity_status = ""
    last_edit = 0.0

    def _edit(text: str, force: bool = False):
        nonlocal last_edit
        if not stream_live or msg is None:
            return
        now = time.time()
        if not force and now - last_edit < 1.5:
            return
        display = text[-3800:] if len(text) > 3800 else text
        display = _redact_secrets(display)
        # Collapse 3+ consecutive blank lines into 2 to avoid giant blank spaces in Telegram.
        display = re.sub(r'\n{3,}', '\n\n', display).strip()
        if not display:
            return
        try:
            bot.edit_message_text(display, chat_id, msg.message_id)
            last_edit = now
        except Exception:
            pass

    # Always send an initial ack so the user sees something immediately,
    # even for heavy long-running queries (128 subnets etc.).
    try:
        msg = bot.send_message(chat_id, "⏳ Traitement en cours...", **send_kw)
    except Exception:
        msg = None

    def _on_text(text: str):
        nonlocal current_text
        current_text = text
        if stream_live:
            _edit(text)

    def _on_activity(status: str):
        nonlocal activity_status
        activity_status = status
        if stream_live and not current_text:
            _edit(status)

    on_activity_cb = _on_activity if stream_live else None

    stream_cwd = WORKING_DIR
    if workspace_id:
        stream_cwd = WORKSPACES_DIR / str(workspace_id)
        stream_cwd.mkdir(parents=True, exist_ok=True)
    wm = _effective_model(workspace_id)

    _claude_semaphore.acquire()
    last_stderr: str = ""
    last_returncode: int = 0
    last_raw_line_count: int = 0
    try:
        for attempt in range(1, MAX_RETRIES + 1):
            current_text = ""
            activity_status = ""
            last_edit = 0.0

            active_provider = _active_provider()

            if active_provider == "codex":
                active_cmd = _codex_cmd(prompt, model=wm, cwd=stream_cwd)
                env = os.environ.copy()
                env.pop("TAU_BOT_TOKEN", None)
                env["PYTHONUNBUFFERED"] = "1"
            elif active_provider == "opencode":
                active_cmd = _opencode_cmd(wm)
                env = os.environ.copy()
                env.pop("TAU_BOT_TOKEN", None)
                env["PYTHONUNBUFFERED"] = "1"
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps({
                    "model": f"opencode/{wm}",
                    "small_model": f"opencode/{wm}",
                    "autoupdate": os.environ.get("OPENCODE_AUTOUPDATE", "false").lower() == "true",
                    "snapshot": os.environ.get("OPENCODE_SNAPSHOT", "false").lower() == "true",
                })
            elif active_provider == "cursor":
                active_cmd = _cursor_cmd(prompt, model=wm, cwd=stream_cwd)
                env = os.environ.copy()
                env.pop("TAU_BOT_TOKEN", None)
                env["PYTHONUNBUFFERED"] = "1"
                if LLM_API_KEY:
                    env["CURSOR_API_KEY"] = LLM_API_KEY
            elif active_provider in ("openrouter", "anthropic"):
                active_cmd = _claude_cmd(prompt, model=wm)
                env = _claude_env(workspace_id=workspace_id)
            else:
                active_cmd = _claude_cmd(prompt, extra_flags=["--model", "bot"])
                env = _claude_env(workspace_id=workspace_id)

            if active_provider == "codex":
                returncode, result_text, raw_lines, stderr_output = _run_codex_once(
                    active_cmd, env, on_text=_on_text, on_activity=on_activity_cb, cwd=stream_cwd,
                )
            elif active_provider == "opencode":
                returncode, result_text, raw_lines, stderr_output = _run_opencode_once(
                    active_cmd, env, on_text=_on_text, on_activity=on_activity_cb, prompt=prompt,
                    cwd=stream_cwd,
                )
            elif active_provider == "cursor":
                returncode, result_text, raw_lines, stderr_output = _run_cursor_once(
                    active_cmd, env, on_text=_on_text, on_activity=on_activity_cb, cwd=stream_cwd,
                )
            else:
                returncode, result_text, raw_lines, stderr_output = _run_claude_once(
                    active_cmd, env, on_text=_on_text, on_activity=on_activity_cb, cwd=stream_cwd,
                )
            last_stderr = stderr_output or ""
            last_returncode = int(returncode)
            last_raw_line_count = len(raw_lines)

            if result_text.strip():
                current_text = result_text
                break
            if current_text.strip():
                # Stream-json had assistant text but no final `result` line — still show it.
                break

            combined_err = f"{stderr_output} {result_text}"
            if returncode != 0 and _is_quota_error(combined_err) and not _using_fallback:
                _log("streaming: quota/rate-limit detected, switching to fallback")
                _switch_to_fallback()
                if stream_live:
                    _edit("Quota limit — switching to fallback, retrying...", force=True)
                continue

            if returncode != 0 and attempt < MAX_RETRIES:
                delay = min(2 ** attempt, 30)
                if stream_live:
                    _edit(
                        f"Error, retrying in {delay}s... (attempt {attempt}/{MAX_RETRIES})",
                        force=True,
                    )
                else:
                    _log(
                        f"telegram agent: retry in {delay}s (attempt {attempt}/{MAX_RETRIES})",
                    )
                time.sleep(delay)
                continue
            break

        if not current_text.strip():
            parts_err = [
                "L'agent n'a pas renvoyé de texte exploitable (sortie vide ou format inattendu). "
                "Requêtes très lourdes (ex. balayer 128 subnets) peuvent échouer ou être tronquées — "
                "essayez une plage plus petite ou une sous-question précise.",
            ]
            if last_stderr.strip():
                parts_err.append(
                    "Détail CLI (stderr) :\n```\n"
                    + _redact_secrets(last_stderr.strip()[:1800])
                    + "\n```",
                )
            if last_returncode not in (0,):
                parts_err.append(f"Code retour du processus : {last_returncode}")
            if last_raw_line_count == 0:
                parts_err.append(
                    "Aucune sortie JSON sur stdout — vérifier `claude --version`, les clés API (OpenRouter), et `pm2 logs`.",
                )
            else:
                parts_err.append(
                    f"{last_raw_line_count} ligne(s) reçue(s) sans texte assistant final — "
                    "voir logs serveur ou activer `TELEGRAM_STREAMING_UPDATES=true` pour suivre l'activité.",
                )
            current_text = "\n\n".join(parts_err)

        if stream_live:
            _edit(current_text, force=True)
            if not current_text.strip():
                try:
                    bot.edit_message_text("(no output)", chat_id, msg.message_id)
                except Exception:
                    pass
        else:
            # Replace the "⏳ Traitement..." ack with the first chunk, then send extra chunks.
            body = _redact_secrets(current_text.strip()) or "(no output)"
            max_len = 4096
            chunks = [body[i: i + max_len] for i in range(0, len(body), max_len)]
            first_replaced = False
            if msg is not None and chunks:
                try:
                    bot.edit_message_text(chunks[0], chat_id, msg.message_id)
                    log_chat(
                        "bot", chunks[0][:1000],
                        telegram_user_id=telegram_log_user_id,
                        telegram_shared_room_id=telegram_log_room_id,
                    )
                    first_replaced = True
                except Exception:
                    pass
            for i, chunk in enumerate(chunks):
                if i == 0 and first_replaced:
                    continue
                bot.send_message(chat_id, chunk, **send_kw)
                log_chat(
                    "bot", chunk[:1000],
                    telegram_user_id=telegram_log_user_id,
                    telegram_shared_room_id=telegram_log_room_id,
                )
            if not chunks and msg is not None:
                try:
                    bot.edit_message_text("(no output)", chat_id, msg.message_id)
                except Exception:
                    pass

    except Exception as e:
        err = _redact_secrets(f"Error: {str(e)[:500]}")
        try:
            if msg is not None:
                bot.edit_message_text(err, chat_id, msg.message_id)
            else:
                bot.send_message(chat_id, err, **send_kw)
        except Exception:
            pass
    finally:
        _claude_semaphore.release()

    return current_text


def _telegram_owner_ids() -> frozenset[int]:
    """Telegram users allowed full operator control (comma list + legacy TELEGRAM_OWNER_ID)."""
    out: set[int] = set()
    for raw in (
        os.environ.get("TELEGRAM_OWNER_IDS", "").strip(),
        os.environ.get("TELEGRAM_OWNER_ID", "").strip(),
    ):
        if not raw:
            continue
        for part in raw.replace(" ", "").split(","):
            if not part:
                continue
            try:
                out.add(int(part))
            except ValueError:
                _log(f"TELEGRAM_OWNER*: skipped invalid id {part!r}")
    return frozenset(out)


def _is_owner(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in _telegram_owner_ids()


def _enroll_owner(user_id: int):
    """Auto-enroll the first /start user as the owner and persist."""
    owner_id = str(user_id)
    os.environ["TELEGRAM_OWNER_ID"] = owner_id
    env_path = WORKING_DIR / ".env"
    if env_path.exists():
        existing = env_path.read_text()
        if "TELEGRAM_OWNER_ID" not in existing:
            with open(env_path, "a") as f:
                f.write(f"\nTELEGRAM_OWNER_ID='{owner_id}'\n")
    elif ENV_ENC_FILE.exists():
        _save_to_encrypted_env("TELEGRAM_OWNER_ID", owner_id)
    _log(f"enrolled owner: {owner_id}")


def run_bot():
    """Run the Telegram bot."""
    token = os.getenv("TAU_BOT_TOKEN")
    if not token:
        _log("TAU_BOT_TOKEN not set; add it to .env and restart")
        sys.exit(1)

    import telebot
    bot = telebot.TeleBot(token)

    public_chat_ids = _telegram_public_chat_ids_from_env()
    workspace_group_ids = _telegram_workspace_group_ids_from_env()

    def _is_public_qa_chat(cid: int) -> bool:
        return cid in public_chat_ids

    def _telegram_member_arbos_chat(cid: int) -> bool:
        """Configured public or workspace group: members invoke the agent with `/arbos …`."""
        return _is_public_qa_chat(cid) or cid in workspace_group_ids

    def _strip_arbos_leading_command(text: str) -> str | None:
        """If *text* starts with `/arbos` (optional @botname), return the rest (may be ''). Else None."""
        t = (text or "").strip()
        if not t.startswith("/"):
            return None
        parts = t.split(maxsplit=1)
        cmd = parts[0].split("@", 1)[0]
        if cmd != "/arbos":
            return None
        return parts[1].strip() if len(parts) > 1 else ""

    if public_chat_ids:
        _log(f"public Bittensor Q&A chats: {sorted(public_chat_ids)}")
    if workspace_group_ids:
        _log(f"Telegram workspace groups (per-group context/): {sorted(workspace_group_ids)}")

    def _goals_map_for_chat(cid: int) -> tuple[dict[int, GoalState], int]:
        if cid in workspace_group_ids:
            return _tg_goals_map(cid), cid
        return _goals, 0

    def _ensure_tg_workspace_meta(cid: int, title: str | None):
        base = WORKSPACES_DIR / str(cid)
        base.mkdir(parents=True, exist_ok=True)
        meta = base / "workspace.json"
        if not meta.exists():
            meta.write_text(
                json.dumps({"telegram_chat_id": cid, "name": title or str(cid)}, indent=2),
            )

    def _forum_reply_thread(message) -> int | None:
        if getattr(message.chat, "is_forum", False):
            tid = getattr(message, "message_thread_id", None)
            if tid:
                return int(tid)
        return None

    def _active_topic_goal_key(message, cid: int) -> int | None:
        if cid not in workspace_group_ids:
            return None
        tid = getattr(message, "message_thread_id", None)
        if tid and int(tid) in _tg_goals_map(cid):
            return int(tid)
        return None

    def _save_chat_id(chat_id: int):
        CHAT_ID_FILE.write_text(str(chat_id))

    def _parse_step_delay_arg(raw: str) -> int:
        """Seconds between steps. `90`, `90s`, `2m`, `3min` (Discord uses minutes; we accept both)."""
        s = raw.strip().lower()
        if s.endswith("min"):
            return int(s[:-3].strip()) * 60
        if len(s) > 1 and s.endswith("m") and s[:-1].strip().isdigit():
            return int(s[:-1].strip()) * 60
        if s.endswith("s"):
            s = s[:-1].strip()
        return int(s)

    def _telegram_reply_prefix(message) -> str:
        """Discord-style quote when replying to the bot (forum or general)."""
        rep = getattr(message, "reply_to_message", None)
        if not rep:
            return ""
        txt = (getattr(rep, "text", None) or "").strip()
        if not txt or not getattr(rep.from_user, "is_bot", False):
            return ""
        return f"[Replying to Arbos: \"{txt[:1000]}\"]\n\n"

    def _goal_index_from_context(message, gmap: dict[int, GoalState], cid: int) -> int | None:
        tid = getattr(message, "message_thread_id", None)
        if tid is None:
            return None
        i = int(tid)
        return i if i in gmap else None

    def _reject(message):
        uid = message.from_user.id if message.from_user else None
        cid = message.chat.id
        _log(f"rejected message from unauthorized user {uid} chat={cid}")
        if not _telegram_owner_ids():
            bot.send_message(
                cid,
                "No owner yet — open a **private chat** with this bot and send /start once.",
                parse_mode="Markdown",
            )
        elif _is_public_qa_chat(cid):
            bot.send_message(
                cid,
                "Réservé aux opérateurs. Pour poser une question : `/arbos` puis votre texte (voix/photo/fichier : légende `/arbos …`).",
                parse_mode="Markdown",
            )
        elif cid in workspace_group_ids:
            bot.send_message(
                cid,
                "Réservé aux opérateurs. Question : `/arbos` … (médias : légende `/arbos …`).",
                parse_mode="Markdown",
            )
        else:
            bot.send_message(cid, "Unauthorized.")

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        uid = message.from_user.id if message.from_user else None
        chat = message.chat
        if not _telegram_owner_ids() and uid is not None:
            if getattr(chat, "type", "") == "private":
                _enroll_owner(uid)
            else:
                bot.send_message(
                    chat.id,
                    "No owner yet. The first /start must be in **private chat** with this bot.",
                    parse_mode="Markdown",
                )
                return
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        _save_chat_id(cid)
        args = (message.text or "").split()
        gmap, ws = _goals_map_for_chat(cid)
        if len(args) < 2:
            bot.send_message(
                cid,
                "Use `/goal` … In workspace groups the loop **auto-starts**.\n"
                "Commands: `/help` / `/ls` / `/goal` / `/start` / `/pause` / `/unpause` / `/force` "
                "/ `/delay` / `/bash` / `/env` / `/model` / …",
                parse_mode="Markdown",
            )
            return
        try:
            idx = int(args[1])
        except ValueError:
            bot.send_message(cid, "Usage: /start <goal_index>")
            return
        with _goals_lock:
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            gs.started = True
            gs.paused = False
            gs.wake.set()
            _save_goals(ws)
        kw = {}
        th = _forum_reply_thread(message)
        if th is not None:
            kw["message_thread_id"] = th
        bot.send_message(cid, f"Goal #{idx} started: {gs.summary}", **kw)
        _log(f"goal #{idx} started via /start (workspace {ws})")

    @bot.message_handler(commands=["ls"])
    def handle_ls(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        if not gmap:
            bot.send_message(cid, "No goals in this workspace. Use /goal <text> to create one.")
            return
        lines = []
        for idx in sorted(gmap.keys()):
            gs = gmap[idx]
            status = _goal_status_label(gs)
            last = _format_last_time(gs.last_finished)
            delay_str = f" delay:{gs.delay}s" if gs.delay else ""
            lines.append(f"#{idx} [{status}]{delay_str} last:{last} - {gs.summary}")
        bot.send_message(cid, "\n".join(lines))

    @bot.message_handler(commands=["status"])
    def handle_status(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        args = (message.text or "").split()
        if len(args) >= 2:
            try:
                idx = int(args[1])
            except ValueError:
                bot.send_message(cid, "Usage: /status [goal_index]")
                return
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            status = _goal_status_label(gs)
            gf = _goal_file(idx, ws)
            goal_text = gf.read_text().strip()[:500] if gf.exists() else "(empty)"
            sf = _state_file(idx, ws)
            state_text = sf.read_text().strip()[:500] if sf.exists() else "(empty)"
            lines = [
                f"Goal #{idx} [{status}] (delay: {gs.delay}s, step {gs.step_count})",
                f"Last run: {gs.last_run or 'never'}",
                f"Last finished: {gs.last_finished or 'never'}",
                "",
                f"Goal: {goal_text}",
                "",
                f"State: {state_text}",
            ]
            bot.send_message(cid, "\n".join(lines))
        else:
            if not gmap:
                bot.send_message(cid, f"No goals in this workspace. Total steps: {_step_count}")
                return
            lines = [f"Total steps: {_step_count}"]
            if ws:
                lines.append(f"Workspace: `{ws}` (goals on disk: context/workspace/{ws}/)")
            for idx in sorted(gmap.keys()):
                gs = gmap[idx]
                status = _goal_status_label(gs)
                last = _format_last_time(gs.last_finished)
                delay_str = f" delay:{gs.delay}s" if gs.delay else ""
                lines.append(f"#{idx} [{status}]{delay_str} last:{last} - {gs.summary}")
            bot.send_message(cid, "\n".join(lines))

    @bot.message_handler(commands=["stop"])
    def handle_stop(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        with _goals_lock:
            count = 0
            for gs in gmap.values():
                if gs.started:
                    gs.started = False
                    gs.stop_event.set()
                    gs.wake.set()
                    count += 1
            _save_goals(ws)
        scope = f"workspace `{ws}`" if ws else "legacy workspace"
        bot.send_message(cid, f"Stopped {count} goal(s) ({scope}).")
        _log(f"goals stopped via /stop ({count}, workspace {ws})")

    @bot.message_handler(commands=["pause"])
    def handle_pause(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        args = (message.text or "").split()
        if len(args) < 2:
            bot.send_message(cid, "Usage: /pause <goal_index>")
            return
        try:
            idx = int(args[1])
        except ValueError:
            bot.send_message(cid, "Usage: /pause <goal_index>")
            return
        with _goals_lock:
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            if gs.paused:
                bot.send_message(cid, f"Goal #{idx} already paused.")
                return
            gs.paused = True
            _save_goals(ws)
        bot.send_message(cid, f"Goal #{idx} paused. Use /start {idx} to resume.")
        _log(f"goal #{idx} paused via /pause (workspace {ws})")

    @bot.message_handler(commands=["delay"])
    def handle_delay(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        args = (message.text or "").split()
        if len(args) < 3:
            bot.send_message(
                cid,
                "Usage: /delay <goal_index> <delay>\n"
                "Examples: `/delay 3 120` (seconds), `/delay 3 2m`, `/delay 3 5min`",
            )
            return
        try:
            idx = int(args[1])
            seconds = _parse_step_delay_arg(args[2])
        except ValueError:
            bot.send_message(cid, "Usage: /delay <goal_index> <delay> (number, optional s/m/min)")
            return
        if seconds < 0:
            bot.send_message(cid, "Delay must be >= 0.")
            return
        with _goals_lock:
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            gs.delay = seconds
            _save_goals(ws)
        bot.send_message(cid, f"Goal #{idx} delay set to {seconds}s ({seconds // 60}m).")
        _log(f"goal #{idx} delay set to {seconds}s via /delay (workspace {ws})")

    @bot.message_handler(commands=["unpause"])
    def handle_unpause(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        args = (message.text or "").split()
        idx = _goal_index_from_context(message, gmap, cid)
        if idx is None and len(args) >= 2:
            try:
                idx = int(args[1])
            except ValueError:
                idx = None
        if idx is None:
            bot.send_message(
                cid,
                "Usage: /unpause <goal_index> or run inside a **forum topic** that is a goal.",
            )
            return
        with _goals_lock:
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            if not gs.paused:
                bot.send_message(cid, f"Goal #{idx} is not paused.")
                return
            gs.paused = False
            gs.wake.set()
            _save_goals(ws)
        bot.send_message(cid, f"Goal #{idx} resumed: {gs.summary}")
        _log(f"goal #{idx} unpaused (workspace {ws})")

    @bot.message_handler(commands=["force"])
    def handle_force(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        args = (message.text or "").split()
        idx = _goal_index_from_context(message, gmap, cid)
        if idx is None and len(args) >= 2:
            try:
                idx = int(args[1])
            except ValueError:
                idx = None
        if idx is None:
            bot.send_message(
                cid,
                "Usage: /force <goal_index> or inside a **forum topic** goal — runs next step immediately.",
            )
            return
        with _goals_lock:
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            if gs.paused:
                bot.send_message(cid, f"Goal #{idx} is paused. Use /unpause first.")
                return
            gs.force_next = True
            gs.wake.set()
            _save_goals(ws)
        bot.send_message(cid, f"Goal #{idx}: forcing next step.")
        _log(f"goal #{idx} force_next (workspace {ws})")

    @bot.message_handler(commands=["goal"])
    def handle_goal(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        text = (message.text or "").split(None, 1)
        if len(text) < 2 or not text[1].strip():
            bot.send_message(cid, "Usage: /goal <your goal text>")
            return
        goal_text = text[1].strip()
        if ws:
            _ensure_tg_workspace_meta(cid, message.chat.title)
        send_kw: dict[str, Any] = {}
        th0 = _forum_reply_thread(message)
        if th0 is not None:
            send_kw["message_thread_id"] = th0
        msg = bot.send_message(cid, "Creating goal...", **send_kw)
        summary = _summarize_goal(goal_text)
        new_idx: int | None = None
        body = goal_text
        if ws and getattr(message.chat, "is_forum", False):
            topic_line = goal_text.split("\n", 1)[0].strip()[:128] or (
                summary[:128] if summary else "goal"
            )
            try:
                topic = bot.create_forum_topic(cid, topic_line)
                tid = getattr(topic, "message_thread_id", None)
                if tid is None and isinstance(topic, dict):
                    tid = topic.get("message_thread_id")
                if tid is not None:
                    new_idx = int(tid)
                    body = (
                        goal_text.split("\n", 1)[1].strip()
                        if "\n" in goal_text
                        else goal_text
                    )
            except Exception as exc:
                _log(f"create_forum_topic failed: {str(exc)[:160]}")
        with _goals_lock:
            if new_idx is not None:
                idx = new_idx
            else:
                idx = max(gmap.keys(), default=0) + 1
            gs = GoalState(index=idx, summary=summary)
            gmap[idx] = gs
            gdir = _goal_dir(idx, ws)
            gdir.mkdir(parents=True, exist_ok=True)
            _goal_file(idx, ws).write_text(body)
            _state_file(idx, ws).write_text("")
            _inbox_file(idx, ws).write_text("")
            _goal_runs_dir(idx, ws).mkdir(parents=True, exist_ok=True)
            if ws:
                gs.started = True
                gs.paused = False
                gs.wake.set()
            _save_goals(ws)
        detail = (
            f"Goal #{idx} created: {summary}\n"
            + (
                "**Loop started** (Discord-style). Commands: /pause /unpause /force /delay"
                if ws
                else f"Use /start {idx} to begin."
            )
            + (f"\n(Forum topic id {idx}.)" if new_idx else "")
        )
        bot.edit_message_text(detail, cid, msg.message_id)
        if new_idx is not None:
            try:
                bot.send_message(
                    cid,
                    f"Goal #{idx} — {summary}\n/start {idx}",
                    message_thread_id=new_idx,
                )
            except Exception as exc:
                _log(f"post forum topic follow-up failed: {str(exc)[:120]}")
        _log(f"goal #{idx} created ({len(goal_text)} chars, ws={ws}): {summary}")

    @bot.message_handler(commands=["delete"])
    def handle_delete(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        args = (message.text or "").split()
        if len(args) < 2:
            bot.send_message(cid, "Usage: /delete <goal_index>")
            return
        try:
            idx = int(args[1])
        except ValueError:
            bot.send_message(cid, "Usage: /delete <goal_index>")
            return
        with _goals_lock:
            gs = gmap.get(idx)
            if not gs:
                bot.send_message(cid, f"Goal #{idx} not found.")
                return
            gs.stop_event.set()
            gs.wake.set()
            gs.started = False
            thread = gs.thread
            del gmap[idx]
            _save_goals(ws)
        if thread and thread.is_alive():
            thread.join(timeout=5)
        import shutil
        gdir = _goal_dir(idx, ws)
        if gdir.exists():
            shutil.rmtree(gdir, ignore_errors=True)
        bot.send_message(cid, f"Goal #{idx} deleted.")
        _log(f"goal #{idx} deleted via /delete (workspace {ws})")

    @bot.message_handler(commands=["clear"])
    def handle_clear(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        import shutil
        cid = message.chat.id
        gmap, ws = _goals_map_for_chat(cid)
        if ws:
            with _goals_lock:
                for gs in gmap.values():
                    gs.stop_event.set()
                    gs.wake.set()
                gmap.clear()
                _save_goals(ws)
            d = WORKSPACES_DIR / str(ws)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            _ensure_tg_workspace_meta(cid, message.chat.title)
            bot.send_message(
                cid,
                f"Cleared Telegram workspace `{ws}` (`context/workspace/{ws}/`).\nReady for a fresh /goal.",
            )
            _log(f"cleared workspace {ws} via /clear")
            return
        with _goals_lock:
            for gs in _goals.values():
                gs.stop_event.set()
                gs.wake.set()
            _goals.clear()
        removed = []
        if CONTEXT_DIR.exists():
            shutil.rmtree(CONTEXT_DIR)
            removed.append("context/")
        try:
            r = subprocess.run(
                ["git", "checkout", "HEAD", "--", "."],
                cwd=WORKING_DIR, capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                removed.append("git checkout (restored tracked files)")
        except Exception:
            pass
        try:
            r = subprocess.run(
                ["git", "clean", "-fd", "--exclude=.env*", "--exclude=chat_id.txt",
                 "--exclude=.venv", "--exclude=__pycache__", "--exclude=.claude"],
                cwd=WORKING_DIR, capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                removed.append(f"git clean ({len(r.stdout.splitlines())} items)")
        except Exception:
            pass
        CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        summary = ", ".join(removed) if removed else "nothing to clear"
        WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        bot.send_message(cid, f"Cleared: {summary}\nReady for a fresh /goal.")
        _log(f"cleared via /clear command: {summary}")

    @bot.message_handler(commands=["model"])
    def handle_model(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        parts = message.text.split(maxsplit=1)
        provider = _active_provider()
        model = _active_model()
        gmap, ws = _goals_map_for_chat(cid)
        if len(parts) < 2 or not parts[1].strip():
            extra = ""
            if ws:
                wm = _read_workspace_model(ws)
                extra = f"\nWorkspace model override: `{wm or '(default)'}`"
            bot.send_message(
                cid,
                f"Current: `{provider}/{model}`{extra}\n\n"
                "Usage: `/model <model_name>`\n"
                "In a **workspace** supergroup (`TELEGRAM_WORKSPACE_GROUP_IDS`), this updates "
                "`context/workspace/<chat_id>/workspace.json` for goals and ad-hoc runs in that chat only.\n"
                "Otherwise it queues `context/.env.pending` for restart.",
                parse_mode="Markdown",
            )
            return
        new_model = parts[1].strip()
        if ws:
            _ensure_tg_workspace_meta(cid, message.chat.title)
            p = _workspace_json_path(ws)
            meta: dict[str, Any] = {}
            if p.exists():
                try:
                    meta = json.loads(p.read_text())
                except (json.JSONDecodeError, OSError):
                    meta = {}
            meta["model"] = new_model
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(meta, indent=2))
            bot.send_message(
                cid,
                f"Workspace model set to `{new_model}` (this supergroup only).",
                parse_mode="Markdown",
            )
            _log(f"/model: workspace {ws} -> {new_model}")
            return
        key = {
            "cursor": "CURSOR_MODEL",
            "codex": "CODEX_MODEL",
            "opencode": "OPENCODE_MODEL",
        }.get(provider, "CLAUDE_MODEL")
        pending = CONTEXT_DIR / ".env.pending"
        pending.parent.mkdir(parents=True, exist_ok=True)
        with open(pending, "a") as f:
            f.write(f"{key}='{new_model}'\n")
        bot.send_message(
            cid,
            f"Model queued: `{key}={new_model}`\nWill apply on next restart.",
            parse_mode="Markdown",
        )
        _log(f"/model: queued {key}={new_model}")

    @bot.message_handler(commands=["env"])
    def handle_env(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        raw = (message.text or "").strip()
        rest = raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) > 1 else ""

        if not rest:
            keys = _list_env_keys_arbos()
            listing = "\n".join(f"• `{k}`" for k in sorted(keys)) if keys else "(none)"
            body = f"**Environment keys** (values not shown):\n{listing}"
            if uid is not None:
                try:
                    bot.send_message(uid, body[:4000], parse_mode="Markdown")
                    bot.send_message(cid, "Key list sent in **your** private chat with the bot.", parse_mode="Markdown")
                    return
                except Exception:
                    pass
            bot.send_message(cid, body[:4000], parse_mode="Markdown")
            return

        toks = rest.split(maxsplit=1)
        head = toks[0]
        if head == "-d":
            if len(toks) < 2:
                bot.send_message(cid, "Usage: `/env -d KEY`", parse_mode="Markdown")
                return
            del_key = toks[1].strip().split()[0]
            try:
                _delete_env_key_arbos(del_key)
                _reload_env_secrets()
            except Exception as exc:
                bot.send_message(cid, f"Delete failed: {str(exc)[:200]}")
                return
            bot.send_message(cid, f"Deleted `{del_key}` from env.")
            _log(f"/env deleted {del_key}")
            return

        if len(toks) < 2:
            bot.send_message(cid, "Usage: `/env KEY VALUE` or `/env` or `/env -d KEY`", parse_mode="Markdown")
            return
        e_key, e_val = toks[0], toks[1]
        env_path = WORKING_DIR / ".env"
        try:
            if env_path.exists():
                lines = env_path.read_text().splitlines()
                updated = False
                for i, line in enumerate(lines):
                    stripped = line.split("#")[0].strip()
                    if stripped.startswith(f"{e_key}="):
                        lines[i] = f"{e_key}='{e_val}'"
                        updated = True
                        break
                if not updated:
                    lines.append(f"{e_key}='{e_val}'")
                env_path.write_text("\n".join(lines).rstrip() + "\n")
            elif ENV_ENC_FILE.exists():
                _save_to_encrypted_env(e_key, e_val)
            else:
                env_path.write_text(f"{e_key}='{e_val}'\n")
            os.environ[e_key] = e_val
            _reload_env_secrets()
        except Exception as exc:
            bot.send_message(cid, f"Failed: {str(exc)[:200]}")
            _log(f"/env set failed: {exc!s}"[:200])
            return
        bot.send_message(cid, f"Set `{e_key}` (restart if a running process must pick it up).", parse_mode="Markdown")
        _log(f"/env set {e_key}")

    @bot.message_handler(commands=["bash"])
    def handle_bash(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.send_message(cid, "Usage: `/bash <shell command>`")
            return
        command = parts[1].strip()
        _, ws = _goals_map_for_chat(cid)
        bash_cwd = (WORKSPACES_DIR / str(ws)) if ws else WORKING_DIR
        bash_cwd.mkdir(parents=True, exist_ok=True)

        msg = bot.send_message(cid, "Running…")

        def _run():
            try:
                r = subprocess.run(
                    command, shell=True, cwd=str(bash_cwd),
                    capture_output=True, text=True, timeout=120,
                )
                out = (r.stdout or "").strip()
                err = (r.stderr or "").strip()
                bits = []
                if out:
                    bits.append(out)
                if err:
                    bits.append("stderr:\n" + err)
                body = "\n".join(bits) if bits else "(no output)"
                body = _redact_secrets(body)[:3500]
                header = f"$ `{command[:200]}` rc={r.returncode}\n"
                try:
                    bot.edit_message_text(header + f"```\n{body}\n```", cid, msg.message_id, parse_mode="Markdown")
                except Exception:
                    bot.edit_message_text(header + body[:3800], cid, msg.message_id)
            except subprocess.TimeoutExpired:
                bot.edit_message_text("(command timed out after 120s)", cid, msg.message_id)
            except Exception as exc:
                bot.edit_message_text(f"Error: {str(exc)[:500]}", cid, msg.message_id)

        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=["help"])
    def handle_help(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        cid = message.chat.id
        gmap, _ = _goals_map_for_chat(cid)
        tid = getattr(message, "message_thread_id", None)
        in_goal = bool(tid and int(tid) in gmap)
        if in_goal:
            txt = (
                "**Goal topic (forum)**\n"
                "• `/pause` / `/unpause` / `/force` — or pass goal id from General\n"
                "• `/delay <id> <delay>` — seconds or `2m` / `5min`\n"
                "• `/delete <id>` · `/model` · `/status`\n"
                "• `/help`"
            )
        else:
            txt = (
                "**Operator**\n"
                "• `/goal` — workspace: **auto-starts** loop (forum: new topic)\n"
                "• `/start` / `/stop` / `/ls` / `/clear` / `/restart` / `/update`\n"
                "• `/bash` — shell in workspace dir (or repo root if not a workspace chat)\n"
                "• `/env` — list (DM) / set / `-d` delete\n"
                "• `/model` — per-workspace or `.env.pending`\n"
                "• Public/workspace groups: **members** → `/arbos` … ; you → normal message or `/arbos` (reply = quote context)"
            )
        bot.send_message(cid, txt, parse_mode="Markdown")

    @bot.message_handler(commands=["arbos"])
    def handle_arbos(message):
        uid = message.from_user.id if message.from_user else None
        cid = message.chat.id
        if uid is None or not _telegram_member_arbos_chat(cid):
            return
        rest = _strip_arbos_leading_command(message.text or "")
        if rest is None:
            return
        tw_kw: dict[str, Any] = {}
        th = _forum_reply_thread(message)
        if th is not None:
            tw_kw["message_thread_id"] = th
        if not rest.strip():
            bot.send_message(
                cid,
                "Utilisation : `/arbos` suivre de votre question.\n"
                "Voix / image / fichier : joindre une **légende** qui commence par `/arbos …`.",
                parse_mode="Markdown",
                **tw_kw,
            )
            return
        _save_chat_id(cid)
        rid = cid if cid < 0 else None
        u = message.from_user
        who = f"@{u.username}" if u.username else (u.first_name or str(uid))
        tag = "public" if _is_public_qa_chat(cid) else "group"
        log_chat(
            "user",
            f"[{tag} /arbos {who}] {rest}"[:1500],
            telegram_user_id=uid,
            telegram_shared_room_id=rid,
        )
        tw = cid if cid in workspace_group_ids else 0
        if _is_owner(uid):
            topic_g = _active_topic_goal_key(message, cid)
            prompt = _build_operator_prompt(
                _telegram_reply_prefix(message) + rest,
                telegram_workspace_id=tw,
                active_topic_goal=topic_g,
                arbos_reply_french=True,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )
        else:
            prompt = _build_public_bittensor_prompt(
                rest,
                who,
                message.chat.title,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )

        def _run():
            response = run_agent_streaming(
                bot,
                prompt,
                cid,
                message_thread_id=th,
                workspace_id=tw,
                telegram_log_user_id=uid,
                telegram_log_room_id=rid,
            )
            log_chat(
                "bot",
                response[:1000],
                telegram_user_id=uid,
                telegram_shared_room_id=rid,
            )
            _process_pending_env()

        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=["restart"])
    def handle_restart(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        if getattr(message.chat, "is_forum", False) and getattr(message, "message_thread_id", None):
            bot.send_message(
                message.chat.id,
                "Use /restart in the **main** forum chat, not inside a topic.",
            )
            return
        bot.send_message(message.chat.id, "Restarting — killing agent and exiting for pm2...")
        _log("restart requested via /restart command")
        _kill_child_procs()
        RESTART_FLAG.touch()

    @bot.message_handler(commands=["update"])
    def handle_update(message):
        uid = message.from_user.id if message.from_user else None
        if not _is_owner(uid):
            _reject(message)
            return
        msg = bot.send_message(message.chat.id, "Pulling latest changes...")
        try:
            r = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=WORKING_DIR, capture_output=True, text=True, timeout=30,
            )
            output = (r.stdout.strip() + "\n" + r.stderr.strip()).strip()
            if r.returncode != 0:
                bot.edit_message_text(f"Git pull failed:\n{output[:3800]}", message.chat.id, msg.message_id)
                _log(f"update failed: {output[:200]}")
                return
            bot.edit_message_text(f"Pulled:\n{output[:3800]}\n\nRestarting...", message.chat.id, msg.message_id)
            _log(f"update pulled: {output[:200]}")
        except Exception as exc:
            bot.edit_message_text(f"Git pull error: {str(exc)[:3800]}", message.chat.id, msg.message_id)
            _log(f"update error: {str(exc)[:200]}")
            return
        _kill_child_procs()
        RESTART_FLAG.touch()

    @bot.message_handler(content_types=["voice", "audio"])
    def handle_voice(message):
        uid = message.from_user.id if message.from_user else None
        cid0 = message.chat.id
        cap0 = message.caption or ""
        arbos_x = _strip_arbos_leading_command(cap0)
        gated0 = _telegram_member_arbos_chat(cid0)
        if _is_owner(uid):
            pass
        elif uid is not None and gated0 and arbos_x is not None:
            pass
        elif gated0:
            return
        else:
            _reject(message)
            return
        _save_chat_id(message.chat.id)
        bot.send_message(message.chat.id, "Transcribing voice note...")

        voice_or_audio = message.voice or message.audio
        file_info = bot.get_file(voice_or_audio.file_id)
        downloaded = bot.download_file(file_info.file_path)

        ext = file_info.file_path.rsplit(".", 1)[-1] if "." in file_info.file_path else "ogg"
        tmp_path = WORKING_DIR / f"_voice_tmp.{ext}"
        tmp_path.write_bytes(downloaded)

        try:
            transcript = transcribe_voice(str(tmp_path), fmt=ext)
        finally:
            tmp_path.unlink(missing_ok=True)

        caption = message.caption or ""
        user_text = f"[Voice note transcription]: {transcript}"
        if caption:
            if not _is_owner(uid) and arbos_x is not None:
                if arbos_x.strip():
                    user_text += f"\n[Caption]: {arbos_x}"
            else:
                user_text += f"\n[Caption]: {caption}"

        cid = message.chat.id
        rid = cid if cid < 0 else None
        log_chat(
            "user", user_text[:1000], telegram_user_id=uid, telegram_shared_room_id=rid,
        )
        if _is_owner(uid):
            tw = cid if cid in workspace_group_ids else 0
            topic_g = _active_topic_goal_key(message, cid)
            prompt = _build_operator_prompt(
                _telegram_reply_prefix(message) + user_text,
                telegram_workspace_id=tw,
                active_topic_goal=topic_g,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )
        else:
            u = message.from_user
            who = f"@{u.username}" if u.username else (u.first_name or str(uid))
            prompt = _build_public_bittensor_prompt(
                user_text,
                who,
                message.chat.title,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )

        def _run():
            th = _forum_reply_thread(message)
            tw_run = cid if cid in workspace_group_ids else 0
            response = run_agent_streaming(
                bot,
                prompt,
                cid,
                message_thread_id=th,
                workspace_id=tw_run,
                telegram_log_user_id=uid,
                telegram_log_room_id=rid,
            )
            log_chat(
                "bot",
                response[:1000],
                telegram_user_id=uid,
                telegram_shared_room_id=rid,
            )
            _process_pending_env()

        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(content_types=["document"])
    def handle_document(message):
        uid = message.from_user.id if message.from_user else None
        cid = message.chat.id
        cap0 = message.caption or ""
        arbos_x = _strip_arbos_leading_command(cap0)
        gated0 = _telegram_member_arbos_chat(cid)
        if _is_owner(uid):
            pass
        elif uid is not None and gated0 and arbos_x is not None:
            pass
        elif gated0:
            return
        else:
            _reject(message)
            return
        _save_chat_id(cid)

        doc = message.document
        filename = doc.file_name or f"file_{doc.file_id[:8]}"
        saved_path = _download_telegram_file(bot, doc.file_id, filename)

        caption = message.caption or ""
        size_kb = doc.file_size / 1024 if doc.file_size else saved_path.stat().st_size / 1024
        user_text = f"[Sent file: {saved_path.name}] saved to {saved_path} ({size_kb:.1f} KB)"
        if caption:
            if not _is_owner(uid) and arbos_x is not None:
                if arbos_x.strip():
                    user_text += f"\n[Caption]: {arbos_x}"
            else:
                user_text += f"\n[Caption]: {caption}"

        is_text = False
        try:
            content = saved_path.read_text(errors="strict")
            if len(content) <= 8000:
                user_text += f"\n[File contents]:\n{content}"
                is_text = True
        except (UnicodeDecodeError, ValueError):
            pass

        if not is_text:
            user_text += "\n(Binary file — not included inline. Read it from the saved path if needed.)"

        rid = cid if cid < 0 else None
        log_chat(
            "user", user_text[:1000], telegram_user_id=uid, telegram_shared_room_id=rid,
        )
        tw = cid if cid in workspace_group_ids else 0
        if _is_owner(uid):
            topic_g = _active_topic_goal_key(message, cid)
            prompt = _build_operator_prompt(
                _telegram_reply_prefix(message) + user_text,
                telegram_workspace_id=tw,
                active_topic_goal=topic_g,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )
        else:
            u = message.from_user
            who = f"@{u.username}" if u.username else (u.first_name or str(uid))
            prompt = _build_public_bittensor_prompt(
                user_text,
                who,
                message.chat.title,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )

        def _run():
            response = run_agent_streaming(
                bot, prompt, cid,
                message_thread_id=_forum_reply_thread(message),
                workspace_id=tw,
                telegram_log_user_id=uid,
                telegram_log_room_id=rid,
            )
            log_chat(
                "bot",
                response[:1000],
                telegram_user_id=uid,
                telegram_shared_room_id=rid,
            )
            _process_pending_env()

        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message):
        uid = message.from_user.id if message.from_user else None
        cid = message.chat.id
        cap0 = message.caption or ""
        arbos_x = _strip_arbos_leading_command(cap0)
        gated0 = _telegram_member_arbos_chat(cid)
        if _is_owner(uid):
            pass
        elif uid is not None and gated0 and arbos_x is not None:
            pass
        elif gated0:
            return
        else:
            _reject(message)
            return
        _save_chat_id(cid)

        photo = message.photo[-1]  # highest resolution
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{ts}.jpg"
        saved_path = _download_telegram_file(bot, photo.file_id, filename)

        caption = message.caption or ""
        user_text = f"[Sent photo: {saved_path.name}] saved to {saved_path}"
        if caption:
            if not _is_owner(uid) and arbos_x is not None:
                if arbos_x.strip():
                    user_text += f"\n[Caption]: {arbos_x}"
            else:
                user_text += f"\n[Caption]: {caption}"

        rid = cid if cid < 0 else None
        log_chat(
            "user", user_text[:1000], telegram_user_id=uid, telegram_shared_room_id=rid,
        )
        tw = cid if cid in workspace_group_ids else 0
        if _is_owner(uid):
            topic_g = _active_topic_goal_key(message, cid)
            prompt = _build_operator_prompt(
                _telegram_reply_prefix(message) + user_text,
                telegram_workspace_id=tw,
                active_topic_goal=topic_g,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )
        else:
            u = message.from_user
            who = f"@{u.username}" if u.username else (u.first_name or str(uid))
            prompt = _build_public_bittensor_prompt(
                user_text,
                who,
                message.chat.title,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )

        def _run():
            response = run_agent_streaming(
                bot, prompt, cid,
                message_thread_id=_forum_reply_thread(message),
                workspace_id=tw,
                telegram_log_user_id=uid,
                telegram_log_room_id=rid,
            )
            log_chat(
                "bot",
                response[:1000],
                telegram_user_id=uid,
                telegram_shared_room_id=rid,
            )
            _process_pending_env()

        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(func=lambda m: True)
    def handle_message(message):
        if message.content_type != "text" or not (message.text or "").strip():
            return
        uid = message.from_user.id if message.from_user else None
        cid = message.chat.id
        text = message.text.strip()

        if text.startswith("/"):
            if _telegram_member_arbos_chat(cid) and not _is_owner(uid):
                th0 = _forum_reply_thread(message)
                kw0: dict[str, Any] = {}
                if th0 is not None:
                    kw0["message_thread_id"] = th0
                bot.send_message(
                    cid,
                    "Les commandes `/…` sont pour les opérateurs. "
                    "Pour une question : `/arbos` puis votre texte.",
                    parse_mode="Markdown",
                    **kw0,
                )
                return
            if not _is_owner(uid):
                _reject(message)
                return
            bot.send_message(
                cid,
                "Unknown command. Owner: `/help` lists all commands.",
                parse_mode="Markdown",
            )
            return

        if _is_owner(uid):
            # In workspace groups, plain text without /arbos is ignored.
            if cid in workspace_group_ids:
                return
            _save_chat_id(cid)
            rid = cid if cid < 0 else None
            log_chat(
                "user", text, telegram_user_id=uid, telegram_shared_room_id=rid,
            )
            tw = 0
            topic_g = _active_topic_goal_key(message, cid)
            prompt = _build_operator_prompt(
                _telegram_reply_prefix(message) + text,
                telegram_workspace_id=tw,
                active_topic_goal=topic_g,
                telegram_user_id=uid,
                telegram_room_id=rid,
            )

            def _run_owner():
                response = run_agent_streaming(
                    bot, prompt, cid,
                    message_thread_id=_forum_reply_thread(message),
                    workspace_id=tw,
                    telegram_log_user_id=uid,
                    telegram_log_room_id=rid,
                )
                log_chat(
                    "bot",
                    response[:1000],
                    telegram_user_id=uid,
                    telegram_shared_room_id=rid,
                )
                _process_pending_env()

            threading.Thread(target=_run_owner, daemon=True).start()
            return

        if uid is not None and _telegram_member_arbos_chat(cid):
            return

        _reject(message)

    _log("telegram bot started")
    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            _log(f"bot polling error: {str(e)[:80]}, reconnecting in 5s")
            time.sleep(5)


# ── Main ─────────────────────────────────────────────────────────────────────

def _kill_child_procs():
    """Kill all tracked claude child processes."""
    with _child_procs_lock:
        procs = list(_child_procs)
    for proc in procs:
        try:
            if proc.poll() is None:
                _log(f"killing child claude pid={proc.pid}")
                proc.kill()
                proc.wait(timeout=5)
        except Exception:
            pass
    with _child_procs_lock:
        _child_procs.clear()


def _kill_stale_claude_procs():
    """Kill any leftover claude processes from a previous arbos instance."""
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["pgrep", "-x", "claude"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            pid = int(line.strip())
            if pid == my_pid:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                _log(f"killed stale claude orphan pid={pid}")
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
    except Exception:
        pass


def _kill_stale_codex_procs():
    """Kill any leftover codex processes from a previous arbos instance."""
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["pgrep", "-f", "codex exec"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            pid = int(line.strip())
            if pid == my_pid:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                _log(f"killed stale codex orphan pid={pid}")
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
    except Exception:
        pass


def _kill_stale_agent_procs():
    """Kill any leftover cursor agent processes from a previous arbos instance.

    Uses `pgrep -f 'agent --print'` instead of pgrep -x to avoid killing
    unrelated system processes named 'agent'.
    """
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["pgrep", "-f", "agent --print"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            pid = int(line.strip())
            if pid == my_pid:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                _log(f"killed stale agent orphan pid={pid}")
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
    except Exception:
        pass


def _send_cli(args: list[str]):
    """CLI entry point: queue a message for the runtime to send to Telegram."""
    import argparse
    parser = argparse.ArgumentParser(description="Send a Telegram message to the operator")
    parser.add_argument("message", nargs="?", help="Message text to send")
    parser.add_argument("--file", help="Send contents of a file instead")
    parsed = parser.parse_args(args)

    if not parsed.message and not parsed.file:
        parser.error("Provide a message or --file")

    if parsed.file:
        text = Path(parsed.file).read_text()
    else:
        text = parsed.message

    goal_index = int(os.environ.get("ARBOS_GOAL_INDEX", "0"))
    _queue_operator_text(text, goal_index=goal_index)
    print(f"Queued message for runtime delivery ({len(text)} chars)")


def _sendfile_cli(args: list[str]):
    """CLI entry point: python arbos.py sendfile path/to/file [--caption 'text'] [--photo]"""
    import argparse
    parser = argparse.ArgumentParser(description="Send a file to the operator via Telegram")
    parser.add_argument("path", help="Path to the file to send")
    parser.add_argument("--caption", default="", help="Caption for the file")
    parser.add_argument("--photo", action="store_true", help="Send as a compressed photo instead of a document")
    parsed = parser.parse_args(args)

    file_path = Path(parsed.path)
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    if parsed.photo:
        ok = _send_telegram_photo(str(file_path), caption=parsed.caption)
    else:
        ok = _send_telegram_document(str(file_path), caption=parsed.caption)

    if ok:
        print(f"Sent {'photo' if parsed.photo else 'file'}: {file_path.name}")
    else:
        print("Failed to send (check TAU_BOT_TOKEN and chat_id.txt)", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "send":
        _send_cli(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "sendfile":
        _sendfile_cli(sys.argv[2:])
        return

    if len(sys.argv) > 1 and sys.argv[1] == "encrypt":
        env_path = WORKING_DIR / ".env"
        if not env_path.exists():
            if ENV_ENC_FILE.exists():
                print(".env.enc already exists (already encrypted)")
            else:
                print(".env not found, nothing to encrypt")
            return
        load_dotenv(env_path)
        bot_token = os.environ.get("TAU_BOT_TOKEN", "")
        if not bot_token:
            print("TAU_BOT_TOKEN must be set in .env", file=sys.stderr)
            sys.exit(1)
        _encrypt_env_file(bot_token)
        print("Encrypted .env → .env.enc, deleted plaintext.")
        print(f"On future starts: TAU_BOT_TOKEN='{bot_token}' python arbos.py")
        return

    if len(sys.argv) > 1 and sys.argv[1] not in ("send", "encrypt", "sendfile"):
        print(f"Unknown subcommand: {sys.argv[1]}", file=sys.stderr)
        print("Usage: arbos.py [send|sendfile|encrypt]", file=sys.stderr)
        sys.exit(1)

    _log(f"arbos starting in {WORKING_DIR} (provider={PROVIDER}, model={CLAUDE_MODEL})")
    _kill_stale_claude_procs()
    if PROVIDER == "codex" or FALLBACK_PROVIDER == "codex":
        _kill_stale_codex_procs()
    if PROVIDER == "cursor" or FALLBACK_PROVIDER == "cursor":
        _kill_stale_agent_procs()
    _reload_env_secrets()
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    GOALS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

    _load_goals()
    _ensure_telegram_qa_fixed_goal()
    if not _goals_background_autorun_default():
        _stop_all_ralph_goal_autorun()
        _log(
            "Ralph goals idle until /start <n> "
            "(GOALS_BACKGROUND_AUTORUN default off when Telegram group IDs are set)",
        )
    _log(f"loaded {_total_registered_goals()} goal(s) (legacy + Telegram workspaces)")

    if FALLBACK_PROVIDER == "opencode":
        _log(f"fallback configured: opencode/{FALLBACK_MODEL}")
    elif FALLBACK_PROVIDER == "codex":
        _log(f"fallback configured: codex/{FALLBACK_MODEL}")
        _check_codex_login("fallback codex")
    elif FALLBACK_PROVIDER == "cursor":
        _log(f"fallback configured: cursor/{FALLBACK_MODEL}")
        _check_cursor_login()
    elif FALLBACK_PROVIDER == "openrouter" and not FALLBACK_API_KEY:
        _log("WARNING: OPENROUTER_API_KEY not set — fallback will not work")

    if PROVIDER == "codex":
        _check_codex_login("primary codex")
    elif PROVIDER == "cursor":
        _check_cursor_login()
    elif PROVIDER == "openrouter" and not LLM_API_KEY:
        _log("WARNING: OPENROUTER_API_KEY not set — OpenRouter calls will fail")
    elif PROVIDER == "opencode" and not LLM_API_KEY:
        _log("WARNING: OPENCODE_API_KEY not set — OpenCode calls may fail")
    elif PROVIDER == "chutes" and not LLM_API_KEY:
        _log("WARNING: CHUTES_API_KEY not set — LLM calls will fail")

    def _handle_shutdown_signal(signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        _log(f"{sig_name} received; shutting down gracefully")
        _shutdown.set()

    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    if PROVIDER == "chutes":
        _log(f"starting chutes proxy thread (port={PROXY_PORT}, agent={CHUTES_ROUTING_AGENT}, bot={CHUTES_ROUTING_BOT})")
        threading.Thread(target=_start_proxy, daemon=True).start()
        time.sleep(1)
    else:
        _log(f"{PROVIDER} direct mode — no proxy needed")

    _write_claude_settings()

    _ping = os.environ.get("TELEGRAM_RESTART_PING", "true").strip().lower()
    if _ping not in ("0", "false", "no") and os.getenv("TAU_BOT_TOKEN"):
        _send_telegram_text("Restarted.")

    threading.Thread(target=_goal_manager, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()

    while not _shutdown.is_set():
        if RESTART_FLAG.exists():
            RESTART_FLAG.unlink()
            _log("restart requested; killing children and exiting for pm2")
            _kill_child_procs()
            sys.exit(0)
        _process_pending_env()
        _shutdown.wait(timeout=1)

    _log("shutdown: killing children")
    _kill_child_procs()
    _log("shutdown complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
