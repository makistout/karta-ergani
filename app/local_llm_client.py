"""Τοπικό LLM (Ollama) ως εφεδρικό όταν το Gemini αποτυγχάνει."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from config import Config

logger = logging.getLogger(__name__)


def local_llm_enabled() -> bool:
    return bool(Config.LOCAL_LLM_ENABLED and (Config.LOCAL_LLM_BASE_URL or "").strip())


def local_llm_available() -> bool:
    """Γρήγορος έλεγχος αν το Ollama απαντά (χωρίς να φορτώσει μοντέλο)."""
    if not local_llm_enabled():
        return False
    base = Config.LOCAL_LLM_BASE_URL.rstrip("/")
    try:
        r = requests.get(f"{base}/api/tags", timeout=(0.5, 1.5))
        return bool(r.ok)
    except requests.RequestException:
        return False


def generate_json(
    *,
    prompt_obj: dict[str, Any],
    schema: dict[str, Any],
    timeout_sec: float = 25.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Κλήση Ollama /api/chat με JSON format.
    Επιστρέφει (parsed_dict, metadata).
    """
    if not local_llm_enabled():
        raise RuntimeError("Τοπικό LLM απενεργοποιημένο")
    model = (Config.LOCAL_LLM_MODEL or "").strip()
    if not model:
        raise RuntimeError("Λείπει LOCAL_LLM_MODEL")
    base = Config.LOCAL_LLM_BASE_URL.rstrip("/")
    body = {
        "model": model,
        "stream": False,
        "format": schema,
        "options": {
            "temperature": 0,
            "num_predict": 512,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Είσαι parser εντολών erganiOS. Απάντησε ΜΟΝΟ με έγκυρο JSON "
                    "σύμφωνα με το schema. Μην επινοείς ΑΦΜ ή καταστήματα εκτός allowed_* / today_home."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_obj, ensure_ascii=False),
            },
        ],
    }
    connect = min(2.0, max(0.5, timeout_sec / 10))
    read = max(5.0, timeout_sec - connect)
    started = __import__("time").monotonic()
    response = requests.post(
        f"{base}/api/chat",
        json=body,
        timeout=(connect, read),
    )
    duration_ms = max(0, round((__import__("time").monotonic() - started) * 1000))
    if not response.ok:
        raise RuntimeError(f"Local LLM HTTP {response.status_code}: {response.text[:400]}")
    data = response.json()
    message = data.get("message") or {}
    text = str(message.get("content") or "").strip()
    if text.startswith("```"):
        import re

        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Το τοπικό LLM δεν επέστρεψε JSON object")
    meta = {
        "model": f"local:{model}"[:128],
        "duration_ms": duration_ms,
        "provider": "ollama",
        "usage_metadata": {
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
        },
    }
    logger.info(
        "local_llm.ok model=%s duration_ms=%s",
        model,
        duration_ms,
    )
    return parsed, meta
