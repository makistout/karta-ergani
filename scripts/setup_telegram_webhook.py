"""Εγγραφή webhook Telegram Bot → https://erganios.gr/api/telegram/webhook"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from config import Config  # noqa: E402

DEFAULT_WEBHOOK_URL = "https://erganios.gr/api/telegram/webhook"


def main() -> int:
    token = (Config.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        print("ΣΦΑΛΜΑ: Λείπει TELEGRAM_BOT_TOKEN στο .env", file=sys.stderr)
        return 1

    webhook_url = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WEBHOOK_URL).strip()
    base = f"https://api.telegram.org/bot{token}"

    info = requests.get(f"{base}/getWebhookInfo", timeout=30).json()
    print("Τρέχον webhook:", info.get("result", {}))

    resp = requests.post(
        f"{base}/setWebhook",
        json={
            "url": webhook_url,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok or not data.get("ok"):
        print("ΣΦΑΛΜΑ setWebhook:", data, file=sys.stderr)
        return 1

    print("OK setWebhook →", webhook_url)
    info2 = requests.get(f"{base}/getWebhookInfo", timeout=30).json()
    result = info2.get("result") or {}
    print("Νέο webhook URL:", result.get("url"))
    print("Pending updates:", result.get("pending_update_count"))
    if result.get("last_error_message"):
        print("Τελευταίο σφάλμα:", result.get("last_error_message"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
