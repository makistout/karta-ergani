"""OpenAI Responses API — εφεδρικός parser όταν αποτυγχάνει το Gemini."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import requests

from config import Config

logger = logging.getLogger(__name__)


def _openai_credentials() -> tuple[str, str]:
    key = (getattr(Config, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (
        getattr(Config, "OPENAI_MODEL", None) or os.environ.get("OPENAI_MODEL") or "gpt-5.5"
    ).strip()
    if key and model:
        return key, model
    # IIS / stale worker: ξαναφόρτωσε .env αν λείπει το key.
    try:
        from pathlib import Path

        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env", override=True)
    except Exception:
        pass
    key = (os.environ.get("OPENAI_API_KEY") or getattr(Config, "OPENAI_API_KEY", None) or "").strip()
    model = (os.environ.get("OPENAI_MODEL") or getattr(Config, "OPENAI_MODEL", None) or "gpt-5.5").strip()
    return key, model


def openai_enabled() -> bool:
    key, model = _openai_credentials()
    return bool(key and model)


def _extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"} and part.get("text"):
                    chunks.append(str(part["text"]))
        elif item.get("type") == "output_text" and item.get("text"):
            chunks.append(str(item["text"]))
    text = "".join(chunks).strip()
    if text:
        return text
    raise ValueError("Το OpenAI δεν επέστρεψε κείμενο εξόδου")


def generate_json(
    *,
    prompt_obj: dict[str, Any],
    timeout_sec: float = 20.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not openai_enabled():
        raise RuntimeError("Το OpenAI δεν είναι ρυθμισμένο")
    key, model = _openai_credentials()
    body: dict[str, Any] = {
        "model": model,
        "store": bool(Config.OPENAI_STORE),
        "input": (
            "Είσαι parser εντολών erganiOS. Απάντησε ΜΟΝΟ με έγκυρο JSON object "
            "(όχι markdown). Το αίτημα:\n"
            + json.dumps(prompt_obj, ensure_ascii=False)
        ),
        "text": {"format": {"type": "json_object"}},
        # Parser: χαμηλό reasoning για χαμηλή καθυστέρηση.
        "reasoning": {"effort": "low"},
    }
    connect = min(2.0, max(0.5, timeout_sec / 10))
    read = max(5.0, timeout_sec - connect)
    started = time.monotonic()
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=(connect, read),
    )
    duration_ms = max(0, round((time.monotonic() - started) * 1000))
    if not response.ok:
        raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:400]}")
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("OpenAI: μη αναμενόμενη απόκριση")
    text = _extract_output_text(data)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI: η έξοδος δεν είναι JSON object")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    metadata = {
        "model": str(data.get("model") or model)[:128],
        "duration_ms": duration_ms,
        "provider": "openai",
        "usage_metadata": usage,
    }
    logger.info("openai.ok model=%s duration_ms=%s", metadata["model"], duration_ms)
    return parsed, metadata
