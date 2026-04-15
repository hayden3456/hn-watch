from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

import requests

from hn_watch import __version__


API_BASE = "https://hacker-news.firebaseio.com/v0"


@dataclass
class ItemSnapshot:
    url: str
    item_id: int
    title: str
    comment_count: int
    score_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hn-watch",
        description="Watch a Hacker News item URL and notify when comments or points increase.",
    )
    parser.add_argument("--url", help="Hacker News item URL to watch.")
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval for the HN updates feed in seconds. Default: 30",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds. Default: 15",
    )
    parser.add_argument(
        "--user-agent",
        default=f"HN-Watch/{__version__}",
        help="User-Agent header to send.",
    )
    parser.add_argument(
        "--show-unchanged",
        action="store_true",
        help="Print a line for checks where no change is detected.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def prompt_for_url() -> str:
    try:
        value = input("URL to watch: ").strip()
    except EOFError as exc:
        raise SystemExit("No URL provided.") from exc

    if not value:
        raise SystemExit("No URL provided.")
    return value


def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def parse_hn_item(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.netloc.lower() != "news.ycombinator.com" or parsed.path != "/item" or "id" not in query:
        raise SystemExit("HN-Watch only supports Hacker News item URLs like https://news.ycombinator.com/item?id=12345")

    try:
        item_id = int(query["id"][0])
    except (ValueError, IndexError) as exc:
        raise SystemExit("The Hacker News item URL is missing a valid numeric id.") from exc

    canonical_url = f"https://news.ycombinator.com/item?id={item_id}"
    return canonical_url, item_id


def build_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
    )
    return session


def fetch_json(session: requests.Session, url: str, timeout: int) -> Any:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_item_snapshot(session: requests.Session, item_id: int, timeout: int) -> ItemSnapshot:
    payload = fetch_json(session, f"{API_BASE}/item/{item_id}.json", timeout)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected item payload for item {item_id}")

    title = payload.get("title") or f"HN item {item_id}"
    comment_count = int(payload.get("descendants") or 0)
    score_count = int(payload.get("score") or 0)

    return ItemSnapshot(
        url=f"https://news.ycombinator.com/item?id={item_id}",
        item_id=item_id,
        title=title,
        comment_count=comment_count,
        score_count=score_count,
    )


def fetch_changed_items(session: requests.Session, timeout: int) -> set[int]:
    payload = fetch_json(session, f"{API_BASE}/updates.json", timeout)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {int(item_id) for item_id in items}


def describe_changes(old: ItemSnapshot, new: ItemSnapshot) -> list[str]:
    changes: list[str] = []

    comment_delta = delta_string("Comments", old.comment_count, new.comment_count)
    if comment_delta:
        changes.append(comment_delta)

    score_delta = delta_string("Points", old.score_count, new.score_count)
    if score_delta:
        changes.append(score_delta)

    return changes


def delta_string(label: str, old: int, new: int) -> str | None:
    if new <= old:
        return None
    return f"{label}: {old} -> {new} (+{new - old})"


def notify(title: str, message: str) -> None:
    print(f"[ALERT] {title}: {message}")

    system = platform.system().lower()
    if system == "linux":
        notify_linux(title, message)
        return
    if system == "darwin":
        notify_macos(title, message)
        return
    if system == "windows":
        notify_windows(title, message)


def notify_linux(title: str, message: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", title, message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def notify_macos(title: str, message: str) -> None:
    if shutil.which("terminal-notifier"):
        subprocess.run(
            ["terminal-notifier", "-title", title, "-message", message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if shutil.which("osascript"):
        script = f'display notification "{escape_applescript(message)}" with title "{escape_applescript(title)}"'
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def notify_windows(title: str, message: str) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return

    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.MessageBox]::Show('{escape_powershell(message)}', '{escape_powershell(title)}')"
    )
    subprocess.run(
        [powershell, "-NoProfile", "-Command", script],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def escape_powershell(value: str) -> str:
    return value.replace("'", "''")


def escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def status_line(snapshot: ItemSnapshot) -> str:
    return f"{snapshot.title} | comments={snapshot.comment_count} | points={snapshot.score_count}"


def next_backoff_seconds(error: requests.RequestException, interval: int) -> int:
    response = getattr(error, "response", None)
    if response is not None and response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return max(interval, int(retry_after))
        return max(interval * 2, 60)
    return interval


def run() -> int:
    args = parse_args()

    url, item_id = parse_hn_item(normalize_url(args.url or prompt_for_url()))
    if args.interval < 10:
        raise SystemExit("--interval must be at least 10 seconds.")

    session = build_session(args.user_agent)

    print(f"Watching {url}")
    print(f"Polling HN updates every {args.interval} seconds")

    try:
        current = fetch_item_snapshot(session, item_id, timeout=args.timeout)
    except (requests.RequestException, ValueError) as exc:
        print(f"Initial fetch failed: {exc}", file=sys.stderr)
        return 1

    print(f"Baseline: {status_line(current)}")

    while True:
        time.sleep(args.interval)

        try:
            changed_items = fetch_changed_items(session, timeout=args.timeout)
        except requests.RequestException as exc:
            delay = next_backoff_seconds(exc, args.interval)
            print(f"Updates fetch failed: {exc}. Backing off for {delay} seconds.", file=sys.stderr)
            time.sleep(delay)
            continue

        if item_id not in changed_items:
            if args.show_unchanged:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No change: {status_line(current)}")
            continue

        try:
            latest = fetch_item_snapshot(session, item_id, timeout=args.timeout)
        except (requests.RequestException, ValueError) as exc:
            delay = next_backoff_seconds(exc, args.interval)
            print(f"Item fetch failed: {exc}. Backing off for {delay} seconds.", file=sys.stderr)
            time.sleep(delay)
            continue

        changes = describe_changes(current, latest)
        if changes:
            message = "; ".join(changes)
            notify("HN-Watch Alert", message)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {latest.title}")
            print(message)
        elif args.show_unchanged:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No count increase: {status_line(latest)}")

        current = latest


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
