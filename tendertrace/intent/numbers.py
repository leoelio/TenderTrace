from __future__ import annotations


_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_cn_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in _DIGITS:
        return _DIGITS[value]
    if "十" in value:
        left, _, right = value.partition("十")
        tens = _DIGITS.get(left, 1) if left else 1
        ones = _DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    total = 0
    for char in value:
        if char not in _DIGITS:
            return None
        total = total * 10 + _DIGITS[char]
    return total

