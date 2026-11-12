"""Look and feel: red & white theme, readable type, interactive background."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

RED = "#C8102E"
RED_DARK = "#9E0B22"
RED_TINT = "#FFF1F3"
INK = "#1F1F24"
INK_SOFT = "#5A5C66"
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"

# Chart palette: validated categorical set led by brand red (dataviz validator, light mode).
# Fixed order, never cycled. Red = the hero series (time-of-use tariff).
CHART = {"tou": "#D0202E", "cap": "#2A78D6", "house": "#1BAF7A", "ev": "#EDA100", "bat": "#6250D6"}


def plotly_template() -> None:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, size=14, color=INK),
        title=dict(font=dict(family=FONT, size=16, color=INK)),
        paper_bgcolor="rgba(255,255,255,0)",
        plot_bgcolor="rgba(255,255,255,0)",
        colorway=list(CHART.values()),
        xaxis=dict(gridcolor="rgba(31,31,36,0.08)", zerolinecolor="rgba(31,31,36,0.25)", linecolor="rgba(31,31,36,0.2)"),
        yaxis=dict(gridcolor="rgba(31,31,36,0.08)", zerolinecolor="rgba(31,31,36,0.25)", linecolor="rgba(31,31,36,0.2)"),
        hoverlabel=dict(font=dict(family=FONT, size=13), bgcolor="white", bordercolor=RED),
        legend=dict(font=dict(size=13)),
    )
    pio.templates["flex"] = t
    pio.templates.default = "plotly_white+flex"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {{ --mx: 50vw; --my: 30vh; --red: {RED}; --red-dark: {RED_DARK}; --red-tint: {RED_TINT}; }}

html, body, .stApp, input, select, textarea, .stMarkdown, [data-testid="stMetric"] {{ font-family: {FONT}; }}
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"] {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp {{ background: #ffffff; color: {INK}; }}

/* ---------- Interactive background ---------- */
.stApp::before {{
  content: ""; position: fixed; inset: -20vmax; z-index: 0; pointer-events: none;
  background:
    radial-gradient(38vmax 38vmax at 12% 18%, rgba(200,16,46,0.10), transparent 60%),
    radial-gradient(34vmax 34vmax at 88% 12%, rgba(200,16,46,0.07), transparent 60%),
    radial-gradient(40vmax 40vmax at 75% 92%, rgba(200,16,46,0.08), transparent 60%);
  animation: drift 26s ease-in-out infinite alternate;
}}
.stApp::after {{
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(420px circle at var(--mx) var(--my), rgba(200,16,46,0.10), transparent 70%),
    radial-gradient(rgba(200,16,46,0.13) 1px, transparent 1.2px) 0 0 / 26px 26px;
  -webkit-mask-image: radial-gradient(700px circle at var(--mx) var(--my), #000 0%, rgba(0,0,0,0.35) 60%, rgba(0,0,0,0.25) 100%);
          mask-image: radial-gradient(700px circle at var(--mx) var(--my), #000 0%, rgba(0,0,0,0.35) 60%, rgba(0,0,0,0.25) 100%);
}}
@keyframes drift {{
  0%   {{ transform: translate3d(0,0,0) rotate(0deg); }}
  50%  {{ transform: translate3d(3vmax,-2vmax,0) rotate(6deg); }}
  100% {{ transform: translate3d(-2vmax,3vmax,0) rotate(-4deg); }}
}}
[data-testid="stAppViewContainer"] > .main, [data-testid="stMain"], section[data-testid="stSidebar"] {{ position: relative; z-index: 1; }}
[data-testid="stHeader"] {{ background: rgba(255,255,255,0.7); backdrop-filter: blur(6px); }}

/* ---------- Typography ---------- */
h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.01em; font-weight: 700; }}
p, li, label, .stMarkdown {{ line-height: 1.6; }}
[data-testid="stCaptionContainer"] {{ color: {INK_SOFT}; font-size: 0.92rem; }}

/* ---------- Hero ---------- */
.hero {{
  position: relative; overflow: hidden; border-radius: 22px; padding: 30px 34px 26px;
  background: linear-gradient(120deg, {RED} 0%, {RED_DARK} 100%); color: #fff;
  box-shadow: 0 18px 40px -18px rgba(158,11,34,0.55); margin-bottom: 18px;
}}
.hero::after {{
  content: ""; position: absolute; right: -80px; top: -80px; width: 320px; height: 320px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,0.22), transparent 65%);
  animation: pulse 7s ease-in-out infinite;
}}
@keyframes pulse {{ 0%,100% {{ transform: scale(1); opacity: .8 }} 50% {{ transform: scale(1.15); opacity: 1 }} }}
.hero h1 {{ color: #fff; font-size: 2.3rem; margin: 0 0 6px; font-weight: 800; }}
.hero p.lead {{ font-size: 1.12rem; max-width: 900px; margin: 0 0 18px; opacity: .95; }}
.steps {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; }}
.step {{ background: rgba(255,255,255,0.13); border: 1px solid rgba(255,255,255,0.28); border-radius: 14px;
        padding: 12px 14px; transition: transform .2s ease, background .2s ease; }}
.step:hover {{ transform: translateY(-3px); background: rgba(255,255,255,0.22); }}
.step b {{ display: block; font-size: 1.0rem; margin-bottom: 2px; }}
.step span {{ font-size: .92rem; opacity: .92; }}
.step .n {{ display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:50%;
           background:#fff; color:{RED}; font-weight:800; font-size:.85rem; margin-right:8px; }}
@media (max-width: 800px) {{ .steps {{ grid-template-columns: 1fr; }} .hero h1 {{ font-size: 1.8rem; }} }}

/* ---------- Summary banner ---------- */
.summary {{ background: #fff; border: 1px solid #F3C9D0; border-left: 6px solid {RED}; border-radius: 14px;
           padding: 16px 20px; font-size: 1.08rem; margin: 6px 0 16px; box-shadow: 0 6px 20px -14px rgba(31,31,36,.35); }}
.summary b {{ color: {RED_DARK}; }}

/* ---------- Section headers ---------- */
.section {{ display:flex; align-items:center; gap:12px; margin: 26px 0 6px; }}
.section .badge {{ background:{RED}; color:#fff; font-weight:800; border-radius:10px; min-width:34px; height:34px;
                   display:inline-flex; align-items:center; justify-content:center; font-size:1rem; }}
.section h3 {{ margin:0; font-size:1.35rem; }}
.section-sub {{ color:{INK_SOFT}; margin: 0 0 10px 46px; font-size: .98rem; }}

/* ---------- Metric cards ---------- */
[data-testid="stMetric"] {{
  background: #fff; border: 1px solid #F1D3D8; border-top: 4px solid {RED}; border-radius: 14px;
  padding: 14px 16px; box-shadow: 0 8px 24px -18px rgba(31,31,36,.45); transition: transform .2s, box-shadow .2s;
}}
[data-testid="stMetric"]:hover {{ transform: translateY(-3px); box-shadow: 0 14px 30px -16px rgba(200,16,46,.45); }}
[data-testid="stMetricLabel"] p {{ font-size: .95rem; color: {INK_SOFT}; font-weight: 600; }}
[data-testid="stMetricValue"] {{ font-size: 1.9rem; font-weight: 800; color: {INK}; }}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 8px; background: rgba(255,255,255,.85); padding: 6px; border-radius: 14px;
                                    border: 1px solid #F1D3D8; }}
.stTabs [data-baseweb="tab"] {{ height: 46px; padding: 0 20px; border-radius: 10px; font-weight: 600; font-size: 1rem; }}
.stTabs [data-baseweb="tab"]:hover {{ background: {RED_TINT}; }}
.stTabs [aria-selected="true"] {{ background: {RED}; color: #fff !important; }}
.stTabs [aria-selected="true"] p {{ color: #fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ---------- Cards around charts, tables, expanders ---------- */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stExpander"] {{
  background: rgba(255,255,255,0.92); border-radius: 14px; border: 1px solid #F1E1E4;
  box-shadow: 0 8px 24px -20px rgba(31,31,36,.5);
}}
[data-testid="stPlotlyChart"] {{ padding: 8px 10px; }}
[data-testid="stExpander"] summary {{ font-weight: 600; }}
[data-testid="stExpander"] summary:hover {{ color: {RED}; }}

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button {{ border-radius: 10px; font-weight: 600; border: 1.5px solid {RED};
  color: {RED}; background: #fff; transition: all .15s; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ background: {RED}; color: #fff; transform: translateY(-1px); }}
.stDownloadButton > button[kind="primary"] {{ background: {RED}; color: #fff; }}
.stDownloadButton > button[kind="primary"]:hover {{ background: {RED_DARK}; border-color: {RED_DARK}; }}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {{ background: linear-gradient(180deg, #FFF5F6 0%, #FFFFFF 70%); border-right: 1px solid #F3D5DA; }}
section[data-testid="stSidebar"] h2 {{ color: {RED_DARK}; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] {{ background: #fff; }}

/* ---------- Glossary chips ---------- */
.gloss {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(260px,1fr)); gap:10px; }}
.gloss div {{ background:#fff; border:1px solid #F1D3D8; border-radius:12px; padding:10px 12px; font-size:.95rem; }}
.gloss b {{ color:{RED_DARK}; }}

@media (prefers-reduced-motion: reduce) {{
  .stApp::before, .hero::after {{ animation: none; }}
  .step, [data-testid="stMetric"], .stButton > button {{ transition: none; }}
}}
</style>
"""

# Cursor-following glow: updates CSS variables on the parent document. If the
# component iframe cannot reach the parent (browser policy), the background
# simply stays static — nothing breaks.
JS = """
<script>
(function () {
  try {
    const doc = window.parent.document;
    if (doc.__flexBgBound) return;
    doc.__flexBgBound = true;
    const root = doc.documentElement;
    let raf = null, x = 0, y = 0;
    doc.addEventListener('mousemove', function (e) {
      x = e.clientX; y = e.clientY;
      if (!raf) raf = window.parent.requestAnimationFrame(function () {
        root.style.setProperty('--mx', x + 'px');
        root.style.setProperty('--my', y + 'px');
        raf = null;
      });
    }, { passive: true });
  } catch (e) { /* static background fallback */ }
})();
</script>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    components.html(JS, height=0)
    plotly_template()


def hero() -> None:
    st.markdown(
        """
<div class="hero">
  <h1>⚡ Home energy-saving explorer</h1>
  <p class="lead">How much could a British household save by using electricity at smarter times,
  and is the equipment worth buying? Real public data from Ofgem and Elexon, with every number sourced.</p>
  <div class="steps">
    <div class="step"><span class="n">1</span><b style="display:inline">Set up your home</b><br>
      <span>Use the sidebar to change usage, add an electric car or a home battery.</span></div>
    <div class="step"><span class="n">2</span><b style="display:inline">Compare tariffs</b><br>
      <span>Fixed-price cap vs. a tariff whose price changes every half-hour.</span></div>
    <div class="step"><span class="n">3</span><b style="display:inline">Check the payback</b><br>
      <span>See whether savings cover the cost of the kit, and how fast.</span></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def section(num: str, title: str, sub: str = "") -> None:
    st.markdown(f'<div class="section"><span class="badge">{num}</span><h3>{title}</h3></div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<p class="section-sub">{sub}</p>', unsafe_allow_html=True)


def summary(html: str) -> None:
    st.markdown(f'<div class="summary">{html}</div>', unsafe_allow_html=True)


GLOSSARY = {
    "Price cap": "The maximum Ofgem lets suppliers charge per unit of electricity and per day. Same price at every hour.",
    "Time-of-use (ToU) tariff": "A tariff whose price changes during the day: cheap when demand is low or wind is high, dear at teatime.",
    "Wholesale price": "What suppliers pay for electricity on the market, every half-hour. Here from Elexon.",
    "Standing charge": "A fixed daily fee you pay regardless of how much you use.",
    "Smart charging": "Letting the car charger pick the cheapest hours overnight instead of charging the moment you plug in.",
    "Payback": "How many years until the money saved equals what you paid for the equipment.",
    "Net present value (NPV)": "Total lifetime savings in today's money minus the upfront cost. Above zero means worth it.",
    "kWh (unit)": "A kilowatt-hour: the 'unit' on your bill. A kettle boil uses about 0.1 kWh.",
}


def glossary() -> None:
    items = "".join(f"<div><b>{k}</b><br>{v}</div>" for k, v in GLOSSARY.items())
    st.markdown(f'<div class="gloss">{items}</div>', unsafe_allow_html=True)
