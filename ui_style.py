"""Look & feel: food photo background, dark overlay, and light cards so every text stays readable."""
from __future__ import annotations

import base64
from pathlib import Path

# Free photo under the Unsplash License — Charles-Albert Clarysse
# https://unsplash.com/photos/a-delicious-spread-of-food-ready-for-eating--5B_sfWV2TE
REMOTE_BG = ("https://images.unsplash.com/photo-1748540459503-19efc015143b"
             "?fm=jpg&q=70&w=2400&auto=format&fit=crop")
LOCAL_BG = Path(__file__).parent / "assets" / "background.jpg"   # put your own photo here to replace it
PHOTO_CREDIT = ('صورة الخلفية: <a href="https://unsplash.com/photos/a-delicious-spread-of-food-ready-for-eating--5B_sfWV2TE" '
                'target="_blank">Charles-Albert Clarysse / Unsplash</a>')


def background_url() -> str:
    if LOCAL_BG.exists():
        return "data:image/jpeg;base64," + base64.b64encode(LOCAL_BG.read_bytes()).decode()
    return REMOTE_BG


def css() -> str:
    bg = background_url()
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Reem+Kufi:wght@600;700&display=swap');
:root {{
  --accent:#2c6a43; --accent-soft:#e1efe4; --spice:#c8871a; --spice-soft:#fbeed3;
  --ink:#1b241e; --muted:#5d6b61; --card:rgba(252,251,247,0.97); --tile:#f3f1ea; --line:rgba(27,36,30,0.09);
}}

/* ---------- background: photo + dark overlay (text never sits directly on the photo) ---------- */
.stApp {{
  background-color:#17211b;
  background-image:
    linear-gradient(180deg, rgba(12,18,14,0.62) 0%, rgba(12,18,14,0.80) 38%, rgba(12,18,14,0.90) 100%),
    url("{bg}");
  background-size:cover; background-position:center; background-attachment:fixed;
}}
[data-testid="stHeader"] {{background:transparent;}}
[data-testid="stHeader"] * {{color:#f4f1e8 !important;}}

/* ---------- RTL + fonts ---------- */
[data-testid="stMain"], [data-testid="stSidebar"] {{direction:rtl; text-align:right;}}
[data-testid="stMain"] *, [data-testid="stSidebar"] * {{font-family:'IBM Plex Sans Arabic', 'Segoe UI', Tahoma, sans-serif;}}
[data-testid="stIconMaterial"], span[class*="material"] {{font-family:'Material Symbols Rounded' !important;}}

/* ---------- hero (white text on the darkened photo) ---------- */
[data-testid="stMainBlockContainer"] {{max-width:1320px; padding-top:2.2rem;}}
.hero {{color:#fff; padding:6px 4px 22px; text-shadow:0 2px 14px rgba(0,0,0,0.55);}}
.hero .eyebrow {{display:inline-block; font-size:0.85rem; font-weight:600; letter-spacing:.03em;
  background:rgba(200,135,26,0.92); color:#fff; padding:3px 12px; border-radius:999px; text-shadow:none;}}
.hero h1 {{font-family:'Reem Kufi','IBM Plex Sans Arabic',sans-serif !important; font-size:2.9rem; line-height:1.15;
  margin:12px 0 6px; padding:0; color:#fff;}}
.hero p {{margin:0; font-size:1.08rem; color:rgba(255,255,255,0.88);}}
.hero .pills {{display:flex; flex-wrap:wrap; gap:8px; margin-top:16px;}}
.hero .pill {{background:rgba(255,255,255,0.14); border:1px solid rgba(255,255,255,0.28); color:#fff;
  padding:5px 14px; border-radius:999px; font-size:0.92rem; text-shadow:none; backdrop-filter:blur(6px);}}
.hero .pill b {{font-weight:700;}}

/* ---------- main card: everything inside the tabs sits on a light, almost opaque surface ---------- */
[data-testid="stTabs"] {{background:var(--card); border-radius:22px; padding:10px 30px 30px;
  box-shadow:0 24px 70px rgba(0,0,0,0.40); border:1px solid rgba(255,255,255,0.5);}}
[data-testid="stTab"] p {{font-size:1.05rem; font-weight:600;}}
[data-testid="stTab"][aria-selected="true"] p {{color:var(--accent);}}
[data-testid="stTabs"] h2, [data-testid="stTabs"] h3 {{color:var(--ink);}}

/* metric tiles */
[data-testid="stMetric"] {{background:var(--tile); border:1px solid var(--line); border-radius:16px; padding:14px 18px;}}
[data-testid="stMetricValue"] {{color:var(--accent); font-weight:700; font-size:clamp(1.45rem, 2.1vw, 2.05rem);}}
[data-testid="stMetricValue"] * {{overflow:visible !important; text-overflow:clip !important; white-space:nowrap;}}
[data-testid="stMetricLabel"] p {{color:var(--muted); font-weight:600;}}

/* buttons */
[data-testid="stBaseButton-primary"] {{background:var(--accent); border-color:var(--accent); border-radius:12px; font-weight:600;}}
[data-testid="stBaseButton-secondary"] {{border-radius:12px;}}
[data-testid="stDataFrame"] {{border-radius:14px; overflow:hidden; border:1px solid var(--line);}}
[data-testid="stExpander"] details {{border-radius:14px; background:#fff;}}

/* ---------- sidebar: light panel ---------- */
[data-testid="stSidebar"] {{background:rgba(250,249,244,0.98); border-left:1px solid var(--line);}}
.brand {{font-family:'Reem Kufi','IBM Plex Sans Arabic',sans-serif !important; font-size:2.3rem; font-weight:700;
  color:var(--accent); margin:0; line-height:1.1;}}

/* chips used on the prep page */
.chip {{display:inline-block; padding:3px 13px; margin:0 0 6px 6px; border-radius:999px; background:var(--tile);
  border:1px solid var(--line); font-size:0.92rem; color:var(--ink);}}
.chip.hot {{background:var(--spice-soft); border-color:rgba(200,135,26,0.35);}}
.chip.on {{background:var(--accent-soft); border-color:rgba(44,106,67,0.3);}}

.credit {{color:rgba(255,255,255,0.65); font-size:0.8rem; margin-top:18px; text-align:center;}}
.credit a {{color:rgba(255,255,255,0.85);}}
</style>"""


def hero(name: str, stats: list[tuple[str, str]], subtitle: str) -> str:
    pills = "".join(f'<span class="pill"><b>{v}</b> {k}</span>' for k, v in stats)
    return (f'<div class="hero"><span class="eyebrow">قِدرة · مساعد التحضير اليومي</span>'
            f'<h1>{name}</h1><p>{subtitle}</p><div class="pills">{pills}</div></div>')
