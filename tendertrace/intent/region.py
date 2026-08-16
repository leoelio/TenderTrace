from __future__ import annotations

from dataclasses import dataclass

from tendertrace.intent.admin_divisions import CITIES, DISTRICTS, PROVINCES


@dataclass(frozen=True)
class RegionMatch:
    value: dict[str, object]
    matched_text: str


_PLACE_SUFFIXES = (
    "特别行政区",
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "自治区",
    "土家族苗族自治州",
    "布依族苗族自治州",
    "哈尼族彝族自治州",
    "藏族羌族自治州",
    "朝鲜族自治州",
    "蒙古自治州",
    "藏族自治州",
    "彝族自治州",
    "苗族自治州",
    "傣族自治州",
    "白族自治州",
    "傈僳族自治州",
    "自治州",
    "地区",
    "盟",
    "新区",
    "省",
    "市",
    "区",
    "县",
)

_PROVINCE_SHORT_NAMES: dict[str, tuple[str, ...]] = {
    "北京": ("京",),
    "天津": ("津",),
    "河北": ("冀",),
    "山西": ("晋",),
    "内蒙古": ("蒙",),
    "辽宁": ("辽",),
    "吉林": ("吉",),
    "黑龙江": ("黑",),
    "上海": ("沪",),
    "江苏": ("苏",),
    "浙江": ("浙",),
    "安徽": ("皖",),
    "福建": ("闽",),
    "江西": ("赣",),
    "山东": ("鲁",),
    "河南": ("豫",),
    "湖北": ("鄂",),
    "湖南": ("湘",),
    "广东": ("粤",),
    "广西": ("桂",),
    "海南": ("琼",),
    "重庆": ("渝",),
    "四川": ("川", "蜀"),
    "贵州": ("黔", "贵"),
    "云南": ("滇", "云"),
    "西藏": ("藏",),
    "陕西": ("陕", "秦"),
    "甘肃": ("甘", "陇"),
    "青海": ("青",),
    "宁夏": ("宁",),
    "新疆": ("新",),
    "台湾": ("台",),
    "香港": ("港",),
    "澳门": ("澳",),
}

_INTERNATIONAL_SCOPES = (
    ("欧洲复兴开发银行", "ebrd"),
    ("European Bank for Reconstruction and Development", "ebrd"),
    ("EBRD", "ebrd"),
    ("ebrd", "ebrd"),
    ("非洲开发银行", "afdb"),
    ("African Development Bank", "afdb"),
    ("AfDB", "afdb"),
    ("AFDB", "afdb"),
    ("afdb", "afdb"),
    ("亚洲开发银行", "adb"),
    ("Asian Development Bank", "adb"),
    ("ADB", "adb"),
    ("adb", "adb"),
    ("美洲开发银行", "idb"),
    ("Inter-American Development Bank", "idb"),
    ("拉丁美洲", "idb"),
    ("拉美", "idb"),
    ("IDB", "idb"),
    ("idb", "idb"),
    ("世界银行", "worldbank"),
    ("联合国全球采购市场", "global"),
    ("联合国采购", "global"),
    ("UNGM", "global"),
    ("英国", "uk"),
    ("United Kingdom", "uk"),
    ("UK", "uk"),
    ("加拿大", "canada"),
    ("Canada", "canada"),
    ("乌克兰", "ukraine"),
    ("Ukraine", "ukraine"),
    ("Prozorro", "ukraine"),
    ("欧盟", "eu"),
    ("欧洲", "eu"),
    ("全球", "global"),
    ("海外", "global"),
    ("国际", "global"),
)


def _short_name(value: str) -> str:
    for suffix in _PLACE_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def _aliases(
    name: str,
    aliases: tuple[str, ...],
    extra: tuple[str, ...] = (),
    *,
    allow_single_short: bool = False,
) -> tuple[str, ...]:
    values: list[str] = []
    for item in (name, _short_name(name), *aliases, *extra):
        if item and item not in values:
            values.append(item)
            short = _short_name(item)
            if short and short not in values and (allow_single_short or len(short) > 1):
                values.append(short)
    return tuple(values)


def _province_full_name(short_name: str) -> str:
    for name in PROVINCES:
        if _short_name(name) == short_name:
            return name
    return short_name


_PROVINCE_ALIASES = sorted(
    (
        (
            alias,
            _short_name(province),
            adcode,
            _aliases(
                province,
                aliases,
                _PROVINCE_SHORT_NAMES.get(_short_name(province), ()),
                allow_single_short=True,
            ),
        )
        for province, (adcode, aliases) in PROVINCES.items()
        for alias in _aliases(
            province,
            aliases,
            _PROVINCE_SHORT_NAMES.get(_short_name(province), ()),
            allow_single_short=True,
        )
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)

_CITY_ALIASES = sorted(
    (
        (alias, _short_name(city), _short_name(province), city_adcode, _aliases(city, aliases))
        for city, (province, city_adcode, aliases) in CITIES.items()
        for alias in _aliases(city, aliases)
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)

_DISTRICT_ALIASES = sorted(
    (
        (
            alias,
            _short_name(district.rsplit(":", 1)[-1]),
            _short_name(province),
            _short_name(city),
            district_adcode,
            _aliases(district.rsplit(":", 1)[-1], aliases),
        )
        for district, (province, city, district_adcode, aliases) in DISTRICTS.items()
        for alias in _aliases(district.rsplit(":", 1)[-1], aliases)
        if alias != "市辖" and len(alias) > 1
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)


def parse_region(query: str) -> RegionMatch:
    for alias, scope in _INTERNATIONAL_SCOPES:
        if alias in query:
            return RegionMatch(
                value={
                    "province": None,
                    "city": None,
                    "district": None,
                    "adcode": None,
                    "city_adcode": None,
                    "district_adcode": None,
                    "aliases": [alias],
                    "city_aliases": [],
                    "district_aliases": [],
                    "scope": scope,
                    "origin": "rule",
                },
                matched_text=alias,
            )
    for alias, district, province, city, district_adcode, district_aliases in _DISTRICT_ALIASES:
        if alias in query:
            province_full = _province_full_name(province)
            province_adcode, province_aliases = PROVINCES[province_full]
            city_full = _city_full_name(city, province)
            city_adcode, city_aliases = _city_record(city_full)
            return RegionMatch(
                value={
                    "province": province,
                    "city": city,
                    "district": district,
                    "adcode": province_adcode,
                    "city_adcode": city_adcode,
                    "district_adcode": district_adcode,
                    "aliases": list(
                        _aliases(
                            province_full,
                            province_aliases,
                            _PROVINCE_SHORT_NAMES.get(province, ()),
                            allow_single_short=True,
                        )
                    )
                    + list(city_aliases)
                    + list(district_aliases),
                    "city_aliases": list(city_aliases),
                    "district_aliases": list(district_aliases),
                    "origin": "rule",
                },
                matched_text=alias,
            )
    for alias, city, province, city_adcode, city_aliases in _CITY_ALIASES:
        if alias in query:
            province_full = _province_full_name(province)
            province_adcode, province_aliases = PROVINCES[province_full]
            return RegionMatch(
                value={
                    "province": province,
                    "city": city,
                    "district": None,
                    "adcode": province_adcode,
                    "city_adcode": city_adcode,
                    "district_adcode": None,
                    "aliases": list(
                        _aliases(
                            province_full,
                            province_aliases,
                            _PROVINCE_SHORT_NAMES.get(province, ()),
                            allow_single_short=True,
                        )
                    )
                    + list(city_aliases),
                    "city_aliases": list(city_aliases),
                    "district_aliases": [],
                    "origin": "rule",
                },
                matched_text=alias,
            )
    for alias, province, adcode, aliases in _PROVINCE_ALIASES:
        if alias in query:
            return RegionMatch(
                value={
                    "province": province,
                    "city": None,
                    "district": None,
                    "adcode": adcode,
                    "city_adcode": None,
                    "district_adcode": None,
                    "aliases": list(aliases),
                    "city_aliases": [],
                    "district_aliases": [],
                    "origin": "rule",
                },
                matched_text=alias,
            )
    return RegionMatch(
        value={
            "province": None,
            "city": None,
            "district": None,
            "adcode": None,
            "city_adcode": None,
            "district_adcode": None,
            "aliases": [],
            "city_aliases": [],
            "district_aliases": [],
            "scope": "domestic",
            "origin": "missing",
        },
        matched_text="",
    )


def _city_full_name(city: str, province: str) -> str:
    for name, (item_province, _, _) in CITIES.items():
        if _short_name(name) == city and _short_name(item_province) == province:
            return name
    return _province_full_name(province)


def _city_record(city_full: str) -> tuple[str | None, tuple[str, ...]]:
    value = CITIES.get(city_full)
    if value is None:
        return None, ()
    _, city_adcode, aliases = value
    return city_adcode, _aliases(city_full, aliases)
