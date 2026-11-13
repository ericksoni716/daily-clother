"""Phase 0 bench: cutout, tagging and illustration experiments.

The tagger (schema, taxonomy, tagging, routes, claude_cli) now lives in the
backend as `closet.tagger`, and the drawing code (templates, illustrate, fills)
as `closet.drawing`; the modules of the same names here are that code.
The backend folder is put on the import path so the bench runs from a checkout
without installing anything.
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.append(str(_BACKEND))
