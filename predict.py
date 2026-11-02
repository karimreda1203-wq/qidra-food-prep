"""Command-line prediction — no UI needed.

Examples
  python predict.py data/sample_restaurant.xlsx
  python predict.py my_restaurant.xlsx --date 2026-11-06 --safety safe --out food_receipt.txt
"""
import argparse
from datetime import date

from qidra import SAFETY, DemandModel, load_file, receipt_text


def main():
    ap = argparse.ArgumentParser(description="How much of each dish to prepare on a given day.")
    ap.add_argument("data", help="sales file (.xlsx or .csv): date + dish + quantity sold")
    ap.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--safety", default="balanced", choices=list(SAFETY))
    ap.add_argument("--name", default=None, help="restaurant name on the receipt")
    ap.add_argument("--out", default="food_receipt.txt")
    a = ap.parse_args()

    restaurant, report = load_file(a.data, a.name)
    print(f"Loaded {report['days']} days, {report['dishes']} dishes ({report['first']} → {report['last']})")
    model = DemandModel(restaurant).fit(a.safety)
    if model.backtest:
        print(f"Backtest accuracy on the last {model.backtest['days']} days: {model.backtest['accuracy']:.0%}")

    d = date.fromisoformat(a.date)
    info = restaurant.describe_day(d)
    events = [e["name"] for e in restaurant.events if e["key"] in restaurant.active_events(d)]
    print(f"\n{d} · {info['day']} · {'weekend' if info['weekend'] else 'weekday'} · {info['season']}"
          + (f" · {', '.join(events)}" if events else ""))
    plan = model.predict(d, a.safety)
    print(plan.drop(columns="note").to_string(index=False))

    text = receipt_text(restaurant.name, d, plan)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()
