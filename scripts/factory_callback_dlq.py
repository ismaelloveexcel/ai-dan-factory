#!/usr/bin/env python3
"""
Dead Letter Queue (DLQ) processor for factory callbacks.

Loads failed callback payloads from a JSON file, retries each entry with
exponential backoff, removes successful ones, and sends a Telegram alert
for exhausted entries.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

DLQ_FILE = os.environ.get("FACTORY_CALLBACK_DLQ_FILE", "/tmp/factory_callback_dlq.json")
MAX_RETRIES = 3
INITIAL_DELAY_SECONDS = 2
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _send_telegram_alert(message: str) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[dlq] Telegram alert sent (status={resp.status})", flush=True)
    except Exception as exc:
        print(f"[dlq] Telegram alert failed: {exc}", file=sys.stderr, flush=True)


def _try_post(entry: dict) -> bool:
    callback_url = entry.get("callback_url", "")
    payload = entry.get("payload", {})
    if not callback_url:
        print("[dlq] Entry missing callback_url, skipping.", file=sys.stderr, flush=True)
        return False

    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    factory_secret = os.environ.get("FACTORY_SECRET", "").strip()
    api_key = os.environ.get("FACTORY_API_KEY", "").strip()

    req = urllib.request.Request(url=callback_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "ai-dan-factory/1.0 (dlq-retry)")
    if factory_secret:
        req.add_header("X-Factory-Secret", factory_secret)
    if api_key:
        req.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[dlq] Retry succeeded for {callback_url} (status={resp.status})", flush=True)
            return True
    except urllib.error.HTTPError as exc:
        print(f"[dlq] HTTP {exc.code} retrying {callback_url}", file=sys.stderr, flush=True)
        return exc.code not in _RETRYABLE_STATUS_CODES
    except urllib.error.URLError as exc:
        print(f"[dlq] Network error retrying {callback_url}: {exc}", file=sys.stderr, flush=True)
        return False


def process_dlq() -> int:
    if not os.path.exists(DLQ_FILE):
        print(f"[dlq] No DLQ file at {DLQ_FILE} \u2014 nothing to retry.", flush=True)
        return 0

    try:
        with open(DLQ_FILE, "r", encoding="utf-8") as f:
            queue: list = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[dlq] Failed to read DLQ file: {exc}", file=sys.stderr, flush=True)
        return 1

    if not isinstance(queue, list):
        print("[dlq] DLQ file is not a JSON array \u2014 resetting.", file=sys.stderr, flush=True)
        queue = []

    remaining: list = []
    final_failures = 0

    for entry in queue:
        retries = entry.get("retries", 0)
        project_id = entry.get("payload", {}).get("project_id", "unknown")

        success = False
        for attempt in range(MAX_RETRIES - retries):
            if _try_post(entry):
                success = True
                break
            delay = INITIAL_DELAY_SECONDS * (2 ** attempt)
            print(f"[dlq] Sleeping {delay}s before next attempt for {project_id}", flush=True)
            time.sleep(delay)

        if success:
            print(f"[dlq] Entry for {project_id} delivered successfully.", flush=True)
        else:
            entry["retries"] = retries + (MAX_RETRIES - retries)
            if entry["retries"] >= MAX_RETRIES:
                print(
                    json.dumps({
                        "event": "FINAL_FAILURE",
                        "error_code": "CALLBACK_TIMEOUT",
                        "project_id": project_id,
                        "callback_url": entry.get("callback_url", ""),
                    }),
                    flush=True,
                )
                _send_telegram_alert(
                    f"\U0001f6a8 *Factory DLQ FINAL_FAILURE*\nProject: `{project_id}`\nCallback exhausted after {MAX_RETRIES} retries."
                )
                final_failures += 1
            else:
                remaining.append(entry)

    try:
        with open(DLQ_FILE, "w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2, ensure_ascii=True)
        print(f"[dlq] Queue saved: {len(remaining)} entry/entries remaining.", flush=True)
    except OSError as exc:
        print(f"[dlq] Failed to save DLQ file: {exc}", file=sys.stderr, flush=True)
        return 1

    return 1 if final_failures > 0 else 0


if __name__ == "__main__":
    raise SystemExit(process_dlq())
