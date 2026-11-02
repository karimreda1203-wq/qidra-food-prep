from datetime import date
from pathlib import Path

import pandas as pd

from qidra import DemandModel, build_restaurant, calendar_keys, guess_mapping, load_file
from qidra.calendar_eg import in_school, DEFAULT_SCHOOL

DATA = Path(__file__).resolve().parents[1] / "data"


def test_calendar():
    assert "sham" in calendar_keys(date(2024, 5, 6))          # Sham El-Nessim 2024
    assert "ramadan" in calendar_keys(date(2027, 2, 20))
    assert "fitr" in calendar_keys(date(2026, 3, 21))
    assert "jul23" in calendar_keys(date(2025, 7, 23))
    assert in_school(date(2025, 11, 2), DEFAULT_SCHOOL)
    assert not in_school(date(2025, 7, 15), DEFAULT_SCHOOL)


def test_long_format_sample():
    r, rep = load_file(str(DATA / "sample_restaurant.xlsx"))
    assert rep["days"] == 731 and rep["dishes"] == 15
    assert r.weekend == [4, 5, 6]                               # inferred from the file's weekend column
    m = DemandModel(r).fit()
    assert m.backtest["accuracy"] > 0.85
    plan = m.predict(date(2026, 11, 6))
    assert len(plan) == 15 and (plan["حضّر"] >= 0).all()


def test_wide_format_and_arabic_digits():
    df = pd.DataFrame({"التاريخ": ["٠١/٠٣/٢٠٢٥", "02/03/2025", "03/03/2025"], "كشري": [10, 12, 9], "طعمية": [20, 22, 18]})
    g = guess_mapping(df)
    assert g["format"] == "wide" and set(g["wide_dishes"]) == {"كشري", "طعمية"}
    r, rep = build_restaurant(df, g, "test")
    assert rep["days"] == 3 and rep["first"] == date(2025, 3, 1)


def test_new_dish_gets_estimate():
    r, _ = load_file(str(DATA / "sample_wide_format.csv"))
    r.add_dish("حواوشي", 30, 40)
    plan = DemandModel(r).fit().predict(date(2026, 11, 6))
    row = plan[plan["الأكلة"] == "حواوشي"].iloc[0]
    assert row["note"] == "أكلة جديدة" and row["حضّر"] > 30   # Friday is busier than average
