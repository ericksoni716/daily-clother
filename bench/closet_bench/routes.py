"""Moved to the backend: `backend/closet/tagger/routes.py`. This name is the same module, kept so bench code and tools work unchanged."""
import sys

from closet.tagger import routes as _moved

sys.modules[__name__] = _moved
