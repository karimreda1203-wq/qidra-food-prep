"""Demand model: one ridge regression per dish on log(1 + quantity sold).

Why log-linear: effects in a restaurant are multiplicative (a weekend adds ~35%
to every dish, Ramadan more), which becomes additive after the log.
On the sample project data it beat gradient boosting (MAE 2.9 vs 4.9 plates).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from .calendar_eg import DAY_NAMES
from .restaurant import Restaurant

SAFETY = {
    "low": {"z": 0.0, "label": "أقل هدر", "hint": "حضّر على قد المتوقع — يكفي في نص الأيام تقريباً"},
    "balanced": {"z": 0.5, "label": "متوازن", "hint": "زيادة صغيرة — يكفي في حوالي ٧ أيام من ١٠"},
    "safe": {"z": 1.0, "label": "ما ينقصش", "hint": "هامش أكبر — يكفي في حوالي ٨ أيام من ١٠، والهدر أعلى"},
}
MIN_DAYS = 21          # fewer days than this -> plain average
BACKTEST_DAYS = 60


def feature_names(r: Restaurant) -> list[str]:
    return (["weekend"] + [f"dow_{i}" for i in range(7)] + [f"month_{m}" for m in range(1, 13)]
            + [f"ev_{e['key']}" for e in r.events] + [f"w_{w}" for w in r.weather_cats] + ["trend"])


def features(r: Restaurant, days: list[date], t0: date, events=None, weather=None, t_max=None) -> np.ndarray:
    """Feature matrix for a list of days. `events`/`weather` override the history (used for prediction)."""
    names = feature_names(r)
    idx = {n: i for i, n in enumerate(names)}
    X = np.zeros((len(days), len(names)))
    for row, d in enumerate(days):
        X[row, idx["weekend"]] = d.weekday() in r.weekend
        X[row, idx[f"dow_{d.weekday()}"]] = 1
        X[row, idx[f"month_{d.month}"]] = 1
        for k in r.active_events(d, events):
            if f"ev_{k}" in idx:
                X[row, idx[f"ev_{k}"]] = 1
        w = weather if weather is not None else r.weather_on(d)
        if w is not None and f"w_{w}" in idx:
            X[row, idx[f"w_{w}"]] = 1
        t = (d - t0).days / 365
        X[row, idx["trend"]] = min(t, t_max + 0.25) if t_max is not None else t
    return X


@dataclass
class DishModel:
    kind: str                 # "ridge" | "avg"
    mean_recent: float
    n: int
    model: Ridge | None = None
    sigma: float = 0.0


class DemandModel:
    def __init__(self, restaurant: Restaurant):
        self.r = restaurant
        self.dish_models: dict[str, DishModel] = {}
        self.backtest: dict | None = None

    # ------------------------------------------------------------------ training
    def _fit(self, upto: date | None = None) -> dict[str, DishModel]:
        r = self.r
        sales = r.sales if upto is None else r.sales[r.sales["date"] <= upto]
        all_days = sorted(sales["date"].unique())
        X_all = features(r, all_days, self.t0)
        row_of = {d: i for i, d in enumerate(all_days)}
        out = {}
        for dish, g in sales.groupby("dish"):
            g = g.sort_values("date")
            y = np.log1p(g["sold"].to_numpy(float))
            recent = float(g["sold"].tail(90).mean())
            if len(g) < MIN_DAYS:
                out[dish] = DishModel("avg", recent, len(g))
                continue
            X = X_all[[row_of[d] for d in g["date"]]]
            m = Ridge(alpha=1.0).fit(X, y)
            resid = y - m.predict(X)
            dof = max(1, len(y) - X.shape[1] // 2)
            out[dish] = DishModel("ridge", recent, len(g), m, max(0.05, float(np.sqrt((resid ** 2).sum() / dof)) * 1.1))
        return out

    def fit(self, safety: str = "balanced") -> "DemandModel":
        days = sorted(self.r.sales["date"].unique())
        if not days:
            raise ValueError("مفيش بيانات")
        self.t0, self.first, self.last = days[0], days[0], days[-1]
        self.t_max = (self.last - self.t0).days / 365
        self.n_days = len(days)
        self.backtest = self._backtest(days, safety) if len(days) >= 150 else None
        self.dish_models = self._fit()
        return self

    def _backtest(self, days: list[date], safety: str) -> dict:
        """Hide the last 60 days, train on the rest, and compare with what was really sold."""
        cut = days[-BACKTEST_DAYS - 1]
        models = self._fit(upto=cut)
        test = self.r.sales[self.r.sales["date"] > cut]
        test_days = sorted(test["date"].unique())
        X = features(self.r, test_days, self.t0)
        row_of = {d: i for i, d in enumerate(test_days)}
        z = SAFETY[safety]["z"]
        price = {d["name"]: d.get("price") or 0 for d in self.r.dishes}
        rows = []
        for _, s in test.iterrows():
            dm = models.get(s["dish"])
            if dm is None:
                continue
            mid, rec = self._point(dm, X[row_of[s["date"]]], z)
            rec = ceil(rec)
            rows.append({"dish": s["dish"], "sold": s["sold"], "pred": mid,
                         "waste": max(0, rec - s["sold"]), "short": max(0, s["sold"] - rec),
                         "real_waste": max(0, s["prepared"] - s["sold"]) if "prepared" in s and pd.notna(s.get("prepared")) else np.nan,
                         "price": price.get(s["dish"], 0)})
        df = pd.DataFrame(rows)
        df["ae"] = (df["pred"] - df["sold"]).abs()
        per = df.groupby("dish").agg(ae=("ae", "sum"), sold=("sold", "sum"), mae=("ae", "mean"))
        per["accuracy"] = (1 - per["ae"] / per["sold"]).clip(lower=0)
        has_real = df["real_waste"].notna().any()
        return {
            "days": len(test_days),
            "accuracy": max(0.0, 1 - df["ae"].sum() / df["sold"].sum()),
            "per_dish": per[["mae", "accuracy"]],
            "model_waste": int(df["waste"].sum()), "model_short": int(df["short"].sum()),
            "model_waste_money": float((df["waste"] * df["price"]).sum()),
            "real_waste": int(df["real_waste"].sum()) if has_real else None,
            "real_waste_money": float((df["real_waste"].fillna(0) * df["price"]).sum()) if has_real else None,
            "sold": int(df["sold"].sum()), "safety": safety,
        }

    @staticmethod
    def _point(dm: DishModel, x: np.ndarray, z: float) -> tuple[float, float]:
        if dm.kind == "avg":
            return dm.mean_recent, dm.mean_recent * (1 + 0.15 * z)
        mu = float(dm.model.predict(x.reshape(1, -1))[0])
        return float(np.expm1(mu)), float(np.expm1(mu + z * dm.sigma))

    # ------------------------------------------------------------------ prediction
    def predict(self, d: date, safety: str = "balanced", events: set | None = None,
                weather: str | None = None, leftovers: dict | None = None) -> pd.DataFrame:
        """How much of each dish to prepare on day d."""
        r, z = self.r, SAFETY[safety]["z"]
        leftovers = leftovers or {}
        x = features(r, [d], self.t0, events=events, weather=weather, t_max=self.t_max)[0]
        rows, pred_sum, mean_sum = [], 0.0, 0.0
        for dish in r.active_dishes():
            name, dm = dish["name"], self.dish_models.get(dish["name"])
            row = {"الأكلة": name, "note": ""}
            if dm is not None:
                mid, rec = self._point(dm, x, z)
                if dm.kind == "ridge":
                    mu = np.log1p(mid)
                    lo, hi = np.expm1(mu - 1.28 * dm.sigma), np.expm1(mu + 1.28 * dm.sigma)
                    pred_sum, mean_sum = pred_sum + mid, mean_sum + dm.mean_recent
                else:
                    lo, hi, row["note"] = mid * 0.75, mid * 1.25, "بيانات قليلة"
                row.update(mid=mid, lo=max(0, lo), hi=hi, rec=rec)
            rows.append(row)
        factor = pred_sum / mean_sum if mean_sum else 1.0
        for row, dish in zip(rows, r.active_dishes()):
            if "mid" not in row and dish.get("estimate"):
                mid = dish["estimate"] * factor   # new dish: owner's guess x today's restaurant-wide factor
                row.update(mid=mid, lo=mid * 0.7, hi=mid * 1.3, rec=mid * (1 + 0.2 * z), note="أكلة جديدة")
        out = pd.DataFrame(rows)
        if out.empty or "mid" not in out:
            return pd.DataFrame(columns=["الأكلة", "متوقع يتباع", "من", "إلى", "فاضل من أمس", "حضّر", "note"])
        out = out.dropna(subset=["mid"])
        out["فاضل من أمس"] = out["الأكلة"].map(lambda n: max(0, int(leftovers.get(n, 0) or 0)))
        out["حضّر"] = (np.ceil(out["rec"]) - out["فاضل من أمس"]).clip(lower=0).astype(int)
        out["متوقع يتباع"] = out["mid"].round().astype(int)
        out["من"] = out["lo"].round().astype(int)
        out["إلى"] = out["hi"].round().astype(int)
        return out[["الأكلة", "متوقع يتباع", "من", "إلى", "فاضل من أمس", "حضّر", "note"]].reset_index(drop=True)

    def default_leftovers(self, d: date) -> dict:
        """Yesterday's prepared − sold, if yesterday was logged with prepared amounts."""
        s = self.r.sales
        y = s[(s["date"] == d - timedelta(days=1))]
        if "prepared" not in y or y["prepared"].isna().all():
            return {}
        return {row.dish: max(0, int(row.prepared - row.sold)) for row in y.itertuples() if pd.notna(row.prepared)}

    def week_ahead(self, start: date, safety: str = "balanced") -> pd.DataFrame:
        rows = []
        for i in range(7):
            d = start + timedelta(days=i)
            p = self.predict(d, safety)
            names = [e["name"] for e in self.r.events if e["key"] in self.r.active_events(d) and e.get("match") != ["school"]]
            rows.append({"date": d, "اليوم": DAY_NAMES[d.weekday()], "إجمالي": int(np.ceil(p["حضّر"].sum())) if len(p) else 0,
                         "مناسبات": "، ".join(names)})
        return pd.DataFrame(rows)


def receipt_text(restaurant_name: str, d: date, plan: pd.DataFrame) -> str:
    """Same format as the project's food_receipt.txt files."""
    lines = ["", "", "=" * 36, "        FOOD RECEIPT", "=" * 36,
             restaurant_name, f"{d.isoformat()}  {DAY_NAMES[d.weekday()]}", "-" * 36, ""]
    lines += [f"{r['الأكلة']} ---> {int(r['حضّر'])}" for _, r in plan.iterrows()]
    lines += ["", "-" * 36, f"الإجمالي ---> {int(plan['حضّر'].sum())}", ""]
    return "\n".join(lines)
