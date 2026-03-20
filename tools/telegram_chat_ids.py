#!/usr/bin/env python3
"""Print chat ids from Telegram getUpdates (for TELEGRAM_WORKSPACE_GROUP_IDS / TELEGRAM_PUBLIC_CHAT_IDS).

Requires TAU_BOT_TOKEN in .env (run from repo root: Arbos_Bittensor/).

If the queue is empty:
  1. Add the bot to the group.
  2. BotFather → /setprivacy → Disable (so the bot sees normal messages), OR
     in the group send a line that mentions the bot: @YourBotName hello
  3. Send /start to the bot in private, or post anything in the group, then re-run.

Usage:
  python tools/telegram_chat_ids.py              # one shot
  python tools/telegram_chat_ids.py --wait 60  # long-poll up to N seconds
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="List Telegram chat ids from getUpdates")
    parser.add_argument("--wait", type=int, default=0, help="Long-poll timeout per request (seconds)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = os.environ.get("TAU_BOT_TOKEN", "").strip()
    if not token:
        print("Set TAU_BOT_TOKEN in .env", file=sys.stderr)
        sys.exit(1)

    params: dict = {"limit": 100}
    if args.wait > 0:
        params["timeout"] = min(args.wait, 50)

    r = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params=params or None,
        timeout=max(15, args.wait + 5),
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        print(data, file=sys.stderr)
        sys.exit(1)

    updates = data.get("result", [])
    if not updates:
        print(
            "No pending updates. Do this, then run again:\n"
            "  • Add @Arbos_bittensor_bot (or your bot) to the group.\n"
            "  • BotFather → /setprivacy → Disable (recommended for Arbos groups).\n"
            "  • Or mention the bot in the group: @YourBotName test\n"
            "  • Or send /start in private chat with the bot.\n"
            f"  • Or: python tools/telegram_chat_ids.py --wait 60\n"
            "    and post in the group while it waits.\n",
            file=sys.stderr,
        )
        sys.exit(2)

    seen: dict[tuple[int, str, str], int] = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
        ctype = chat.get("type", "")
        key = (int(cid), str(ctype), str(title))
        seen[key] = seen.get(key, 0) + 1

    print("Chats (use negative ids for supergroups in .env):\n")
    for (cid, ctype, title), n in sorted(seen.items(), key=lambda x: x[0][0]):
        label = repr(title) if title else "(no title)"
        print(f"  TELEGRAM_…={cid}   # type={ctype} name={label}  (events={n})")
    print("\nExample:\n  TELEGRAM_WORKSPACE_GROUP_IDS=-1001234567890")


if __name__ == "__main__":
    main()
