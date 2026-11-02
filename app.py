"""Qidra — Streamlit app.

Run locally:   streamlit run app.py
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from qidra import DAY_NAMES, SAFETY, DemandModel, build_restaurant, guess_mapping, read_table, receipt_text, template_excel_bytes
from qidra.calendar_eg import ISLAMIC, orthodox_easter
from qidra.data_io import load_file, sheet_names
import html

import ui_style

SAMPLE = Path(__file__).parent / "data" / "sample_restaurant.xlsx"

st.set_page_config(page_title="قِدرة | تحضير المطبخ", page_icon="🍲", layout="wide")
st.markdown(ui_style.css(), unsafe_allow_html=True)


# ---------------------------------------------------------------- state
@st.cache_resource(show_spinner=False)
def _sample_restaurant():
    r, _ = load_file(str(SAMPLE), "مطعم المشروع (تجريبي)")
    return r


def set_restaurant(r):
    st.session_state.r = r
    retrain()


def retrain():
    with st.spinner("بيتعلّم من بياناتك…"):
        st.session_state.model = DemandModel(st.session_state.r).fit(st.session_state.safety)


if "safety" not in st.session_state:
    st.session_state.safety = "balanced"
if "r" not in st.session_state:
    set_restaurant(copy.deepcopy(_sample_restaurant()))
    st.session_state.is_demo = True

r = st.session_state.r
m: DemandModel = st.session_state.model


# ---------------------------------------------------------------- sidebar: load data
with st.sidebar:
    st.markdown('<p class="brand">قِدرة</p>', unsafe_allow_html=True)
    st.caption("كمية التحضير اليومية لكل أكلة — عشان تقلل هدر الأكل")
    st.subheader("١. بيانات المطعم")
    up = st.file_uploader("ارفع ملف المبيعات (Excel أو CSV)", type=["xlsx", "xls", "csv"])
    st.download_button("تحميل نموذج فاضي للمطعم", template_excel_bytes(), "نموذج بيانات المطعم.xlsx",
                       width="stretch")
    if st.session_state.get("is_demo"):
        st.info("شغّال دلوقتي على بيانات المشروع التجريبية. ارفع ملف مطعمك عشان تبدأ.")
    elif st.button("رجوع للبيانات التجريبية", width="stretch"):
        set_restaurant(copy.deepcopy(_sample_restaurant()))
        st.session_state.is_demo = True
        st.rerun()

    if up is not None:
        data = up.getvalue()
        sheets = sheet_names(data, up.name)
        sheet = st.selectbox("الشيت", sheets) if len(sheets) > 1 else 0
        try:
            df = read_table(data, up.name, sheet)
        except Exception as e:  # noqa: BLE001
            st.error(f"مش قادر أقرا الملف: {e}")
            st.stop()
        g = guess_mapping(df)
        st.subheader("٢. كل عمود معناه إيه؟")
        cols = ["— مش موجود —"] + list(df.columns)
        pick = lambda label, key, required=False: (lambda v: None if v == cols[0] else v)(
            st.selectbox(label + (" *" if required else ""), cols,
                         index=cols.index(g[key]) if g.get(key) in cols else 0, key=f"map_{key}_{up.name}"))
        name = st.text_input("اسم المطعم", Path(up.name).stem.replace("_", " "))
        fmt = st.radio("شكل الملف", ["long", "wide"], index=0 if g["format"] == "long" else 1, horizontal=False,
                       format_func={"long": "كل صف = أكلة في يوم", "wide": "كل صف = يوم، والأكلات أعمدة"}.get)
        g["format"] = fmt
        g["date"] = pick("التاريخ", "date", True)
        if fmt == "long":
            g["dish"] = pick("اسم الأكلة", "dish", True)
            g["sold"] = pick("الكمية المباعة", "sold", True)
            g["prepared"] = pick("الكمية المحضرة", "prepared")
            g["price"] = pick("السعر", "price")
        else:
            taken = {g["date"]}
            options = [c for c in df.columns if c not in taken]
            default = g["wide_dishes"] or [c for c in options if pd.api.types.is_numeric_dtype(df[c])]
            g["wide_dishes"] = st.multiselect("أعمدة الأكلات", options, default=[c for c in default if c in options])
        g["weather"] = pick("الطقس", "weather")
        g["weekend"] = pick("ويك إند (0/1) — عشان نعرف أيام إجازتك", "weekend")
        used = {g.get(k) for k in ("date", "dish", "sold", "prepared", "price", "weather", "weekend")} | set(g.get("wide_dishes") or [])
        ev_opts = [c for c in df.columns if c not in used]
        g["events"] = st.multiselect("أعمدة مناسبات (0/1) من ملفك", ev_opts, default=[c for c in g["events"] if c in ev_opts],
                                     help="لو مفيش، هنستخدم تقويم المناسبات المصري المدمج")
        try:
            new_r, rep = build_restaurant(df, g, name)
            st.success(f"هيتقرا {rep['days']:,} يوم · {rep['dishes']} أكلة\n\nمن {rep['first']} لحد {rep['last']}")
            notes = []
            if rep["skipped"]:
                notes.append(f"{rep['skipped']:,} صف اتساب (تاريخ أو كمية مش مفهومة)")
            if rep["duplicates"]:
                notes.append(f"{rep['duplicates']:,} صف متكرر لنفس الأكلة في نفس اليوم — اتجمعوا")
            if rep["days"] < 60:
                notes.append("الأيام قليلة — التوقع هيبقى تقريبي. الأحسن سنة أو أكتر.")
            notes.append("أيام الويك إند: " + " + ".join(DAY_NAMES[d] for d in new_r.weekend))
            st.caption("\n\n".join(notes))
            if st.button("استيراد وتدريب", type="primary", width="stretch"):
                set_restaurant(new_r)
                st.session_state.is_demo = False
                st.rerun()
        except ValueError as e:
            st.warning(str(e))

    st.divider()
    st.caption("البيانات مش بتتحفظ على السيرفر. بعد ما تسجّل أيام جديدة، نزّل نسخة Excel من «بيانات المطعم» وارفعها المرة الجاية.")


# ---------------------------------------------------------------- main
_stats = [("يوم بيانات", f"{m.n_days:,}"), ("أكلة", str(len(r.dishes)))]
if m.backtest:
    _stats.append(("دقة التوقع", f"{m.backtest['accuracy']:.0%}"))
_stats.append(("النهارده", f"{DAY_NAMES[date.today().weekday()]} {date.today():%d/%m}"))
st.markdown(ui_style.hero(html.escape(r.name), _stats, "كمية كل أكلة المفروض تتحضر النهارده — متحسبة من مبيعات مطعمك"),
            unsafe_allow_html=True)
tab_today, tab_data, tab_log, tab_settings = st.tabs(["تحضير النهارده", "بيانات المطعم", "تسجيل يوم", "الإعدادات"])

# ---------- today
with tab_today:
    left, right = st.columns([1, 2.2], gap="large")
    with left:
        d = st.date_input("اليوم", date.today(), format="YYYY-MM-DD")
        info = r.describe_day(d)
        cal_events = r.active_events(d)
        school_ev = next((e for e in r.events if e.get("match") == ["school"]), None)
        chips = [f'<span class="chip">{info["day"]}</span>',
                 f'<span class="chip {"hot" if info["weekend"] else ""}">{"ويك إند" if info["weekend"] else "يوم عادي"}</span>',
                 f'<span class="chip">{info["season"]}</span>']
        if school_ev:
            on = school_ev["key"] in cal_events
            chips.append(f'<span class="chip {"on" if on else ""}">{"فيه دراسة" if on else "مفيش دراسة"}</span>')
        st.markdown("**اتحسب من التاريخ**<br>" + "".join(chips), unsafe_allow_html=True)
        names = {e["name"]: e["key"] for e in r.events}
        chosen = st.multiselect("مناسبات اليوم (اتعرفت أوتوماتيك — تقدر تغيّر)", list(names),
                                default=[e["name"] for e in r.events if e["key"] in cal_events], key=f"ev_{d}")
        weather = None
        if r.weather_cats:
            w0 = r.weather_on(d)
            weather = st.selectbox("الطقس", r.weather_cats, index=r.weather_cats.index(w0) if w0 in r.weather_cats else 0)
        safety = st.radio("مستوى الأمان", list(SAFETY), index=list(SAFETY).index(st.session_state.safety),
                          format_func=lambda k: SAFETY[k]["label"], horizontal=True)
        st.caption(SAFETY[safety]["hint"])
        if safety != st.session_state.safety:
            st.session_state.safety = safety
        if (d - m.last).days > 45:
            st.warning(f"آخر يوم في بياناتك {m.last} — التوقع هيبقى أدق لو سجّلت الأيام الأخيرة.")

        defaults = m.default_leftovers(d)
        with st.expander("الفاضل من أمس (لو ينفع يتسخن)"):
            leftovers = {}
            for dish in r.active_dishes():
                leftovers[dish["name"]] = st.number_input(dish["name"], min_value=0, step=1,
                                                          value=int(defaults.get(dish["name"], 0)), key=f"lo_{d}_{dish['name']}")

    plan = m.predict(d, safety, events={names[n] for n in chosen}, weather=weather, leftovers=leftovers)
    with right:
        price = {x["name"]: x.get("price") or 0 for x in r.dishes}
        c1, c2, c3 = st.columns(3)
        c1.metric("إجمالي التحضير", f"{int(plan['حضّر'].sum()):,}")
        c2.metric("متوقع يتباع", f"{int(plan['متوقع يتباع'].sum()):,}")
        money = sum(row["متوقع يتباع"] * price.get(row["الأكلة"], 0) for _, row in plan.iterrows())
        if money:
            c3.metric("إيراد متوقع (جنيه)", f"{money:,.0f}")
        show = plan.assign(**{"المدى": plan["من"].astype(str) + "–" + plan["إلى"].astype(str)})
        st.dataframe(show[["الأكلة", "متوقع يتباع", "المدى", "فاضل من أمس", "حضّر", "note"]], hide_index=True,
                     width="stretch", height=min(35 * (len(show) + 1) + 3, 640),
                     column_config={"حضّر": st.column_config.NumberColumn("حضّر ✔", help="الكمية اللي تتحضر"),
                                    "note": st.column_config.TextColumn("ملاحظة")})
        st.download_button("تحميل الإيصال (food_receipt.txt)", receipt_text(r.name, d, plan),
                           f"food_receipt_{d}.txt", type="primary")
        st.markdown("**الأسبوع الجاي — إجمالي الأطباق (عشان المشتريات)**")
        week = m.week_ahead(date.today(), safety)
        week["label"] = [f"{row['اليوم']} {row['date']:%d/%m}" for _, row in week.iterrows()]
        week["نوع اليوم"] = ["ويك إند / مناسبة" if (row["date"].weekday() in r.weekend or row["مناسبات"]) else "يوم عادي"
                             for _, row in week.iterrows()]
        x = alt.X("label:N", sort=None, title=None,
                  axis=alt.Axis(labelAngle=0, labelLimit=200, labelFontSize=12, labelPadding=8))
        base = alt.Chart(week)
        bars = base.mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=46).encode(
            x=x, y=alt.Y("إجمالي:Q", title=None, axis=alt.Axis(grid=True, gridOpacity=0.25, labelFontSize=11),
                         scale=alt.Scale(domain=[0, max(10, int(week["إجمالي"].max() * 1.15))], nice=True)),
            color=alt.Color("نوع اليوم:N", scale=alt.Scale(domain=["يوم عادي", "ويك إند / مناسبة"], range=["#2c6a43", "#c8871a"]),
                            legend=None),
            tooltip=[alt.Tooltip("label:N", title="اليوم"), alt.Tooltip("إجمالي:Q", title="إجمالي الأطباق"),
                     alt.Tooltip("مناسبات:N", title="مناسبات")])
        labels = base.mark_text(dy=-9, fontSize=13, fontWeight="bold", color="#1b241e").encode(x=x, y="إجمالي:Q", text="إجمالي:Q")
        st.altair_chart((bars + labels).properties(height=260).configure_view(strokeWidth=0), width="stretch")
        st.caption("🟩 يوم عادي · 🟧 ويك إند أو مناسبة (بيتباع فيه أكتر)")
        special = week[week["مناسبات"] != ""]
        if len(special):
            st.caption(" · ".join(f"{row['اليوم']}: {row['مناسبات']}" for _, row in special.iterrows()))

# ---------- data
with tab_data:
    bt = m.backtest
    cols = st.columns(4)
    cols[0].metric("يوم مسجّل", f"{m.n_days:,}")
    cols[1].metric("أكلة", len(r.dishes))
    cols[2].metric("الفترة", f"{round((m.last - m.first).days / 30.4)} شهر", help=f"من {m.first} لحد {m.last}")
    if bt:
        cols[3].metric("دقة التوقع (آخر ٦٠ يوم)", f"{bt['accuracy']:.0%}")
    st.caption(f"البيانات من {m.first} لحد {m.last}")

    a, b = st.columns(2, gap="large")
    with a:
        st.subheader("المطعم يدخّل بياناته إزاي؟")
        st.markdown("""
1. كل اللي محتاجينه **٣ حاجات بس**: التاريخ، اسم الأكلة، الكمية اللي اتباعت.
2. اليوم، الويك إند، الصيف/الشتاء، الدراسة، رمضان والأعياد — **التطبيق بيحسبهم لوحده من التاريخ**.
3. الأكلات بتتاخد من الملف نفسه، فكل مطعم بأكلاته هو.
""")
        st.caption("شكل ١: كل صف = أكلة في يوم")
        st.dataframe(pd.DataFrame({"التاريخ": ["2025-03-01", "2025-03-01"], "الأكلة": ["كشري", "طعمية"],
                                   "الكمية المباعة": [63, 58], "الكمية المحضرة (اختياري)": [70, 60]}), hide_index=True)
        st.caption("شكل ٢: كل صف = يوم، وكل أكلة عمود")
        st.dataframe(pd.DataFrame({"التاريخ": ["2025-03-01", "2025-03-02"], "كشري": [63, 55], "طعمية": [58, 49],
                                   "فول": [61, 52]}), hide_index=True)
    with b:
        if bt:
            st.subheader(f"لو كنت مشيت بالتوقع آخر {bt['days']} يوم")
            st.caption(f"النموذج اتدرّب على اللي قبلهم بس (مستوى الأمان: {SAFETY[bt['safety']]['label']}).")
            x1, x2, x3 = st.columns(3)
            x1.metric("هدر بالتوقع", f"{bt['model_waste']:,}", help="أطباق اتحضرت وما اتباعتش")
            x2.metric("نقص بالتوقع", f"{bt['model_short']:,}", help="أطباق كانت هتتطلب ومش موجودة")
            if bt["real_waste"] is not None:
                x3.metric("الهدر الفعلي", f"{bt['real_waste']:,}")
        st.subheader("الأكلات")
        rows = []
        for dish in r.dishes:
            s = r.sales[r.sales["dish"] == dish["name"]]
            wk = s["date"].map(lambda x: x.weekday() in r.weekend)
            lift = (s[wk]["sold"].mean() / s[~wk]["sold"].mean() - 1) if wk.any() and (~wk).any() else None
            acc = bt["per_dish"]["accuracy"].get(dish["name"]) if bt else None
            rows.append({"الأكلة": dish["name"], "السعر": dish.get("price"), "متوسط يومي": round(s["sold"].mean(), 1) if len(s) else None,
                         "زيادة الويك إند": f"{lift:+.0%}" if lift is not None else "—",
                         "دقة التوقع": acc, "أيام": len(s)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"دقة التوقع": st.column_config.ProgressColumn("دقة التوقع", min_value=0, max_value=1, format="percent")})
    st.download_button("تصدير البيانات Excel (بكل الأعمدة المحسوبة)", r.to_excel_bytes(), f"{r.name} - بيانات.xlsx")

# ---------- log a day
with tab_log:
    a, b = st.columns([2, 1], gap="large")
    with a:
        st.subheader("سجّل مبيعات يوم")
        st.caption("آخر اليوم اكتب اللي اتباع فعلاً. كل يوم بتسجّله التوقع بيتعلّم منه.")
        ld = st.date_input("التاريخ", date.today(), key="log_date", format="YYYY-MM-DD")
        rec = m.predict(ld, st.session_state.safety).set_index("الأكلة")["حضّر"].to_dict()
        existing = r.sales[r.sales["date"] == ld].set_index("dish")
        def _old(col, dish):
            v = existing[col].get(dish) if len(existing) and col in existing else None
            return None if v is None or pd.isna(v) else v

        table = pd.DataFrame({
            "الأكلة": [x["name"] for x in r.active_dishes()],
            "اتباع": [_old("sold", x["name"]) for x in r.active_dishes()],
            "اتحضّر": [_old("prepared", x["name"]) if _old("prepared", x["name"]) is not None else rec.get(x["name"])
                       for x in r.active_dishes()],
        })
        edited = st.data_editor(table, hide_index=True, disabled=["الأكلة"], width="stretch", key=f"log_{ld}",
                                column_config={"اتباع": st.column_config.NumberColumn(min_value=0, step=1),
                                               "اتحضّر": st.column_config.NumberColumn(min_value=0, step=1)})
        lw = st.selectbox("الطقس", r.weather_cats, key="log_w",
                          index=r.weather_cats.index(r.weather_on(ld)) if r.weather_on(ld) in r.weather_cats else 0) if r.weather_cats else None
        lev = st.multiselect("مناسبات اليوم ده", [e["name"] for e in r.events],
                             default=[e["name"] for e in r.events if e["key"] in r.active_events(ld)], key=f"log_ev_{ld}")
        if st.button("حفظ اليوم", type="primary"):
            sold = {row["الأكلة"]: row["اتباع"] for _, row in edited.iterrows() if pd.notna(row["اتباع"])}
            prep = {row["الأكلة"]: row["اتحضّر"] for _, row in edited.iterrows() if pd.notna(row["اتحضّر"])}
            try:
                r.log_day(ld, sold, prep, lw, {e["key"] for e in r.events if e["name"] in lev})
                retrain()
                st.success("اتسجّل والتوقع اتحدّث. متنساش تنزّل نسخة Excel محدثة من «بيانات المطعم».")
            except ValueError as e:
                st.warning(str(e))
    with b:
        st.subheader("أكلة جديدة في المنيو")
        st.caption("مالهاش تاريخ؟ اكتب متوسط تقريبي — التطبيق هيظبطه حسب اليوم (ويك إند، رمضان…).")
        with st.form("new_dish", clear_on_submit=True):
            nn = st.text_input("اسم الأكلة")
            ne = st.number_input("بيتباع منها في اليوم تقريباً", min_value=0.0, step=1.0)
            npr = st.number_input("السعر (اختياري)", min_value=0.0, step=1.0)
            if st.form_submit_button("إضافة"):
                try:
                    if not nn or ne <= 0:
                        raise ValueError("اكتب اسم الأكلة والمتوسط")
                    r.add_dish(nn.strip(), ne, npr or None)
                    retrain()
                    st.success("اتضافت")
                except ValueError as e:
                    st.warning(str(e))

# ---------- settings
with tab_settings:
    a, b = st.columns(2, gap="large")
    with a:
        st.subheader("المطعم")
        new_name = st.text_input("الاسم", r.name)
        wk = st.multiselect("أيام الويك إند عندك", list(range(7)), default=r.weekend, format_func=lambda i: DAY_NAMES[i])
        st.markdown("**مواعيد الدراسة (شهر-يوم)**")
        s1, s2, s3, s4 = st.columns(4)
        sc = {"start": s1.text_input("بداية السنة", r.school["start"]), "end": s2.text_input("نهاية السنة", r.school["end"]),
              "break_start": s3.text_input("بداية نص السنة", r.school["break_start"]),
              "break_end": s4.text_input("نهاية نص السنة", r.school["break_end"])}
        active = st.multiselect("أكلات المنيو الحالي", [x["name"] for x in r.dishes],
                                default=[x["name"] for x in r.active_dishes()])
        if st.button("حفظ وإعادة التدريب", type="primary"):
            import re
            if not all(re.fullmatch(r"\d{2}-\d{2}", v) for v in sc.values()):
                st.warning("اكتب المواعيد بالشكل 09-21")
            elif not wk or len(wk) == 7:
                st.warning("اختار يوم ويك إند واحد على الأقل")
            else:
                r.name, r.weekend, r.school = new_name or r.name, sorted(wk), sc
                for x in r.dishes:
                    x["active"] = x["name"] in active
                retrain()
                st.rerun()
    with b:
        st.subheader("المناسبات اللي التطبيق بيراعيها")
        st.dataframe(pd.DataFrame([{"المناسبة": e["name"], "المصدر": ("من ملفك، والأيام الجاية من التقويم" if e.get("match") else "من ملفك — علّمها بإيدك في يومها") if e["file"] else "التقويم المدمج"} for e in r.events]),
                     hide_index=True, width="stretch")
        y = date.today().year
        rows = []
        for yy in (y, y + 1):
            if yy in ISLAMIC:
                row = ISLAMIC[yy]
                rows += [(f"رمضان {yy}", f"{yy}-{row[0]}"), (f"عيد الفطر {yy}", f"{yy}-{row[1]}"), (f"عيد الأضحى {yy}", f"{yy}-{row[2]}")]
            rows.append((f"شم النسيم {yy}", str(orthodox_easter(yy) + timedelta(days=1))))
        st.markdown("**التقويم المدمج (مصر)**")
        st.dataframe(pd.DataFrame(sorted(rows, key=lambda t: t[1]), columns=["المناسبة", "التاريخ"]), hide_index=True, width="stretch")
        st.caption("مواعيد رمضان والأعياد تقريبية (±يوم حسب الرؤية). لو اختلفت، علّم المناسبة بإيدك.")

st.markdown(f'<p class="credit">{ui_style.PHOTO_CREDIT}</p>', unsafe_allow_html=True)
