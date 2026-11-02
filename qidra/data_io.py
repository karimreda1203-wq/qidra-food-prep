"""Read any restaurant's sales file and turn it into one standard shape.

Accepted layouts
  long : one row per dish per day   -> التاريخ | الأكلة | الكمية المباعة | (الكمية المحضرة) | (السعر) | (الطقس)
  wide : one row per day, dish cols -> التاريخ | كشري | طعمية | فول ...

Only date + dish + quantity sold are required. Day name, weekend, season,
school term, Ramadan and holidays are computed from the date.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta

import pandas as pd

from .calendar_eg import DEFAULT_SCHOOL, DEFAULT_WEEKEND, build_events, calendar_match_for, normalize
from .restaurant import Restaurant

SYNONYMS = {
    "date": ["التاريخ", "تاريخ", "date", "day date"],
    "dish": ["الاكله", "اكله", "الاكلات", "الصنف", "صنف", "الاصناف", "الطبق", "طبق", "المنتج", "منتج",
             "الوجبه", "وجبه", "item", "dish", "product", "menu item"],
    "prepared": ["الكميه المحضره", "المحضر", "محضره", "المحضره", "الكميه المجهزه", "المجهزه", "مجهزه", "تحضير",
                 "prepared", "produced", "cooked"],
    "sold": ["الكميه المباعه", "المباع", "مبيعات", "المبيعات", "الكميه", "عدد", "sold", "sales", "qty", "quantity"],
    "price": ["السعر", "سعر", "price"],
    "weather": ["الطقس", "طقس", "الجو", "weather"],
    "weekend": ["ويك اند", "ويكند", "weekend", "عطله", "نهايه الاسبوع"],
}
# columns the app derives itself (ignored on import)
DERIVED = ["اليوم", "الفصل", "الموسم", "السنه", "الشهر", "اليوم في الشهر", "الايراد", "الفاضل",
           "revenue", "month", "year", "season", "weekday", "day name", "total", "الاجمالي"]
ROLES = ["date", "dish", "prepared", "sold", "price", "weather", "weekend"]


# ---------------------------------------------------------------- reading
def read_table(data: bytes | str, filename: str, sheet: str | int | None = 0) -> pd.DataFrame:
    """Read .xlsx/.xls/.csv from bytes (uploads) or a path."""
    src = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    if filename.lower().endswith((".csv", ".txt")):
        df = pd.read_csv(src, encoding="utf-8-sig")
    else:
        df = pd.read_excel(src, sheet_name=sheet if sheet is not None else 0)
    df.columns = [str(c).strip() if str(c).strip() else f"عمود {i + 1}" for i, c in enumerate(df.columns)]
    return df.dropna(how="all")


def sheet_names(data: bytes, filename: str) -> list[str]:
    if filename.lower().endswith((".csv", ".txt")):
        return []
    return pd.ExcelFile(io.BytesIO(data)).sheet_names


# ---------------------------------------------------------------- cell parsing
_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")


def parse_date(v) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        if 20000 < v < 80000:  # Excel serial number
            return (datetime(1899, 12, 30) + timedelta(days=int(v))).date()
        return None
    s = str(v).translate(_AR).strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return _valid(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y = y + 2000 if y < 100 else y
        if b > 12 and a <= 12:  # month/day order
            a, b = b, a
        return _valid(y, b, a)
    return None


def _valid(y, mo, d):
    try:
        return date(y, mo, d) if 1990 <= y <= 2100 else None
    except ValueError:
        return None


def parse_num(v) -> float | None:
    if v is None or isinstance(v, (date, datetime)):
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).translate(_AR).replace(",", "").strip()
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


# ---------------------------------------------------------------- guessing the columns
def _profile(col: pd.Series) -> dict:
    vals = [v for v in col.head(600).tolist() if not (v is None or (isinstance(v, float) and pd.isna(v)))]
    n = len(vals) or 1
    nums = [parse_num(v) for v in vals]
    return {
        "n": len(vals),
        "date": sum(parse_date(v) is not None and not (isinstance(v, (int, float)) and v < 20000) for v in vals) / n,
        "num": sum(x is not None for x in nums) / n,
        "bin": sum(x in (0.0, 1.0) for x in nums) / n,
        "str": sum(isinstance(v, str) and parse_num(v) is None for v in vals) / n,
        "distinct": len({str(v) for v in vals[:600]}),
    }


def _score(name: str, words: list[str]) -> int:
    n, best = normalize(name), 0
    for w in words:
        k = normalize(w)
        if n == k:
            best = max(best, 3)
        elif n.startswith(k) or n.endswith(k):
            best = max(best, 2)
        elif k in n:
            best = max(best, 1)
    return best


def guess_mapping(df: pd.DataFrame) -> dict:
    """Guess which column is which. The UI lets the owner correct it."""
    cols = list(df.columns)
    prof = {c: _profile(df[c]) for c in cols}
    ok = {
        "date": lambda p: p["date"] > 0.8,
        "dish": lambda p: p["str"] > 0.6,
        "sold": lambda p: p["num"] > 0.9 and p["bin"] < 0.98,
        "prepared": lambda p: p["num"] > 0.9 and p["bin"] < 0.98,
        "price": lambda p: p["num"] > 0.9,
        "weather": lambda p: p["str"] > 0.6 and p["distinct"] < 40,
        "weekend": lambda p: p["bin"] > 0.95,
    }
    used, mapping = set(), {r: None for r in ROLES}
    for role in ROLES:
        best, best_score = None, 0
        for c in cols:
            if c in used or not ok[role](prof[c]):
                continue
            s = _score(c, SYNONYMS[role])
            if role != "weekend" and _score(c, DERIVED) >= 2 and s < 3:
                continue
            if s > best_score:
                best, best_score = c, s
        if best is None and role == "date":
            best = next((c for c in cols if c not in used and prof[c]["date"] > 0.9), None)
        if best is not None:
            mapping[role] = best
            used.add(best)

    fmt = "long" if mapping["dish"] else "wide"
    events, wide_dishes = [], []
    for c in cols:
        if c in used or not prof[c]["n"]:
            continue
        derived = _score(c, DERIVED) >= 2
        if prof[c]["bin"] > 0.98:
            if calendar_match_for(c) or not derived:
                events.append(c)
        elif prof[c]["num"] > 0.9 and fmt == "wide" and not derived:
            wide_dishes.append(c)
    mapping.update(format=fmt, events=events, wide_dishes=wide_dishes)
    return mapping


# ---------------------------------------------------------------- building the restaurant
def build_restaurant(df: pd.DataFrame, mapping: dict, name: str = "مطعمي") -> tuple[Restaurant, dict]:
    m = mapping
    if not m.get("date"):
        raise ValueError("اختار عمود التاريخ.")
    if m["format"] == "long" and not (m.get("dish") and m.get("sold")):
        raise ValueError("اختار عمود الأكلة وعمود الكمية المباعة.")
    if m["format"] == "wide" and not m.get("wide_dishes"):
        raise ValueError("اختار عمود أكلة واحد على الأقل.")

    report = {"rows": len(df), "skipped": 0, "negative": 0}
    dates = df[m["date"]].map(parse_date)
    bad = dates.isna()
    report["skipped"] += int(bad.sum())
    df, dates = df[~bad], dates[~bad]

    # -------- per-day info: weather, owner's event flags, weekend flags
    day = pd.DataFrame({"date": dates})
    if m.get("weather"):
        day["weather"] = df[m["weather"]].astype("string").str.strip()
    event_cols = list(m.get("events") or [])
    for i, c in enumerate(event_cols):
        day[f"f{i}"] = (df[c].map(parse_num) == 1).astype(int)
    weekend = list(DEFAULT_WEEKEND)
    if m.get("weekend"):
        wk = pd.DataFrame({"dow": [d.weekday() for d in dates], "v": df[m["weekend"]].map(parse_num)}).dropna()
        days_on = sorted(wk.groupby("dow")["v"].mean().loc[lambda s: s > 0.5].index.tolist())
        if 0 < len(days_on) < 7:
            weekend = days_on
    agg = {c: "max" for c in day.columns if c.startswith("f")}
    if "weather" in day:
        agg["weather"] = lambda s: s.dropna().mode().iat[0] if s.notna().any() else None
    days = day.groupby("date").agg(agg) if agg else pd.DataFrame(index=sorted(set(dates)))

    # -------- sales rows
    if m["format"] == "long":
        long = pd.DataFrame({
            "date": dates,
            "dish": df[m["dish"]].astype("string").str.strip(),
            "sold": df[m["sold"]].map(parse_num),
        })
        if m.get("prepared"):
            long["prepared"] = df[m["prepared"]].map(parse_num)
        if m.get("price"):
            long["price"] = df[m["price"]].map(parse_num)
    else:
        long = (pd.DataFrame({"date": dates}).join(df[m["wide_dishes"]])
                .melt(id_vars="date", var_name="dish", value_name="sold"))
        long["sold"] = long["sold"].map(parse_num)
        long["dish"] = long["dish"].astype(str)

    missing = long["dish"].isna() | (long["dish"] == "") | long["sold"].isna()
    report["skipped"] += int(missing.sum()) if m["format"] == "long" else 0
    long = long[~missing]
    neg = long["sold"] < 0
    report["negative"] = int(neg.sum())
    long = long[~neg]
    report["duplicates"] = int(long.duplicated(["date", "dish"]).sum())
    sums = {"sold": "sum"}
    if "prepared" in long:
        sums["prepared"] = lambda s: s.sum(min_count=1)
    if "price" in long:
        sums["price"] = "last"
    sales = long.groupby(["date", "dish"], sort=False).agg(sums).reset_index()

    dishes = list(dict.fromkeys(long["dish"]))
    prices = sales.dropna(subset=["price"]).groupby("dish")["price"].last().to_dict() if "price" in sales else {}
    weather_cats = sorted(days["weather"].dropna().unique().tolist()) if "weather" in days else []
    days = days.loc[days.index.isin(sales["date"].unique())]

    restaurant = Restaurant(
        name=name or "مطعمي",
        sales=sales[["date", "dish", "sold"] + [c for c in ("prepared",) if c in sales]],
        days=days,
        dishes=[{"name": d, "price": prices.get(d), "estimate": None, "active": True} for d in dishes],
        events=build_events(event_cols),
        weekend=weekend,
        school=dict(DEFAULT_SCHOOL),
        weather_cats=weather_cats,
    )
    all_days = sorted(sales["date"].unique())
    report.update(
        days=len(all_days), dishes=len(dishes),
        first=all_days[0] if all_days else None, last=all_days[-1] if all_days else None,
        weekend_from_file=bool(m.get("weekend")),
        gaps=int(sum(max(0, (b - a).days - 1) for a, b in zip(all_days, all_days[1:]))),
    )
    return restaurant, report


def load_file(path: str, name: str | None = None, sheet=0) -> tuple[Restaurant, dict]:
    """One-liner for scripts/notebooks: read + guess + build."""
    df = read_table(path, path, sheet)
    return build_restaurant(df, guess_mapping(df), name or re.sub(r"\.\w+$", "", path.split("/")[-1]))
