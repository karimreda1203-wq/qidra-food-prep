"""Egyptian calendar features derived from a date.

Everything a restaurant owner should NOT have to type by hand:
day name, weekend, season, school term, Ramadan, Eids, Sham El-Nessim
and official holidays. Islamic dates are approximate (+/- 1 day).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache

# weekday(): Monday=0 ... Sunday=6
DAY_NAMES = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
FRIDAY, SATURDAY, SUNDAY = 4, 5, 6
DEFAULT_WEEKEND = [FRIDAY, SATURDAY]
DEFAULT_SCHOOL = {"start": "09-21", "end": "06-10", "break_start": "01-24", "break_end": "02-07"}

# [1st Ramadan, 1st Eid al-Fitr, 1st Eid al-Adha, Hijri new year, Mawlid] — Egypt, approximate
ISLAMIC = {
    2019: ["05-06", "06-04", "08-11", "08-31", "11-09"],
    2020: ["04-24", "05-24", "07-31", "08-20", "10-29"],
    2021: ["04-13", "05-13", "07-20", "08-10", "10-19"],
    2022: ["04-02", "05-02", "07-09", "07-30", "10-08"],
    2023: ["03-23", "04-21", "06-28", "07-19", "09-27"],
    2024: ["03-11", "04-10", "06-16", "07-07", "09-15"],
    2025: ["03-01", "03-30", "06-06", "06-26", "09-04"],
    2026: ["02-19", "03-20", "05-27", "06-16", "08-26"],
    2027: ["02-08", "03-10", "05-16", "06-06", "08-15"],
    2028: ["01-28", "02-27", "05-05", "05-25", "08-03"],
    2029: ["01-16", "02-14", "04-24", "05-14", "07-24"],
    2030: ["01-06", "02-05", "04-13", "05-03", "07-13"],
}
FIXED = {
    "01-01": "newyear", "01-07": "jan7", "01-25": "jan25", "02-14": "valentine",
    "03-21": "mother", "04-25": "apr25", "05-01": "may1", "06-30": "jun30",
    "07-23": "jul23", "10-06": "oct6",
}
OFFICIAL = ["jan7", "jan25", "apr25", "may1", "jun30", "jul23", "oct6", "hny", "mawlid"]

CAL_EVENTS = [
    {"key": "ramadan", "name": "رمضان", "match": ["ramadan"]},
    {"key": "fitr", "name": "عيد الفطر", "match": ["fitr"]},
    {"key": "adha", "name": "عيد الأضحى", "match": ["adha"]},
    {"key": "sham", "name": "شم النسيم", "match": ["sham"]},
    {"key": "valentine", "name": "عيد الحب", "match": ["valentine"]},
    {"key": "mother", "name": "عيد الأم", "match": ["mother"]},
    {"key": "newyear", "name": "رأس السنة", "match": ["newyear"]},
    {"key": "official", "name": "إجازة رسمية", "match": OFFICIAL},
    {"key": "school", "name": "أيام الدراسة", "match": ["school"]},
]


def season(d: date) -> str:
    m = d.month
    if m in (12, 1, 2):
        return "شتاء"
    if m <= 5:
        return "ربيع"
    if m <= 8:
        return "صيف"
    return "خريف"


def orthodox_easter(year: int) -> date:
    """Coptic/Orthodox Easter (Meeus Julian algorithm, converted to Gregorian)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return date(year, month, day) + timedelta(days=13)


def _md(d: date) -> str:
    return f"{d.month:02d}-{d.day:02d}"


@lru_cache(maxsize=None)
def calendar_keys(d: date) -> frozenset:
    keys = set()
    if _md(d) in FIXED:
        keys.add(FIXED[_md(d)])
    if orthodox_easter(d.year) + timedelta(days=1) == d:
        keys.add("sham")
    row = ISLAMIC.get(d.year)
    if row:
        ram, fitr, adha, hny, maw = (date(d.year, int(x[:2]), int(x[3:])) for x in row)
        if ram <= d < fitr:
            keys.add("ramadan")
        if fitr <= d < fitr + timedelta(days=3):
            keys.add("fitr")
        if adha <= d < adha + timedelta(days=4):
            keys.add("adha")
        if d == hny:
            keys.add("hny")
        if d == maw:
            keys.add("mawlid")
    return frozenset(keys)


def in_school(d: date, school: dict) -> bool:
    md = _md(d)
    in_year = md >= school["start"] or md < school["end"]
    in_break = school["break_start"] <= md < school["break_end"]
    return in_year and not in_break


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(text) -> str:
    s = str(text or "").translate(_AR_DIGITS).lower()
    s = re.sub(r"[ً-ْـ]", "", s)
    s = re.sub("[أإآ]", "ا", s).replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"[_\-()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def calendar_match_for(column_name: str):
    """Map an owner's event column (e.g. 'ثورة 23 يوليو') to calendar keys, so future dates are known."""
    n = normalize(column_name)
    rules = [
        (("رمضان", "ramadan"), ["ramadan"]),
        (("فطر",), ["fitr"]),
        (("اضحي", "الكبير"), ["adha"]),
        (("شم ", "النسيم"), ["sham"]),
        (("الحب", "فالنتين", "valentine"), ["valentine"]),
        (("عيد الام", "mother"), ["mother"]),
        (("راس السنه", "new year"), ["newyear"]),
        (("يوليو",), ["jul23"]),
        (("اكتوبر",), ["oct6"]),
        (("يناير", "الشرطه"), ["jan25"]),
        (("سيناء",), ["apr25"]),
        (("عمال",), ["may1"]),
        (("يونيو",), ["jun30"]),
        (("مولد", "نبوي"), ["mawlid"]),
        (("ميلاد", "كريسماس"), ["jan7"]),
        (("هجري",), ["hny"]),
        (("دراس", "مدارس", "school"), ["school"]),
        (("رسمي", "اجازه", "holiday"), OFFICIAL),
    ]
    for words, keys in rules:
        if any(w in n for w in words):
            return list(keys)
    return None


def build_events(file_event_columns: list[str]) -> list[dict]:
    """Owner's own event columns first, then built-in calendar events they did not cover."""
    events = [
        {"key": f"f{i}", "name": name, "match": calendar_match_for(name), "file": True}
        for i, name in enumerate(file_event_columns)
    ]
    covered = {k for e in events for k in (e["match"] or [])}
    for ce in CAL_EVENTS:
        remaining = [k for k in ce["match"] if k not in covered]
        if remaining:
            events.append({"key": ce["key"], "name": ce["name"], "match": remaining, "file": False})
    return events


def event_on(event: dict, d: date, school: dict) -> bool:
    if not event.get("match"):
        return False
    keys = calendar_keys(d)
    return any(in_school(d, school) if k == "school" else k in keys for k in event["match"])
