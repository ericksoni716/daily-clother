"""The release's "What's new", read from the changelog by tools/whats_new.py (run by the release workflow)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "whats_new.py"

CHANGELOG = """# Changelog

Some words about the file.

## Unreleased

### Changed

- Trips pack lighter, and the list
  wraps onto a second line.

### Fixed

- The [weather](https://example.invalid/weather) is right again.

[weather]: https://example.invalid/weather

## 1.2.0

### Fixed

- A sock no longer goes missing.

## 1.1.0

See the release.
"""


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("whats_new", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_versions_own_section_wins(tool):
    assert tool.whats_new(CHANGELOG, "1.2.0") == "### Fixed\n\n- A sock no longer goes missing.\n"
    assert tool.whats_new(CHANGELOG, "v1.1.0") == "See the release.\n"


def test_a_version_not_yet_written_down_gets_unreleased(tool):
    notes = tool.whats_new(CHANGELOG, "1.3.0")
    assert notes.startswith("### Changed\n\n- Trips pack lighter, and the list\n  wraps onto a second line.\n")
    assert "### Fixed\n\n- The [weather](https://example.invalid/weather) is right again." in notes
    assert "[weather]:" not in notes          # link references are dropped
    assert "1.2.0" not in notes and "sock" not in notes   # stops at the next version


def test_an_empty_version_section_falls_back_to_unreleased(tool):
    text = CHANGELOG.replace("## 1.2.0\n\n### Fixed\n\n- A sock no longer goes missing.\n", "## 1.2.0\n\n")
    assert tool.whats_new(text, "1.2.0").startswith("### Changed")


def test_headings_with_a_date_or_brackets_name_the_version(tool):
    assert tool.whats_new("## [2.0.0] - 2026-11-20\n\n- New.\n", "2.0.0") == "- New.\n"
    assert tool.whats_new("## 2.0.0 (20 November)\n\n- New.\n", "2.0.0") == "- New.\n"
    assert tool.whats_new("## 2.0.0\n\n- New.\n", "2.0.01") == ""


def test_nothing_to_say_prints_nothing(tool, tmp_path):
    assert tool.whats_new("# Changelog\n\n## Unreleased\n\n\n## 1.0.0\n\n", "1.1.0") == ""
    assert tool.whats_new("# Changelog\n", "1.1.0") == ""
    assert tool.whats_new("## Unreleased\n\n[x]: https://example.invalid\n", "1.1.0") == ""

    def run(*args):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=30)

    empty = tmp_path / "CHANGELOG.md"
    empty.write_text("# Changelog\n\n## Unreleased\n", encoding="utf-8")
    for args in ((("1.1.0", str(empty))), ("1.1.0", str(tmp_path / "missing.md"))):
        done = run(*args)
        assert (done.returncode, done.stdout) == (0, "")
    full = tmp_path / "full.md"
    full.write_text(CHANGELOG, encoding="utf-8")
    done = run("1.2.0", str(full))
    assert (done.returncode, done.stdout) == (0, "### Fixed\n\n- A sock no longer goes missing.\n")
