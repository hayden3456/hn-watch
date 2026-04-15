from __future__ import annotations

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from hn_watch import __version__


COMMENT_PATTERNS = [
    r"(\d[\d,]*)\s+comments?\b",
    r"\bcomments?\s*[:\-]?\s*(\d[\d,]*)",
]

SCORE_PATTERNS = [
    r"(\d[\d,]*)\s+(?:points?|score)\b",
]


@dataclass
class PageSnapshot:
    url: str
    title: str
    comment_count: Optional[int]
    score_count: Optional[int]
    body_hash: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hn-watch",
        description="Watch a Hacker News item URL and notify when comments or points increase.",
    )
    parser.add_argument("--url", help="Page URL to watch.")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds. Default: 60",
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
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = f"https://{url}"

    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def validate_hn_item_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.netloc.lower() != "news.ycombinator.com" or parsed.path != "/item" or "id" not in query:
        raise SystemExit("HN-Watch only supports Hacker News item URLs like https://news.ycombinator.com/item?id=12345")
    return url


def fetch_snapshot(url: str, timeout: int, user_agent: str) -> PageSnapshot:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": user_agent},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else url
    comment_count, score_count = extract_hacker_news_metrics(url, soup)
    body_hash = hashlib.sha256(response.text.encode("utf-8")).hexdigest()

    return PageSnapshot(
        url=url,
        title=title,
        comment_count=comment_count,
        score_count=score_count,
        body_hash=body_hash,
    )


def extract_hacker_news_metrics(url: str, soup: BeautifulSoup) -> tuple[Optional[int], Optional[int]]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.netloc.lower() != "news.ycombinator.com" or parsed.path != "/item" or "id" not in query:
        raise ValueError("Not a Hacker News item URL")

    score_count: Optional[int] = None
    score_node = soup.select_one("span.score")
    if score_node:
        score_count = extract_metric([score_node.get_text(" ", strip=True)], SCORE_PATTERNS)

    comment_count: Optional[int] = None
    subtext = soup.select_one("td.subtext, span.subline")
    if subtext:
        for link in subtext.select('a[href^="item?id="]'):
            text = link.get_text(" ", strip=True)
            count = extract_metric([text], COMMENT_PATTERNS)
            if count is not None:
                comment_count = count
                break

    return comment_count, score_count


def extract_metric(text_chunks: list[str], patterns: list[str]) -> Optional[int]:
    values: list[int] = []
    for text in text_chunks:
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw_value = next((group for group in match.groups() if group), None)
                if raw_value:
                    try:
                        values.append(int(raw_value.replace(",", "")))
                    except ValueError:
                        continue
    return max(values) if values else None


def describe_changes(old: PageSnapshot, new: PageSnapshot) -> list[str]:
    changes: list[str] = []

    comment_delta = delta_string("Comments", old.comment_count, new.comment_count)
    if comment_delta:
        changes.append(comment_delta)

    score_delta = delta_string("Points", old.score_count, new.score_count)
    if score_delta:
        changes.append(score_delta)

    if not changes and old.body_hash != new.body_hash:
        changes.append("The HN item changed, but comments and points did not increase.")

    return changes


def delta_string(label: str, old: Optional[int], new: Optional[int]) -> Optional[str]:
    if old is None or new is None or new <= old:
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


def status_line(snapshot: PageSnapshot) -> str:
    parts = [snapshot.title]
    if snapshot.comment_count is not None:
        parts.append(f"comments={snapshot.comment_count}")
    if snapshot.score_count is not None:
        parts.append(f"points={snapshot.score_count}")
    return " | ".join(parts)


def run() -> int:
    args = parse_args()

    url = validate_hn_item_url(normalize_url(args.url or prompt_for_url()))
    if args.interval < 5:
        raise SystemExit("--interval must be at least 5 seconds.")

    print(f"Watching {url}")
    print(f"Polling every {args.interval} seconds")

    try:
        current = fetch_snapshot(url, timeout=args.timeout, user_agent=args.user_agent)
    except requests.RequestException as exc:
        print(f"Initial fetch failed: {exc}", file=sys.stderr)
        return 1

    print(f"Baseline: {status_line(current)}")

    while True:
        time.sleep(args.interval)
        try:
            latest = fetch_snapshot(url, timeout=args.timeout, user_agent=args.user_agent)
        except requests.RequestException as exc:
            print(f"Fetch failed: {exc}", file=sys.stderr)
            continue

        changes = describe_changes(current, latest)
        if changes:
            message = "; ".join(changes)
            notify("HN-Watch Alert", message)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {latest.title}")
            print(message)
        elif args.show_unchanged:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No change: {status_line(latest)}")

        current = latest


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
