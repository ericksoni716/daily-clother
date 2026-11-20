"""The shoe tracing bench (`trace_shoes`).

The drawing code lives in the backend as `closet.drawing`; `illustrate` and
`fills` here are those same modules under their old names, kept for the bench's
imports. The tests of the tagger and the drawing are in `backend/tests/`.
The backend folder is put on the import path so the bench runs from a checkout
without installing anything.
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.append(str(_BACKEND))
