"""The app is called Nines (DECISIONS, "The word sweep: Closet to Nines"): no word the program says or sends calls it
Closet again. Every string in the server's code is read, except docstrings, which may tell the history: log lines,
messages, the command-line help, the tray's labels and the user agents. "closet", the place, is lower case in those
strings or a name of its own (the tab is the frontend's), so it does not trip this."""
import ast
import re
from pathlib import Path

CODE = Path(__file__).resolve().parents[1] / "closet"
OLD_NAME = re.compile(r"(?<![-\w])Closet\b(?!\.exe|\.app)")   # X-Closet-… headers and Closet.exe, the old file, are not it

# the names kept to carry the old one over, and the one log line that says what was carried over
CARRIED_OVER = {
    ("apikey.py", "Closet"),           # OLD_SERVICE: the keychain entry up to 0.13.0
    ("autostart.py", "Closet"),        # OLD_NAME: start at login up to 0.11.0
    ("backup.py", "Closet backup"),    # OLD_SUBFOLDER
    ("config.py", "Closet"),           # the data folder while it has not moved yet
    ("datafolder.py", "Closet"),       # OLD: the data folder up to 0.11.0
    ("cli.py", "the API key in the keychain moved from the entry named Closet to the one named Nines"),
}


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def test_no_string_the_program_says_or_sends_calls_it_closet():
    found = []
    for path in sorted(CODE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
                    and OLD_NAME.search(node.value) and (path.name, node.value) not in CARRIED_OVER):
                found.append(f"{path.relative_to(CODE)}:{node.lineno}: {node.value[:80]!r}")
    assert not found, "the app is called Nines:\n" + "\n".join(found)


def test_every_name_kept_to_carry_the_old_one_over_is_still_there():
    """So the list above cannot quietly allow more than it needs to."""
    present = set()
    for path in sorted(CODE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                present.add((path.name, node.value))
    assert CARRIED_OVER <= present


def test_the_old_name_is_caught_where_a_person_would_read_it():
    for said in ('log.info("Closet opens in its own window")', 'USER_AGENT = "Closet/1 (model download)"',
                 'pystray.MenuItem("Open Closet", show)', 'ap.add_argument("--browser", help="instead of Closet\'s window")'):
        values = [n.value for n in ast.walk(ast.parse(said)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert any(OLD_NAME.search(v) for v in values), said
    for fine in ("Your closet is kept either way.", "X-Closet-Client", "carried over from Closet.exe", "closet.db"):
        assert not OLD_NAME.search(fine), fine
