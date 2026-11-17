"""How much one request may send, in one place (see DECISIONS, "Upload limits").

`gate.py` counts the bytes as they come in and stops at these, before anything is parsed or written.
"""
from __future__ import annotations

import re

MB = 1024 * 1024

PHOTO_BYTES = 60 * MB          # one photo as the owner chose it, before the page shrinks it
FORM_BYTES = 1 * MB            # the rest of an upload: the form's own lines, the upload key, a name, the photo's hash
UPLOAD_BYTES = PHOTO_BYTES + FORM_BYTES   # a request that carries a photo
BODY_BYTES = 1 * MB            # any other request: JSON, a few kilobytes at most

# The calls that carry a photo (multipart, one photo each); every other request gets BODY_BYTES.
UPLOADS = frozenset({
    ("POST", "/api/items"),
    ("POST", "/api/sources"),
    ("POST", "/api/would-this-work"),
    ("POST", "/api/add/sort"),          # up to ten small copies of the photos chosen on Add
})
# And those with an item in their path: another photo of a shoe, a retaken photo.
# (They were missing, so a phone's photo was refused there as "more than Closet reads in one request".)
UPLOAD_PATHS = (re.compile(r"/api/items/[^/]+/photos?"),)


def limit_for(method: str, path: str) -> int:
    if (method, path) in UPLOADS or (method == "POST" and any(p.fullmatch(path) for p in UPLOAD_PATHS)):
        return UPLOAD_BYTES
    return BODY_BYTES
