from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any

from dateutil.relativedelta import relativedelta

from tendertrace.intent.numbers import parse_cn_int


_RELATIVE_RE = re.compile(
    r"(?P<text>(?:最近|近)\s*(?P<n>[0-9一二两三四五六七八九十]+)\s*个?\s*(?P<unit>天|日|周|星期|月|年))"
)
_ABSOLUTE_MONTH_RE = re.compile(
    r"(?P<text>(?P<year>20\d{2})\s*年\s*(?P<month>[0-9一二两三四五六七八九十]{1,3})\s*月份?)"
)


_UNIT_MAP = {
    "天": "day",
    "日": "day",
    "周": "week",
    "星期": "week",
    "月": "month",
    "年": "year",
}


@dataclass(frozen=True)
class ParsedTime:
    value: dict[str, Any]
    matched_text: str


def parse_time_expr(query: str) -> ParsedTime:
    absolute = _ABSOLUTE_MONTH_RE.search(query)
    if absolute:
        year = int(absolute.group("year"))
        month_raw = absolute.group("month")
        month = parse_cn_int(month_raw)
        if month is not None and 1 <= month <= 12:
            last_day = calendar.monthrange(year, month)[1]
            return ParsedTime(
                value={
                    "kind": "absolute",
                    "from": date(year, month, 1).isoformat(),
                    "to": date(year, month, last_day).isoformat(),
                    "origin": "rule",
                },
                matched_text=absolute.group("text"),
            )

    relative = _RELATIVE_RE.search(query)
    if relative:
        n = parse_cn_int(relative.group("n"))
        unit = _UNIT_MAP[relative.group("unit")]
        if n is not None and n > 0:
            return ParsedTime(
                value={
                    "kind": "relative",
                    "ast": {"op": "last", "unit": unit, "n": n},
                    "origin": "rule",
                },
                matched_text=relative.group("text"),
            )

    return ParsedTime(
        value={
            "kind": "relative",
            "ast": {"op": "last", "unit": "month", "n": 1},
            "origin": "default",
        },
        matched_text="",
    )


def resolve_window(time_expr: dict[str, Any], now: datetime) -> dict[str, str]:
    if time_expr["kind"] == "absolute":
        return {"from": time_expr["from"], "to": time_expr["to"]}
    ast = time_expr["ast"]
    unit = ast["unit"]
    n = ast["n"]
    delta_args = {
        "day": {"days": n},
        "week": {"weeks": n},
        "month": {"months": n},
        "year": {"years": n},
    }[unit]
    start = now - relativedelta(**delta_args)
    return {"from": start.date().isoformat(), "to": now.date().isoformat()}

