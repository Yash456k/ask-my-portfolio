#!/usr/bin/env python3
"""Refresh the server-side portfolio activity cache from Codex, Claude Code and GitHub."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "var" / "activity" / "activity.json"
CODEX_PROFILE_URL = "https://chatgpt.com/backend-api/wham/profiles/me"


def find_codex_home() -> Path:
    candidates: list[Path] = []
    if configured := os.environ.get("CODEX_HOME"):
        configured_home = Path(configured).expanduser()
        if (configured_home / "auth.json").exists():
            return configured_home
        candidates.append(configured_home)
    candidates.append(Path.home() / ".codex")
    candidates.extend(Path("/mnt/c/Users").glob("*/.codex"))

    available = [candidate for candidate in candidates if (candidate / "auth.json").exists()]
    if available:
        return max(
            available,
            key=lambda candidate: (
                sum(1 for _ in (candidate / "sessions").rglob("*.jsonl"))
                if (candidate / "sessions").exists()
                else 0,
                (candidate / "auth.json").stat().st_mtime,
            ),
        )
    raise RuntimeError("Could not find a Codex home containing authentication")


def read_codex_credentials(codex_home: Path) -> tuple[str, str]:
    auth_path = codex_home / "auth.json"
    if not auth_path.exists():
        raise RuntimeError(f"Codex authentication was not found at {auth_path}")

    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Codex authentication could not be read") from error

    tokens = auth.get("tokens") or {}
    account_id = tokens.get("account_id")
    source = os.environ.get("ACTIVITY_CODEX_AUTH_SOURCE", "codex")
    if source == "codex":
        access_token = tokens.get("access_token")
    elif source == "hermes":
        # Hermes owns token rotation and locks its shared credential pool. Never
        # copy its refresh tokens into the independent Codex CLI auth file.
        try:
            status = import_module("hermes_cli.auth").get_codex_auth_status()
            access_token = status.get("api_key") if status.get("logged_in") else None
        except Exception:
            raise RuntimeError("Hermes Codex authentication could not be resolved") from None
        if not access_token:
            raise RuntimeError("Hermes has no current Codex login")
        try:
            payload = access_token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            managed_account = claims.get("https://api.openai.com/auth", {}).get(
                "chatgpt_account_id"
            )
        except (ValueError, IndexError, AttributeError):
            raise RuntimeError("Hermes Codex account could not be identified") from None
        # Anchor the public graph to the original account, even if Hermes later
        # selects a different account from its pool.
        if not account_id or managed_account != account_id:
            raise RuntimeError("Hermes Codex login does not match the portfolio account")
    else:
        raise RuntimeError("Unknown activity Codex authentication source")
    if not access_token or not account_id:
        raise RuntimeError("Codex authentication is missing an access token or account ID")
    return access_token, account_id


def read_codex_activity(codex_home: Path, start: date, end: date) -> dict[str, Any]:
    access_token, account_id = read_codex_credentials(codex_home)
    request = Request(  # noqa: S310 - URL is the HTTPS constant above.
        CODEX_PROFILE_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-ID": account_id,
            "OAI-Language": "en",
            "Originator": "Codex Desktop",
            "User-Agent": "Portfolio Activity Sync/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            profile = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Codex profile request failed with HTTP {error.code}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("Codex profile request failed") from error

    stats = profile.get("stats") or {}
    buckets = stats.get("daily_usage_buckets")
    if not isinstance(buckets, list):
        raise RuntimeError("Codex profile response did not include daily usage")

    days = sorted(
        (
            {"date": str(bucket.get("start_date", ""))[:10], "tokens": int(bucket.get("tokens", 0))}
            for bucket in buckets
            if start.isoformat() <= str(bucket.get("start_date", ""))[:10] <= end.isoformat()
            and int(bucket.get("tokens", 0)) > 0
        ),
        key=lambda item: item["date"],
    )
    peak = max(days, key=lambda item: item["tokens"], default=None)
    return {
        "total": sum(item["tokens"] for item in days),
        "lifetimeTotal": int(stats.get("lifetime_tokens", 0)),
        "peakDailyTokens": int(stats.get("peak_daily_tokens", 0)),
        "activeDays": len(days),
        "peak": {"date": peak["date"], "count": peak["tokens"]} if peak else None,
        "days": days,
    }


def read_claude_activity(start: date, end: date) -> dict[str, Any] | None:
    """Claude Code tokens per day from the claude-code-usage hive note, which the laptop's
    scripts/claude_usage_to_hive.py keeps. None when the note is missing or unreadable, so the
    rest of the snapshot still refreshes."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed arguments
            ["hivenote", "read", "claude-code-usage", "--json"],  # noqa: S607 - on the service PATH
            capture_output=True, text=True, timeout=30, check=True,
        )
        notes = json.loads(result.stdout).get("notes") or []
        saved = json.loads(notes[0]["content"]).get("days", {}) if notes else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, IndexError):
        return None
    if not saved:
        return None
    all_days = {str(day)[:10]: int(tokens) for day, tokens in saved.items() if int(tokens) > 0}
    days = [
        {"date": day, "tokens": tokens}
        for day, tokens in sorted(all_days.items())
        if start.isoformat() <= day <= end.isoformat()
    ]
    peak = max(days, key=lambda item: item["tokens"], default=None)
    return {
        "total": sum(item["tokens"] for item in days),
        "lifetimeTotal": sum(all_days.values()),
        "peakDailyTokens": max(all_days.values()),
        "activeDays": len(days),
        "since": min(all_days),
        "peak": {"date": peak["date"], "count": peak["tokens"]} if peak else None,
        "days": days,
    }


def run_gh_graphql(start: date, end: date) -> dict[str, Any]:
    query = """
    query($from: DateTime!, $to: DateTime!) {
      viewer {
        login
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    command = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"from={start.isoformat()}T00:00:00Z",
        "-F",
        f"to={end.isoformat()}T23:59:59Z",
    ]
    result = subprocess.run(  # noqa: S603 - executable and arguments are controlled here.
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["data"]["viewer"]


def read_github_activity(start: date, end: date) -> dict[str, Any]:
    viewer = run_gh_graphql(start, end)
    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": item["date"], "count": item["contributionCount"]}
        for week in calendar["weeks"]
        for item in week["contributionDays"]
        if start.isoformat() <= item["date"] <= end.isoformat()
        and item["contributionCount"] > 0
    ]
    peak = max(days, key=lambda item: item["count"], default=None)
    return {
        "username": viewer["login"],
        "total": sum(item["count"] for item in days),
        "activeDays": len(days),
        "peak": peak,
        "days": days,
    }


def write_snapshot(snapshot: dict[str, Any], output_path: Path) -> bool:
    rendered = json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n"
    previous = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    if previous == rendered:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    output_path.parent.chmod(0o755)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.chmod(0o644)
        os.replace(temporary_path, output_path)
        output_path.chmod(0o644)
        return True
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("ACTIVITY_CACHE_PATH", DEFAULT_OUTPUT_PATH)),
        help="public cache file written atomically (default: ACTIVITY_CACHE_PATH or var/activity)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    end = datetime.now().astimezone().date()
    start = end - timedelta(days=365)
    codex_home = find_codex_home()

    snapshot = {
        "generatedAt": (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        ),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "codex": read_codex_activity(codex_home, start, end),
        "github": read_github_activity(start, end),
    }
    claude = read_claude_activity(start, end)
    if claude is not None:
        snapshot["claude"] = claude
    output_path = args.output.expanduser()
    write_snapshot(snapshot, output_path)
    print(
        f"Refreshed {output_path}: "
        f"{snapshot['codex']['total']:,} Codex tokens, "
        f"{snapshot['github']['total']:,} GitHub contributions, "
        f"{claude['total'] if claude else 0:,} Claude Code tokens"
    )


if __name__ == "__main__":
    main()
