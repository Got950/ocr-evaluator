from __future__ import annotations

import re


_NON_ALLOWED = re.compile(r"[^a-z0-9.\s]+")
_MULTI_SPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    t = text.lower()
    t = _NON_ALLOWED.sub(" ", t)
    t = _MULTI_SPACE.sub(" ", t)
    return t.strip()

