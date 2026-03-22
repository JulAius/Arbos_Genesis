#!/usr/bin/env python3
"""
Discord API client — read-only access to Discord guilds, channels and messages.

Base URL : https://discord.com/api/v10
Auth     : DISCORD_TOKEN (user token) → Authorization: <token>
           DISCORD_BOT_TOKEN (bot)    → Authorization: Bot <token>
Docs     : https://discord.com/developers/docs/reference

Default guild: 799672011265015819 (Bittensor Discord)

Rate limits: 50 req/s global. Per-route limits vary.
"""

import os
import json
import httpx
from typing import Any, Optional
from pathlib import Path
from datetime import datetime, timedelta

# ── env / auth ────────────────────────────────────────────────────────────────

def _load_env() -> None:
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent]:
        env_path = parent / ".env"
        if env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path, override=False)
            except ImportError:
                pass
            break

_load_env()

BASE_URL = os.getenv("DISCORD_BASE_URL", "https://discord.com/api/v10")
ALLOWED_GUILD = os.getenv("DISCORD_GUILD_ID", "799672011265015819")
DEFAULT_GUILD = ALLOWED_GUILD


def _get_auth() -> str:
    """Return the Authorization header value.
    Prefers DISCORD_TOKEN (user token) over DISCORD_BOT_TOKEN (bot token)."""
    _load_env()
    user_token = os.getenv("DISCORD_TOKEN")
    if user_token:
        return user_token
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if bot_token:
        return f"Bot {bot_token}"
    raise EnvironmentError("DISCORD_TOKEN (or DISCORD_BOT_TOKEN) not set")


def _headers() -> dict:
    return {
        "Authorization": _get_auth(),
        "Content-Type": "application/json",
    }


def _get(path: str, params: Optional[dict] = None, *, _retries: int = 3) -> Any:
    import time
    url = f"{BASE_URL}{path}"
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    last_exc: Exception | None = None
    for attempt in range(_retries):
        try:
            r = httpx.get(url, params=clean, headers=_headers(), timeout=30)
            if r.status_code == 403:
                raise httpx.HTTPStatusError(
                    f"403 Forbidden — bot may lack permissions for: {path}",
                    request=r.request, response=r,
                )
            if r.status_code == 404:
                raise httpx.HTTPStatusError(
                    f"404 Not Found: {path}",
                    request=r.request, response=r,
                )
            # Discord rate limit: Retry-After header
            if r.status_code == 429:
                retry_after = r.json().get("retry_after", 1.0)
                if attempt < _retries - 1:
                    time.sleep(retry_after)
                    last_exc = httpx.HTTPStatusError(
                        f"429 Rate Limited", request=r.request, response=r,
                    )
                    continue
            r.raise_for_status()
            return r.json()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_exc = exc
            if attempt < _retries - 1:
                time.sleep(1.5 * (attempt + 1))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (500, 502, 503, 504) and attempt < _retries - 1:
                last_exc = exc
                time.sleep(2.0 * (attempt + 1))
            else:
                raise
    raise last_exc  # type: ignore[misc]


# ── Guild guard ──────────────────────────────────────────────────────────────

def _enforce_guild(guild_id: str) -> None:
    """Raise if guild_id is not the allowed Bittensor guild."""
    if guild_id != ALLOWED_GUILD:
        raise PermissionError(f"Access restricted to Bittensor guild ({ALLOWED_GUILD}). Got: {guild_id}")


# ── Permission bits ──────────────────────────────────────────────────────────

PERM_BITS = {
    0x1: "CREATE_INSTANT_INVITE",
    0x2: "KICK_MEMBERS",
    0x4: "BAN_MEMBERS",
    0x8: "ADMINISTRATOR",
    0x10: "MANAGE_CHANNELS",
    0x20: "MANAGE_GUILD",
    0x400: "VIEW_CHANNEL",
    0x800: "SEND_MESSAGES",
    0x2000: "MANAGE_MESSAGES",
    0x4000: "EMBED_LINKS",
    0x8000: "ATTACH_FILES",
    0x10000: "READ_MESSAGE_HISTORY",
    0x20000: "MENTION_EVERYONE",
    0x10000000: "MANAGE_ROLES",
    0x20000000: "MANAGE_WEBHOOKS",
    0x800000000: "MODERATE_MEMBERS",
}


def _perm_flags(value: int) -> list[str]:
    """Decode a permission integer into a list of flag names."""
    return [name for bit, name in PERM_BITS.items() if value & bit]


# ── Guild ────────────────────────────────────────────────────────────────────

def get_guild(guild_id: str = DEFAULT_GUILD) -> dict:
    """Guild info (name, description, member count, etc.)."""
    _enforce_guild(guild_id)
    return _get(f"/guilds/{guild_id}", {"with_counts": "true"})


def get_guild_channels(guild_id: str = DEFAULT_GUILD) -> list:
    """List all channels in a guild. Returns channel objects with id, name, type, parent_id, topic."""
    _enforce_guild(guild_id)
    return _get(f"/guilds/{guild_id}/channels")


def get_guild_roles(guild_id: str = DEFAULT_GUILD) -> list:
    """List all roles in a guild."""
    _enforce_guild(guild_id)
    return _get(f"/guilds/{guild_id}/roles")


def get_guild_member(guild_id: str, user_id: str) -> dict:
    """Get a guild member by user ID."""
    _enforce_guild(guild_id)
    return _get(f"/guilds/{guild_id}/members/{user_id}")


def get_roles_summary(guild_id: str = DEFAULT_GUILD) -> list[dict]:
    """Return admin/mod/owner roles with decoded permissions."""
    roles = get_guild_roles(guild_id)
    guild = get_guild(guild_id)
    owner_id = guild.get("owner_id")
    result = []
    for r in sorted(roles, key=lambda x: x.get("position", 0), reverse=True):
        perms = int(r.get("permissions", "0"))
        is_admin = bool(perms & 0x8)
        is_mod = bool(perms & (0x2 | 0x4 | 0x2000 | 0x10000000 | 0x800000000))
        if is_admin or is_mod:
            result.append({
                "id": r["id"],
                "name": r["name"],
                "position": r.get("position"),
                "admin": is_admin,
                "mod": is_mod,
                "key_perms": _perm_flags(perms),
            })
    return {"owner_id": owner_id, "roles": result}


def get_channel_permissions(channel_id: str, guild_id: str = DEFAULT_GUILD) -> dict:
    """Get permission overwrites for a channel, resolved with role/user names."""
    _enforce_guild(guild_id)
    channel = get_channel(channel_id)
    roles = get_guild_roles(guild_id)
    role_map = {r["id"]: r["name"] for r in roles}
    overwrites = channel.get("permission_overwrites", [])
    result = []
    for ow in overwrites:
        oid = ow["id"]
        otype = "user" if ow["type"] == 1 else "role"
        name = role_map.get(oid, oid)
        if otype == "user":
            try:
                member = get_guild_member(guild_id, oid)
                name = member.get("user", {}).get("username", oid)
                nick = member.get("nick")
                if nick:
                    name = f"{name} ({nick})"
            except Exception:
                pass
        allow = int(ow.get("allow", "0"))
        deny = int(ow.get("deny", "0"))
        entry = {
            "type": otype,
            "name": name,
            "allow": _perm_flags(allow) if allow else [],
            "deny": _perm_flags(deny) if deny else [],
        }
        result.append(entry)
    return {
        "channel": channel.get("name"),
        "channel_id": channel_id,
        "overwrites": result,
    }


# ── Channels ─────────────────────────────────────────────────────────────────

# Channel types: 0=text, 2=voice, 4=category, 5=announcement, 10=thread,
#                11=public_thread, 12=private_thread, 13=stage, 15=forum, 16=media

def get_channel(channel_id: str) -> dict:
    """Get a single channel by ID."""
    return _get(f"/channels/{channel_id}")


def get_channel_messages(channel_id: str, limit: int = 50,
                         before: str | None = None,
                         after: str | None = None,
                         around: str | None = None) -> list:
    """Get messages from a channel. Max 100 per call.
    Use before/after/around with a message ID for pagination."""
    return _get(f"/channels/{channel_id}/messages", {
        "limit": min(limit, 100),
        "before": before,
        "after": after,
        "around": around,
    })


def get_pinned_messages(channel_id: str) -> list:
    """Get pinned messages in a channel."""
    return _get(f"/channels/{channel_id}/pins")


# ── Threads ──────────────────────────────────────────────────────────────────

def get_active_threads(guild_id: str = DEFAULT_GUILD) -> dict:
    """List all active threads in a guild. Returns {threads: [...], members: [...]}."""
    _enforce_guild(guild_id)
    return _get(f"/guilds/{guild_id}/threads/active")


def get_thread_messages(thread_id: str, limit: int = 50,
                        before: str | None = None,
                        after: str | None = None) -> list:
    """Get messages from a thread (same endpoint as channel messages)."""
    return get_channel_messages(thread_id, limit, before, after)


# ── Forum channels ───────────────────────────────────────────────────────────

def get_forum_threads(channel_id: str, limit: int = 25) -> dict:
    """List archived threads in a forum channel.
    Returns {threads: [...], members: [...], has_more: bool}."""
    return _get(f"/channels/{channel_id}/threads/archived/public", {"limit": min(limit, 100)})


# ── Search (via messages endpoint + filtering) ───────────────────────────────

def search_guild_messages(guild_id: str = DEFAULT_GUILD,
                          content: str | None = None,
                          author_id: str | None = None,
                          channel_id: str | None = None,
                          has: str | None = None,
                          min_id: str | None = None,
                          max_id: str | None = None,
                          limit: int = 25) -> dict:
    """Search messages in a guild.
    has: link, embed, file, video, image, sound, sticker.
    Returns {messages: [[msg, ...], ...], total_results: int}."""
    _enforce_guild(guild_id)
    return _get(f"/guilds/{guild_id}/messages/search", {
        "content": content,
        "author_id": author_id,
        "channel_id": channel_id,
        "has": has,
        "min_id": min_id,
        "max_id": max_id,
        "limit": min(limit, 25),
    })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_message(msg: dict, verbose: bool = False) -> dict:
    """Extract key fields from a Discord message for compact display."""
    author = msg.get("author", {})
    result = {
        "id": msg["id"],
        "author": author.get("username", "?"),
        "content": msg.get("content", ""),
        "timestamp": msg.get("timestamp", ""),
    }
    if msg.get("attachments"):
        result["attachments"] = len(msg["attachments"])
    if msg.get("embeds"):
        result["embeds"] = len(msg["embeds"])
    if msg.get("referenced_message"):
        ref = msg["referenced_message"]
        result["reply_to"] = {
            "author": ref.get("author", {}).get("username", "?"),
            "content": ref.get("content", "")[:200],
        }
    if verbose:
        result["author_id"] = author.get("id")
        result["channel_id"] = msg.get("channel_id")
        if msg.get("thread"):
            result["thread"] = {"id": msg["thread"]["id"], "name": msg["thread"].get("name")}
    return result


def _format_channel(ch: dict) -> dict:
    """Extract key fields from a channel object."""
    TYPE_NAMES = {
        0: "text", 2: "voice", 4: "category", 5: "announcement",
        10: "announcement_thread", 11: "public_thread", 12: "private_thread",
        13: "stage", 15: "forum", 16: "media",
    }
    return {
        "id": ch["id"],
        "name": ch.get("name", "?"),
        "type": TYPE_NAMES.get(ch.get("type"), str(ch.get("type"))),
        "topic": ch.get("topic"),
        "parent_id": ch.get("parent_id"),
    }


def list_text_channels(guild_id: str = DEFAULT_GUILD) -> list:
    """List only text/announcement/forum channels (skip voice/category)."""
    channels = get_guild_channels(guild_id)
    text_types = {0, 5, 15}  # text, announcement, forum
    return [_format_channel(ch) for ch in channels if ch.get("type") in text_types]


def read_recent(channel_id: str, limit: int = 20, verbose: bool = False) -> list:
    """Read recent messages from a channel, formatted for compact display."""
    msgs = get_channel_messages(channel_id, limit=limit)
    return [_format_message(m, verbose=verbose) for m in reversed(msgs)]


def snowflake_from_timestamp(ts: datetime) -> str:
    """Convert a datetime to a Discord snowflake ID for use as before/after cursor."""
    discord_epoch = 1420070400000  # 2015-01-01T00:00:00Z in ms
    ms = int(ts.timestamp() * 1000) - discord_epoch
    return str(ms << 22)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    import argparse

    P = argparse.ArgumentParser(
        prog="discord",
        description="Discord API CLI — read-only access to Bittensor Discord (guild 799672011265015819)",
    )
    P.add_argument("--raw", action="store_true", help="Output raw API response (no formatting)")

    S = P.add_subparsers(dest="cmd")

    # ── Guild info
    S.add_parser("guild-info", help="Guild name, description, member count")

    # ── Channels
    S.add_parser("channels", help="List all text/announcement/forum channels")
    S.add_parser("channels-all", help="List ALL channels (including voice, categories)")

    # ── Messages
    p = S.add_parser("messages", help="Read messages from a channel")
    p.add_argument("channel_id", help="Channel or thread ID")
    p.add_argument("--limit", type=int, default=20, help="Number of messages (max 100)")
    p.add_argument("--before", help="Get messages before this message ID")
    p.add_argument("--after", help="Get messages after this message ID")
    p.add_argument("--verbose", "-v", action="store_true", help="Include author_id, channel_id")

    # ── Pinned
    p = S.add_parser("pinned", help="Get pinned messages from a channel")
    p.add_argument("channel_id", help="Channel or thread ID")

    # ── Threads
    S.add_parser("threads", help="List active threads in the guild")

    p = S.add_parser("forum-threads", help="List archived threads in a forum channel")
    p.add_argument("channel_id", help="Forum channel ID")
    p.add_argument("--limit", type=int, default=25, help="Number of threads (max 100)")

    # ── Search
    p = S.add_parser("search", help="Search messages in the guild")
    p.add_argument("query", nargs="?", help="Search text")
    p.add_argument("--channel", help="Filter by channel ID")
    p.add_argument("--author", help="Filter by author ID")
    p.add_argument("--has", choices=["link", "embed", "file", "video", "image", "sound", "sticker"],
                   help="Filter by attachment type")
    p.add_argument("--limit", type=int, default=25, help="Number of results (max 25)")
    p.add_argument("--hours", type=int, help="Only messages from last N hours")

    # ── Channel info
    p = S.add_parser("channel-info", help="Get info about a specific channel")
    p.add_argument("channel_id", help="Channel ID")

    # ── Roles & Permissions
    S.add_parser("roles", help="List admin/mod/owner roles in the guild")

    p = S.add_parser("permissions", help="Show permission overwrites for a channel")
    p.add_argument("channel_id", help="Channel ID")

    p = S.add_parser("member", help="Get info about a guild member")
    p.add_argument("user_id", help="User ID")

    args = P.parse_args()
    a = vars(args)

    try:
        cmd = a.pop("cmd")
        if not cmd:
            P.print_help()
            return

        guild = ALLOWED_GUILD
        raw = a.pop("raw")

        def _out(data):
            print(json.dumps(data, indent=2, ensure_ascii=False))

        if cmd == "guild-info":
            data = get_guild(guild)
            if not raw:
                data = {
                    "id": data["id"],
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "member_count": data.get("approximate_member_count"),
                    "online": data.get("approximate_presence_count"),
                }
            _out(data)

        elif cmd == "channels":
            _out(list_text_channels(guild))

        elif cmd == "channels-all":
            data = get_guild_channels(guild)
            if not raw:
                data = [_format_channel(ch) for ch in data]
            _out(data)

        elif cmd == "messages":
            cid = a["channel_id"]
            limit = a["limit"]
            before = a.get("before")
            after = a.get("after")
            verbose = a.get("verbose", False)
            if raw:
                _out(get_channel_messages(cid, limit, before, after))
            else:
                _out(read_recent(cid, limit, verbose))

        elif cmd == "pinned":
            data = get_pinned_messages(a["channel_id"])
            if not raw:
                data = [_format_message(m) for m in data]
            _out(data)

        elif cmd == "threads":
            data = get_active_threads(guild)
            if not raw:
                threads = data.get("threads", [])
                data = [{
                    "id": t["id"],
                    "name": t.get("name"),
                    "parent_id": t.get("parent_id"),
                    "message_count": t.get("message_count"),
                    "member_count": t.get("member_count"),
                } for t in threads]
            _out(data)

        elif cmd == "forum-threads":
            data = get_forum_threads(a["channel_id"], a.get("limit", 25))
            if not raw:
                threads = data.get("threads", [])
                data = {
                    "threads": [{
                        "id": t["id"],
                        "name": t.get("name"),
                        "message_count": t.get("message_count"),
                        "archive_timestamp": t.get("thread_metadata", {}).get("archive_timestamp"),
                    } for t in threads],
                    "has_more": data.get("has_more", False),
                }
            _out(data)

        elif cmd == "search":
            min_id = None
            if a.get("hours"):
                cutoff = datetime.now(tz=__import__('datetime').timezone.utc) - timedelta(hours=a["hours"])
                min_id = snowflake_from_timestamp(cutoff)
            data = search_guild_messages(
                guild,
                content=a.get("query"),
                author_id=a.get("author"),
                channel_id=a.get("channel"),
                has=a.get("has"),
                min_id=min_id,
                limit=a.get("limit", 25),
            )
            if not raw:
                results = data.get("messages", [])
                data = {
                    "total_results": data.get("total_results", 0),
                    "messages": [_format_message(m[0]) for m in results if m],
                }
            _out(data)

        elif cmd == "channel-info":
            data = get_channel(a["channel_id"])
            if not raw:
                data = _format_channel(data)
            _out(data)

        elif cmd == "roles":
            data = get_roles_summary(guild)
            if not raw:
                # Resolve guild owner username
                try:
                    owner = get_guild_member(guild, data["owner_id"])
                    data["owner"] = owner.get("user", {}).get("username", data["owner_id"])
                    data["owner_nick"] = owner.get("nick")
                except Exception:
                    data["owner"] = data["owner_id"]
            _out(data)

        elif cmd == "permissions":
            _out(get_channel_permissions(a["channel_id"], guild))

        elif cmd == "member":
            member = get_guild_member(guild, a["user_id"])
            roles_raw = get_guild_roles(guild)
            role_map = {r["id"]: r["name"] for r in roles_raw}
            if not raw:
                member_roles = [role_map.get(rid, rid) for rid in member.get("roles", [])]
                data = {
                    "username": member.get("user", {}).get("username"),
                    "global_name": member.get("user", {}).get("global_name"),
                    "nick": member.get("nick"),
                    "roles": member_roles,
                    "joined_at": member.get("joined_at"),
                }
            else:
                data = member
            _out(data)

        else:
            P.error(f"Unknown command: {cmd}")

    except httpx.HTTPStatusError as e:
        print(json.dumps({"error": str(e), "status_code": e.response.status_code}))
        raise SystemExit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        raise SystemExit(1)


if __name__ == "__main__":
    _cli()
