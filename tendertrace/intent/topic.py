from __future__ import annotations

import re

import jieba.posseg as pseg


_CATEGORY_SYNONYMS = {
    "充电桩": ["充电桩", "充电设施", "充电设备", "充电站", "充电基础设施", "新能源汽车充电"],
    "服务器": ["服务器", "计算服务器", "存储服务器", "信创服务器", "GPU服务器", "机架式服务器"],
    "空调": ["空调", "中央空调", "空调设备", "空调系统", "暖通空调", "制冷设备", "多联机"],
    "储能": ["储能", "储能系统", "储能电站", "新型储能", "电化学储能"],
    "医疗设备": ["医疗设备", "医用设备", "医学装备", "医疗器械", "诊疗设备"],
    "电梯": ["电梯", "扶梯", "自动扶梯", "升降梯"],
    "消防": ["消防", "消防设备", "消防设施", "消防系统"],
    "安防": ["安防", "视频监控", "监控系统", "门禁系统", "安防设备"],
    "网络设备": ["网络设备", "交换机", "路由器", "防火墙", "无线控制器"],
}

_CATEGORY_SOURCE_TERMS = {
    "充电桩": ["electric vehicle charging", "charging station", "EV charger"],
    "服务器": ["server", "data center server", "computing infrastructure"],
    "空调": ["air conditioning", "HVAC", "cooling system"],
    "储能": ["energy storage", "battery storage", "BESS"],
    "医疗设备": ["medical equipment", "medical device", "diagnostic equipment"],
    "电梯": ["elevator", "lift", "escalator"],
    "消防": ["fire protection", "fire safety equipment", "fire suppression"],
    "安防": ["security system", "video surveillance", "access control"],
    "网络设备": ["network equipment", "network infrastructure", "switch router"],
}

_NEGATIVE = ["中标", "成交", "废标", "流标", "终止", "结果"]

_STOP_PHRASES = [
    "全部招投标信息",
    "全部投标信息",
    "全部采购信息",
    "投标信息",
    "招标信息",
    "招投标信息",
    "采购信息",
    "招标公告",
    "采购公告",
    "都有哪些",
    "有哪些",
    "相关的",
    "相关",
    "全国范围",
    "全国",
    "区域内",
    "请汇总后",
    "汇总后",
    "每天",
    "每日",
    "发送给我",
    "推送给我",
    "标讯信息",
    "标讯",
    "来一份",
    "帮我盯着",
    "帮我查询",
    "查询",
    "检索",
    "全部",
    "的",
]

_STOP_WORDS = {
    "最近",
    "近",
    "月",
    "月份",
    "年",
    "今天",
    "明天",
    "昨天",
    "区域",
    "信息",
    "公告",
    "项目",
    "采购",
    "招标",
    "投标",
    "相关",
}

_KEEP_FLAGS = ("n", "vn", "eng")

_CATEGORY_ALIASES = sorted(
    (
        (alias, canonical, tuple(item for item in synonyms if item != canonical))
        for canonical, synonyms in _CATEGORY_SYNONYMS.items()
        for alias in synonyms
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)


def extract_topic(
    query: str,
    *,
    region_text: str = "",
    time_text: str = "",
    schedule_text: str = "",
) -> dict[str, object]:
    text = _remove_context(query, region_text=region_text, time_text=time_text, schedule_text=schedule_text)
    category_terms = _match_categories(text)
    if category_terms:
        core = [term["term"] for term in category_terms]
        expanded = [
            {"term": synonym, "weight": round(0.92 - index * 0.03, 2), "origin": "domain_dict"}
            for term in category_terms
            for index, synonym in enumerate(term["synonyms"])
        ]
        return {
            "core": core,
            "expanded": _dedupe_expanded(expanded, core),
            "source_terms": _source_terms(core),
            "negative": list(_NEGATIVE),
            "origin": "category_dict",
            "confidence": 0.94,
            "open_scope": False,
        }

    core = _noun_terms(text)
    confidence = 0.76 if core else 0.0
    if not core:
        core = _fallback_terms(text)
        confidence = 0.48 if core else 0.0
    return {
        "core": core,
        "expanded": [],
        "source_terms": [term for term in core if re.search(r"[A-Za-z]", term)],
        "negative": list(_NEGATIVE),
        "origin": "jieba_pos" if confidence >= 0.7 else "fallback",
        "confidence": confidence,
        "open_scope": not core and ("全部" in query or "不限主题" in query),
    }


def _remove_context(
    query: str,
    *,
    region_text: str = "",
    time_text: str = "",
    schedule_text: str = "",
) -> str:
    text = query
    for removable in (region_text, time_text, schedule_text):
        if removable:
            text = text.replace(removable, " ")
    text = re.sub(r"今天\s*\d{1,2}\s*[:：点时]\s*\d{0,2}\s*分?", " ", text)
    text = re.sub(r"每天\s*\d{1,2}\s*[:：点时]\s*\d{0,2}\s*分?", " ", text)
    text = re.sub(r"每周[一二三四五六日天1-7]?(?:早上|上午|下午|晚上)?[一二两三四五六七八九十\d:：点时半分]*", " ", text)
    for phrase in _STOP_PHRASES:
        text = text.replace(phrase, " ")
    text = re.sub(r"(或者|或是|以及|和|与|及|或)", " ", text)
    text = re.sub(r"[，,。？?！!；;：:（）(){}【】\\s]+", " ", text)
    return text


def _match_categories(text: str) -> list[dict[str, object]]:
    candidates: list[tuple[int, str, tuple[str, ...]]] = []
    for alias, canonical, synonyms in _CATEGORY_ALIASES:
        index = text.find(alias)
        if index < 0:
            continue
        candidates.append((index, canonical, synonyms))
    matched: list[dict[str, object]] = []
    seen: set[str] = set()
    for _, canonical, synonyms in sorted(candidates, key=lambda item: item[0]):
        if canonical in seen:
            continue
        seen.add(canonical)
        matched.append({"term": canonical, "synonyms": synonyms})
        if len(matched) >= 3:
            break
    return matched


def _noun_terms(text: str) -> list[str]:
    terms: list[str] = []
    for word, flag in pseg.cut(text):
        token = _normalize_token(word)
        if not token or token in _STOP_WORDS:
            continue
        if not flag.startswith(_KEEP_FLAGS):
            continue
        if len(token) == 1 and not re.match(r"[A-Za-z0-9]", token):
            continue
        terms.append(token)
        if len(terms) >= 3:
            break
    return _dedupe_terms(terms)


def _fallback_terms(text: str) -> list[str]:
    tokens = [_normalize_token(token) for token in text.split(" ") if token.strip()]
    tokens = [
        token
        for token in tokens
        if token and token not in _STOP_WORDS and not re.fullmatch(r"\d+", token)
    ]
    return _dedupe_terms(tokens[:3])


def _normalize_token(value: str) -> str:
    token = value.strip()
    if token.endswith("项目") and len(token) > 2:
        token = token[:-2]
    return token


def _dedupe_terms(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _dedupe_expanded(items: list[dict[str, object]], core: list[str]) -> list[dict[str, object]]:
    seen = set(core)
    result: list[dict[str, object]] = []
    for item in items:
        term = str(item.get("term") or "")
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(item)
    return result


def _source_terms(core: list[str]) -> list[str]:
    terms: list[str] = []
    for category in core:
        terms.extend(_CATEGORY_SOURCE_TERMS.get(category, ()))
    return _dedupe_terms(terms)
