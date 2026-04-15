# HN-Watch

HN-Watch is a small cross-platform CLI that watches a Hacker News item page and alerts you when the post gets new comments or more points.

It is built with:

- Python
- `requests`
- `BeautifulSoup`

It works on:

- Linux
- macOS
- Windows

## What It Watches

HN-Watch only supports Hacker News item pages:

```text
https://news.ycombinator.com/item?id=12345
```

It checks:

- comment count
- point count

If either number goes up, HN-Watch prints an alert in the terminal and sends a desktop notification.

## How Notifications Work

HN-Watch uses platform-specific notifications:

- Linux: `notify-send`
- macOS: `terminal-notifier` if installed, otherwise `osascript`
- Windows: PowerShell WinForms message box

The tool always also prints alerts in the terminal, so it still works even if desktop notifications are unavailable.

## Install

The easiest install path for most users is `pipx`.

### Linux

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install hn-watch
```

Optional desktop notification dependency:

```bash
sudo apt install libnotify-bin
```

### macOS

```bash
brew install pipx
pipx ensurepath
pipx install hn-watch
```

Optional preferred notification tool:

```bash
brew install terminal-notifier
```

### Windows

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install hn-watch
```

## Usage

Pass the Hacker News item URL with `--url`:

```bash
hn-watch --url "https://news.ycombinator.com/item?id=47779274"
```

Or run it with no URL and it will prompt for one:

```bash
hn-watch
```

Useful options:

```bash
hn-watch --url "https://news.ycombinator.com/item?id=47779274" --interval 60
hn-watch --url "https://news.ycombinator.com/item?id=47779274" --timeout 15
hn-watch --url "https://news.ycombinator.com/item?id=47779274" --show-unchanged
```

## Example Output

```text
Watching https://news.ycombinator.com/item?id=47779274
Polling every 60 seconds
Baseline: Making Wax Sealed Letters at Scale | Hacker News | comments=3 | points=1
[ALERT] HN-Watch Alert: Comments: 3 -> 4 (+1)
```

## How It Works

1. HN-Watch fetches the Hacker News item page with `requests`.
2. It parses the HTML with `BeautifulSoup`.
3. It reads the post's current point count and comment count from the page.
4. It sleeps for the configured interval.
5. It fetches the page again and compares the new counts to the previous snapshot.
6. If points or comments increased, it sends a notification.

## Important Notes

- HN-Watch is intentionally limited to Hacker News item pages.
- It does not watch the HN front page, user pages, or external sites.
- It tracks increases in points and comments only.
- A URL with an anchor is fine. HN-Watch ignores the `#...` fragment and watches the underlying item page.

## Help

See the built-in CLI help:

```bash
hn-watch --help
```
