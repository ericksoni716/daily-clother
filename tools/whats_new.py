"""Print what is new in a version of Nines, from the changelog, as Markdown.

    python tools/whats_new.py VERSION [CHANGELOG]

The release workflow puts this under "## What's new" in the release's notes. It prints the changelog's
`## <version>` section when there is one with something in it, otherwise the `## Unreleased` section, and
nothing at all when both are empty or missing (or the file cannot be read), so a release never fails because
of the changelog. The `### Changed` and `### Fixed` subheadings and their bullets are kept as written; link
reference lines (`[x]: https://…`) are dropped. Standard library only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S")


def _heading(line: str) -> str | None:
    """The title of a `## ` heading ("0.9.0", "Unreleased"), or None for any other line."""
    m = re.match(r"^##\s+(.+?)\s*#*\s*$", line)
    return m.group(1) if m and not line.startswith("###") else None


def _names(title: str, version: str) -> bool:
    """Whether a heading's title names this version: "0.9.0", "v0.9.0", "[0.9.0]", "0.9.0 - 2026-11-20"."""
    m = re.match(r"^\[?v?([0-9A-Za-z.+-]+?)\]?(?:\s|$|[(:,])", title + " ")
    return bool(m) and m.group(1) == version.removeprefix("v")


def sections(text: str) -> dict[str, list[str]]:
    """Each `## ` section's lines (without the heading), by its title as written."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.replace("\r\n", "\n").split("\n"):
        title = _heading(line)
        if title is not None:
            current = found.setdefault(title, [])
            continue
        if current is not None:
            current.append(line.rstrip())
    return found


def _tidy(lines: list[str]) -> str:
    kept = [ln for ln in lines if not LINK_REFERENCE.match(ln)]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return text + "\n" if text else ""


def whats_new(text: str, version: str) -> str:
    """The Markdown for this version: its own section, else Unreleased, else ""."""
    found = sections(text)
    for title, lines in found.items():
        if _names(title, version) and _tidy(lines):
            return _tidy(lines)
    for title, lines in found.items():
        if title.strip("[]").lower() == "unreleased":
            return _tidy(lines)
    return ""


def main(argv: list[str]) -> int:
    if not argv or len(argv) > 2:
        print("usage: whats_new.py VERSION [CHANGELOG]", file=sys.stderr)
        return 2
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    sys.stdout.write(whats_new(text, argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
