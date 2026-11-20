"""Phase 0 bench: cutout, tagging and illustration experiments.

The tagger now lives in the backend as `closet.tagger`, and the drawing code as
`closet.drawing`; `schema`, `taxonomy`, `tagging`, `routes`, `illustrate` and
`fills` here are those same modules under their old names, kept for the bench
commands. The tests of the tagger and the drawing are in `backend/tests/`.
The backend folder is put on the import path so the bench runs from a checkout
without installing anything.
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.append(str(_BACKEND))
