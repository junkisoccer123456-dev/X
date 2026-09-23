"""X（旧Twitter）の文字数カウント.

twitter-text v3 の設定に準拠: 下記の範囲の文字は1、それ以外（日本語など）は2と数え、
上限は280（全角140字相当）。URL は長さに関係なく23として数える。
"""

from __future__ import annotations

import re

URL_RE = re.compile(r"https?://\S+")
URL_WEIGHT = 23
FREE_LIMIT = 280

# twitter-text config v3 の weight=100 の範囲
_LIGHT_RANGES = (
    (0x0000, 0x10FF),
    (0x2000, 0x200D),
    (0x2010, 0x201F),
    (0x2032, 0x2037),
)


def _char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in _LIGHT_RANGES) else 2


def weighted_length(text: str) -> int:
    total = 0
    pos = 0
    for m in URL_RE.finditer(text):
        total += sum(_char_weight(c) for c in text[pos : m.start()])
        total += URL_WEIGHT
        pos = m.end()
    total += sum(_char_weight(c) for c in text[pos:])
    return total
