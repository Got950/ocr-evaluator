from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


_Q_MARKER = re.compile(
    r"(?im)(^|\n)\s*(?:q(?:uestion)?\s*)?(?P<num>[0-9Il]{1,3})\s*(?:[\)\.\:\-])?\s+",
)


def _to_int(s: str) -> Optional[int]:
    s = s.strip()
    s = s.replace("I", "1").replace("l", "1").replace("|", "1")
    if not s.isdigit():
        return None
    try:
        return int(s)
    except Exception:
        return None


def segment_answers(full_text: str) -> Dict[int, str]:
    if not full_text:
        return {}

    matches: List[Tuple[int, int, int]] = []
    for m in _Q_MARKER.finditer(full_text):
        num_raw = m.group("num") or ""
        num = _to_int(num_raw)
        if num is None or num <= 0:
            continue
        matches.append((m.start(), m.end(), num))

    if not matches:
        return {}

    out: Dict[int, str] = {}
    for i, (start, end, num) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else len(full_text)
        ans = full_text[end:next_start].strip()
        if not ans:
            continue
        prev = out.get(num)
        out[num] = (prev + "\n" + ans).strip() if prev else ans

    return out

