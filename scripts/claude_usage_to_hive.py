#!/usr/bin/env python3
"""Count Claude Code tokens per day from this machine's session logs and save them to HiveNote.

The portfolio's nightly activity sync reads the note on the server. Only daily totals leave this
machine, never prompts or code. Claude Code deletes old sessions, so the note keeps the higher of
the saved and the counted total for every day: history never shrinks. Run it whenever the
machine is awake; every run recounts every day still on disk.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

NOTE = "claude-code-usage"
DESCRIPTION = (
    "Daily Claude Code token totals from Yash's laptop; read by the portfolio activity sync"
)
LOG_ROOTS = [
    Path.home() / ".claude" / "projects",
    *map(Path, glob.glob("/mnt/c/Users/*/.claude/projects")),
]
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def count_days() -> Counter[str]:
    """Tokens per local calendar day. A message is logged once per content block, and resumed
    sessions repeat earlier messages, so each message counts once by its id and request id."""
    seen: set[tuple[str, str]] = set()
    days: Counter[str] = Counter()
    for root in LOG_ROOTS:
        for path in root.glob("**/*.jsonl"):
            try:
                lines = path.open(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            with lines:
                for line in lines:
                    if '"usage"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = entry.get("message") or {}
                    usage = message.get("usage") or {}
                    stamp = entry.get("timestamp")
                    if not usage or not stamp:
                        continue
                    key = (str(message.get("id")), str(entry.get("requestId")))
                    if key in seen:
                        continue
                    seen.add(key)
                    day = (
                        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                        .astimezone()
                        .date()
                        .isoformat()
                    )
                    days[day] += sum(int(usage.get(field) or 0) for field in TOKEN_FIELDS)
    return days


def hivenote(*args: str, text: str | None = None) -> subprocess.CompletedProcess[str]:
    binary = shutil.which("hivenote") or next(
        iter(sorted(glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/hivenote")))), None
    )
    if binary is None:
        sys.exit("hivenote is not installed on this machine")
    env = {**os.environ, "PATH": f"{Path(binary).parent}{os.pathsep}{os.environ.get('PATH', '')}"}
    return subprocess.run(  # noqa: S603 - our own hivenote binary, fixed commands
        [binary, *args, "--json"], input=text, capture_output=True, text=True, env=env, timeout=60
    )


def saved_days() -> dict[str, int] | None:
    """The note's days, or None when the note does not exist yet."""
    result = hivenote("read", NOTE)
    if result.returncode != 0:
        sys.exit(f"Could not read the {NOTE} note: {result.stderr.strip()[:300]}")
    notes = json.loads(result.stdout).get("notes") or []
    if not notes:
        return None
    return {
        day: int(tokens)
        for day, tokens in json.loads(notes[0].get("content") or "{}").get("days", {}).items()
    }


def main() -> None:
    counted = count_days()
    saved = saved_days()
    merged = dict(saved or {})
    for day, tokens in counted.items():
        merged[day] = max(merged.get(day, 0), tokens)
    if saved == merged:
        print(f"{NOTE}: unchanged ({len(merged)} days)")
        return
    text = json.dumps(
        {
            "source": "Claude Code session logs: input, output and cache tokens per local day",
            "updated": datetime.now(timezone.utc)  # noqa: UP017 - runs on Python 3.9 too
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "days": dict(sorted(merged.items())),
        },
        indent=1,
    )
    result = (
        hivenote("add", NOTE, DESCRIPTION, "-", text=text)
        if saved is None
        else hivenote("replace", NOTE, "-", text=text)
    )
    if result.returncode != 0:
        sys.exit(f"Could not save the {NOTE} note: {result.stderr.strip()[:300]}")
    print(f"{NOTE}: saved {len(merged)} days, {sum(merged.values()):,} tokens")


if __name__ == "__main__":
    main()
