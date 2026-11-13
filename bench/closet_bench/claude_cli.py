"""Moved to the backend: `backend/closet/tagger/claude_cli.py`. This name is the same module, kept so bench code and tools work unchanged."""
import sys

from closet.tagger import claude_cli as _moved

sys.modules[__name__] = _moved
