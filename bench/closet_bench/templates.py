"""Moved to the backend: `backend/closet/drawing/templates.py`. This name is the same module, kept so bench code and tools work unchanged."""
import sys

from closet.drawing import templates as _moved

sys.modules[__name__] = _moved
