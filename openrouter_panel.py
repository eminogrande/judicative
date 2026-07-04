#!/usr/bin/env python3
"""Run a blind Judicative panel packet through an OpenRouter judge team.

Usage:
  OPENROUTER_API_KEY=... python3 openrouter_panel.py \
    --packet panel_run/packet.md \
    --out panel_run/openrouter_judges \
    --models anthropic/claude-sonnet-4 openai/gpt-4.1 google/gemini-2.5-pro

Then aggregate with:
  python3 panel.py aggregate --dir panel_run --mapping panel_run/mapping.SEALED.json \
    --judges panel_run/openrouter_judges/*.json --rubric rubric_v2.json \
    --report PANEL_REPORT_OPENROUTER.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_SYSTEM = (
    "You are a strict senior code reviewer on a blind panel. "
    "Return only valid JSON matching the requested schema."
)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "judge"


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start:end + 1])
        raise


def submission_labels(packet_text: str) -> list[str]:
    return sorted(set(re.findall(r"^###\s+(SUBMISSION-[A-Z]+)\s*$", packet_text, re.MULTILINE)))


def validate_panel_response(data: dict[str, Any], labels: list[str]) -> None:
    if not isinstance(data.get("reviews"), dict):
        raise ValueError("response missing reviews object")
    missing = [label for label in labels if label not in data["reviews"]]
    if missing:
        raise ValueError(f"response missing reviews for: {', '.join(missing)}")
    ranking = data.get("ranking")
    if not isinstance(ranking, list):
        raise ValueError("response missing ranking list")
    if set(ranking) != set(labels):
        raise ValueError("ranking must contain exactly the submission labels")


def call_openrouter(
    *,
    model: str,
    packet_text: str,
    api_key: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
) -> str:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM},
            {"role": "user", "content": packet_text},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/eminogrande/judicative",
        "X-Title": "Judicative OpenRouter Panel",
    }
    req = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Judicative blind panel packet through OpenRouter models.")
    parser.add_argument("--packet", required=True, help="Path to panel.py prepare packet.md")
    parser.add_argument("--out", required=True, help="Directory for per-model judge JSON files")
    parser.add_argument("--models", nargs="+", required=True, help="OpenRouter model IDs")
    parser.add_argument("--base-url", default=os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to wait between model calls")
    parser.add_argument("--allow-invalid", action="store_true", help="Write JSON even if labels/ranking validation fails")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is required", file=sys.stderr)
        return 2

    packet_path = Path(args.packet)
    packet_text = packet_path.read_text(encoding="utf-8")
    labels = submission_labels(packet_text)
    if not labels:
        print(f"No SUBMISSION-* labels found in {packet_path}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for i, model in enumerate(args.models):
        judge_id = safe_name(model)
        print(f"judging with {model}...", file=sys.stderr)
        raw_path = out / f"{judge_id}.raw.txt"
        json_path = out / f"{judge_id}.json"
        try:
            raw = call_openrouter(
                model=model,
                packet_text=packet_text,
                api_key=api_key,
                base_url=args.base_url,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            raw_path.write_text(raw, encoding="utf-8")
            data = extract_json_object(raw)
            data.setdefault("judge_id", model)
            if not args.allow_invalid:
                validate_panel_response(data, labels)
            json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"wrote {json_path}", file=sys.stderr)
        except Exception as exc:
            print(f"FAILED {model}: {exc}", file=sys.stderr)
            return 1
        if i < len(args.models) - 1 and args.sleep:
            time.sleep(args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
