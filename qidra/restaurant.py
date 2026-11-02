"""A restaurant = its menu, its sales history and its own settings."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .calendar_eg import DAY_NAMES, DEFAULT_SCHOOL, DEFAULT_WEEKEND, event_on, season


@dataclass
class Restaurant:
    name: str
    sales: pd.DataFrame            # date | dish | sold | (prepared)
    days: pd.DataFrame             # index=date ; weather + explicit event flags (column per event key)
    dishes: list[dict]             # {"name", "price", "estimate", "active"}
    events: list[dict]             # {"key", "name", "match", "file"}
    weekend: list[int] = field(default_factory=lambda: list(DEFAULT_WEEKEND))
    school: dict = field(default_factory=lambda: dict(DEFAULT_SCHOOL))
    weather_cats: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ calendar context for one day
    def active_events(self, d: date, overrides: set | None = None) -> set:
        """Events on day d: explicit value stored for that day if any, else the built-in calendar."""
        if overrides is not None:
            return set(overrides)
        out = set()
        row = self.days.loc[d] if d in self.days.index else None
        for ev in self.events:
            val = row.get(ev["key"]) if row is not None and ev["key"] in self.days.columns else None
            if val is not None and not pd.isna(val):
                if val:
                    out.add(ev["key"])
            elif event_on(ev, d, self.school):
                out.add(ev["key"])
        return out

    def weather_on(self, d: date):
        if not self.weather_cats:
            return None
        if "weather" in self.days.columns and d in self.days.index and pd.notna(self.days.at[d, "weather"]):
            return self.days.at[d, "weather"]
        same_month = self.days[[x.month == d.month for x in self.days.index]]
        if "weather" in same_month and same_month["weather"].notna().any():
            return same_month["weather"].mode().iat[0]
        return self.weather_cats[0]

    def describe_day(self, d: date) -> dict:
        return {
            "day": DAY_NAMES[d.weekday()],
            "weekend": d.weekday() in self.weekend,
            "season": season(d),
        }

    # ------------------------------------------------------------ editing
    @property
    def has_prepared(self) -> bool:
        return "prepared" in self.sales and self.sales["prepared"].notna().any()

    def active_dishes(self) -> list[dict]:
        return [d for d in self.dishes if d.get("active", True)]

    def add_dish(self, name: str, estimate: float, price: float | None = None):
        if any(d["name"] == name for d in self.dishes):
            raise ValueError("الأكلة دي موجودة")
        self.dishes.append({"name": name, "price": price, "estimate": float(estimate), "active": True})

    def log_day(self, d: date, sold: dict, prepared: dict | None = None,
                weather: str | None = None, events: set | None = None):
        """Record what actually happened on day d (replaces that day if it exists)."""
        prepared = prepared or {}
        rows = [{"date": d, "dish": k, "sold": float(v),
                 "prepared": float(prepared[k]) if prepared.get(k) is not None else np.nan}
                for k, v in sold.items() if v is not None]
        if not rows:
            raise ValueError("اكتب الكمية اللي اتباعت لأكلة واحدة على الأقل")
        new = pd.DataFrame(rows)
        if "prepared" not in self.sales:
            self.sales = self.sales.assign(prepared=np.nan)
        self.sales = pd.concat([self.sales[self.sales["date"] != d], new], ignore_index=True)
        row = {ev["key"]: int(ev["key"] in (events or set())) for ev in self.events}
        if weather is not None:
            row["weather"] = weather
            if weather not in self.weather_cats:
                self.weather_cats.append(weather)
        days = self.days.drop(index=d, errors="ignore")
        self.days = pd.concat([days, pd.DataFrame([row], index=[d])]).sort_index()
        for k in sold:
            if not any(x["name"] == k for x in self.dishes):
                self.dishes.append({"name": k, "price": None, "estimate": None, "active": True})

    # ------------------------------------------------------------ export
    def to_dataframe(self) -> pd.DataFrame:
        """Long table with every derived column — same shape as the project's dataset."""
        price = {d["name"]: d.get("price") for d in self.dishes}
        out = []
        for d, grp in self.sales.sort_values("date").groupby("date", sort=True):
            info, ev = self.describe_day(d), self.active_events(d)
            base = {"التاريخ": d, "اليوم": info["day"], "ويك اند": int(info["weekend"]), "الفصل": info["season"]}
            if self.weather_cats:
                base["الطقس"] = self.weather_on(d)
            for _, r in grp.iterrows():
                row = dict(base, **{"الأكلة": r["dish"], "السعر (جنيه)": price.get(r["dish"]),
                                    "الكمية المباعة": r["sold"]})
                if "prepared" in grp:
                    row["الكمية المحضرة"] = r["prepared"]
                row.update({e["name"]: int(e["key"] in ev) for e in self.events})
                out.append(row)
        return pd.DataFrame(out)

    def to_excel_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.to_dataframe().to_excel(buf, index=False, sheet_name="البيانات")
        return buf.getvalue()


def template_excel_bytes() -> bytes:
    """Blank file a restaurant owner fills in."""
    sales = pd.DataFrame({
        "التاريخ": ["2025-03-01", "2025-03-01", "2025-03-02", "2025-03-02"],
        "الأكلة": ["كشري", "طعمية", "كشري", "طعمية"],
        "الكمية المباعة": [63, 58, 55, 49],
        "الكمية المحضرة": [70, 60, 60, 55],
        "السعر": [25, 10, 25, 10],
        "الطقس": ["معتدل", "معتدل", "حار", "حار"],
    })
    how = pd.DataFrame({"إزاي تملا الملف": [
        "كل صف = أكلة واحدة في يوم واحد.",
        "المطلوب: التاريخ + الأكلة + الكمية المباعة.",
        "الكمية المحضرة والسعر والطقس اختياريين — امسح العمود لو مش عندك.",
        "التاريخ بالشكل 2025-03-01 أو 01/03/2025.",
        "مش محتاج تكتب اليوم أو الويك إند أو الفصل أو رمضان والأعياد — التطبيق بيحسبهم من التاريخ.",
        "عندك مناسبة خاصة (ماتش، مولد في المنطقة…)؟ زوّد عمود باسمها: 1 في أيامها و0 في الباقي.",
        "كل ما البيانات أطول (سنة أو سنتين) التوقع يبقى أدق.",
    ]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        sales.to_excel(xw, index=False, sheet_name="المبيعات")
        how.to_excel(xw, index=False, sheet_name="التعليمات")
        for ws in xw.book.worksheets:
            ws.sheet_view.rightToLeft = True
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 18
    return buf.getvalue()
