from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from tendertrace.intent.numbers import parse_cn_int


_DIGIT_COLON_TIME_RE = re.compile(r"(?<!\d)(?P<hour>\d{1,2})\s*[:：]\s*(?P<minute>\d{1,2})(?!\d)")
_DIGIT_POINT_TIME_RE = re.compile(r"(?<!\d)(?P<hour>\d{1,2})\s*[点时]\s*(?P<half>半)?(?P<minute>\d{1,2})?分?")
_CN_POINT_TIME_RE = re.compile(
    r"(?P<hour>[一二两三四五六七八九十]{1,3})\s*[点时]\s*(?P<half>半)?(?P<minute>[一二两三四五六七八九十]{1,3})?分?"
)
_WEEKDAY_MAP = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "日": 0,
    "天": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 0,
}


@dataclass(frozen=True)
class ParsedSchedule:
    value: dict[str, Any]
    matched_text: str


def _format_time(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def extract_time_of_day(query: str) -> tuple[int, int, str]:
    for regex in (_DIGIT_COLON_TIME_RE, _DIGIT_POINT_TIME_RE):
        match = regex.search(query)
        if match:
            hour = int(match.group("hour"))
            minute = int(match.groupdict().get("minute") or 0)
            if match.groupdict().get("half"):
                minute = 30
            return hour, minute, match.group(0)
    match = _CN_POINT_TIME_RE.search(query)
    if match:
        hour = parse_cn_int(match.group("hour")) or 9
        minute_raw = match.groupdict().get("minute")
        minute = parse_cn_int(minute_raw) if minute_raw else 0
        if match.groupdict().get("half"):
            minute = 30
        return hour, minute or 0, match.group(0)
    return 9, 0, ""


def parse_schedule(query: str) -> ParsedSchedule:
    hour, minute, time_text = extract_time_of_day(query)
    time_value = _format_time(hour, minute)

    if re.search(r"每天|每日", query):
        return ParsedSchedule(
            value={
                "kind": "recurring",
                "cron": f"{minute} {hour} * * *",
                "tz": "Asia/Shanghai",
                "time": time_value,
                "origin": "rule",
            },
            matched_text=time_text,
        )

    weekly = re.search(r"每周\s*([一二三四五六日天1-7])|每星期\s*([一二三四五六日天1-7])", query)
    if weekly:
        weekday = weekly.group(1) or weekly.group(2)
        return ParsedSchedule(
            value={
                "kind": "recurring",
                "cron": f"{minute} {hour} * * {_WEEKDAY_MAP[weekday]}",
                "tz": "Asia/Shanghai",
                "time": time_value,
                "origin": "rule",
            },
            matched_text=(weekly.group(0) + time_text).strip(),
        )

    monthly = re.search(r"每月\s*([0-9一二两三四五六七八九十]{1,3})\s*[号日]", query)
    if monthly:
        day = parse_cn_int(monthly.group(1)) or 1
        return ParsedSchedule(
            value={
                "kind": "recurring",
                "cron": f"{minute} {hour} {day} * *",
                "tz": "Asia/Shanghai",
                "time": time_value,
                "origin": "rule",
            },
            matched_text=(monthly.group(0) + time_text).strip(),
        )

    if "今天" in query and re.search(r"发送|推送|来一份|汇总", query):
        return ParsedSchedule(
            value={
                "kind": "once_at",
                "time": time_value,
                "tz": "Asia/Shanghai",
                "origin": "rule",
            },
            matched_text=("今天" + time_text).strip(),
        )

    return ParsedSchedule(value={"kind": "immediate", "origin": "rule"}, matched_text="")

