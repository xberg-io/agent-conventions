#!/usr/bin/env python3
"""Generate a reproducible bytes/token calibration from native Anthropic token counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def estimate(samples: list[dict]) -> float:
    if not samples or any(sample["tokens"] <= 0 or sample["bytes"] <= 0 for sample in samples):
        raise ValueError("calibration needs nonempty samples with positive bytes and tokens")
    return sum(sample["bytes"] for sample in samples) / sum(sample["tokens"] for sample in samples)


def measure(path: Path, root: Path, model: str, key: str) -> dict:
    text = path.read_text()
    body = {"model": model, "messages": [{"role": "user", "content": text}]}
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages/count_tokens",
        data=json.dumps(body).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        tokens = json.load(response)["input_tokens"]
    return {
        "path": str(path.resolve().relative_to(root.resolve())),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "bytes": len(text.encode()),
        "tokens": tokens,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("samples", type=Path, nargs="+")
    args = parser.parse_args()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        parser.error("ANTHROPIC_API_KEY is not set")
    samples = [measure(path, args.root, args.model, key) for path in args.samples]
    result = {
        "calibration_version": "1",
        "harness_version": "2",
        "date": datetime.now(UTC).date().isoformat(),
        "model": args.model,
        "method": "Anthropic count_tokens endpoint; message-envelope overhead included conservatively",
        "bytes_per_token": estimate(samples),
        "samples": samples,
        "scope": "Instruction text; excludes CLI built-in prompts, runtime overhead and unmeasured MCP schemas",
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
