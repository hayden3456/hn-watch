# HN-Watch

HN-Watch watches a Hacker News post and alerts you when it gets new comments or more points.

It works on Linux, macOS, and Windows.

## Install

From PyPI:

```bash
pip install hn-watch
```

From this repo:

```bash
pip install .
```

## Use

Watch a post:

```bash
hn-watch --url "https://news.ycombinator.com/item?id=47779274"
```

Or run it and paste the URL when prompted:

```bash
hn-watch
```

Useful options:

```bash
hn-watch --url "https://news.ycombinator.com/item?id=47779274" --interval 30
hn-watch --url "https://news.ycombinator.com/item?id=47779274" --show-unchanged
```

## What It Does

- watches one Hacker News item URL
- checks for new comments
- checks for point increases
- sends a desktop notification when counts go up
- uses the official Hacker News API

## Notes

- only supports Hacker News item URLs
- ignores `#comment` fragments and watches the main item
- prints alerts in the terminal even if desktop notifications are unavailable
