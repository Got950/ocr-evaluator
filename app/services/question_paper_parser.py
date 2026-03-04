from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


_Q_MARKER = re.compile(
    r"(?im)(^|\n)\s*(?:section\s+[a-z]\s*[:\-]?\s*)?(?:q(?:uestion)?\s*)?(?P<num>[0-9Il]{1,3})\s*(?:[\)\.\:\-])?\s+"
)


def _to_int(s: str) -> Optional[int]:
    s = (s or "").strip().replace("I", "1").replace("l", "1").replace("|", "1")
    if not s.isdigit():
        return None
    try:
        return int(s)
    except Exception:
        return None

_MARKS_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)\(\s*(?P<m>[0-9]{1,3})\s*marks?\s*\)"),
    re.compile(r"(?i)\[\s*(?P<m>[0-9]{1,3})\s*marks?\s*\]"),
    re.compile(r"(?i)(?P<m>[0-9]{1,3})\s*marks?\b"),
    re.compile(r"(?i)\[\s*(?P<m>[0-9]{1,3})\s*\]"),
]


def _guess_marks(text: str) -> Optional[int]:
    t = (text or "").strip()
    if not t:
        return None
    for pat in _MARKS_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        try:
            v = int(m.group("m"))
        except Exception:
            continue
        if v > 0:
            return v
    return None


def parse_question_paper(extracted_text: str) -> List[Dict[str, Any]]:
    """
    Parse OCR text from a question paper into an ordered list of question drafts.

    Output items:
      - number: int
      - question_text: str
      - max_marks_guess: Optional[int]
    """
    text = (extracted_text or "").strip()
    if not text:
        return []

    matches: List[Tuple[int, int, int]] = []
    for m in _Q_MARKER.finditer(text):
        num = _to_int(m.group("num") or "")
        if num is None or num <= 0:
            continue
        matches.append((m.start(), m.end(), num))

    if not matches:
        return []

    out: List[Dict[str, Any]] = []
    for i, (start, end, num) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        body = text[end:next_start].strip()
        if not body:
            continue
        out.append(
            {
                "number": int(num),
                "question_text": body,
                "max_marks_guess": _guess_marks(body),
            }
        )

    return out

