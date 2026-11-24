"""
app.py — Wearable Health Insights Dashboard (v2)

An interactive biomedical-signal dashboard built on personal Apple Watch data.

    Python  -> data engineering (streaming XML parse, time-weighted aggregation)
    Plotly  -> interactive charts
    MATLAB  -> independent statistical reproduction (correlation_analysis.m)
    SciPy   -> live statistics + the PPG signal-processing simulator

This is a WELLNESS / engineering tool, not a diagnostic one. It surfaces
patterns in one person's data; it does not interpret medical conditions.

Run with:  streamlit run app.py
Author:    Nabeel Abdel
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy import signal, stats

# =============================================================================
# 0. Page setup & design tokens
# =============================================================================
st.set_page_config(
    page_title="Wearable Health Insights",
    page_icon="❤️",
    layout="wide",
    initial_sidebar_state="auto",
)

# Colour system - dark "instrument panel" theme. Series colours are the dark-mode
# steps of a colour-blind-validated categorical palette (fixed order, never
# cycled); the zone ramp is a single-hue sequential scale because zones are
# *ordered* intensity, not separate categories.
C = {
    "blue": "#3987e5", "orange": "#ff7a45", "aqua": "#2fc48f", "yellow": "#f0b429",
    "magenta": "#e86aa0", "violet": "#9c8cf2", "red": "#f06a6a",
    "ink": "#F2F4F8", "ink2": "#9AA3B5", "ink3": "#5F6878",
    "grid": "#1E2636", "surface": "#111723", "surface2": "#0D1320", "bg": "#080B12",
    "line": "#1F2838",
}
ZONE_RAMP = ["#1C3A66", "#235291", "#2E6FC0", "#3987e5", "#7FB4F5"]
ZONE_LABELS = ["Zone 1 · Very light", "Zone 2 · Light", "Zone 3 · Moderate",
               "Zone 4 · Hard", "Zone 5 · Maximum"]
ZONE_COLS = ["zone1_min", "zone2_min", "zone3_min", "zone4_min", "zone5_min"]
MONO = "'JetBrains Mono', 'SF Mono', ui-monospace, Menlo, Consolas, monospace"

# -----------------------------------------------------------------------------
# Published US reference data (for the "Population context" tab).
# These are transcribed from the cited tables - they are NOT derived from my data.
# Each list holds the 5th, 10th, 25th, 50th, 75th, 90th and 95th percentiles.
# -----------------------------------------------------------------------------
REF_PCTS = [5, 10, 25, 50, 75, 90, 95]

# VO2max, mL O2/kg/min, measured directly by cardiopulmonary exercise testing on
# a treadmill. Kaminsky et al., Mayo Clin Proc 2015 (FRIEND registry, 7,783 tests,
# US adults 20-79 without cardiovascular disease), Table 3.
VO2_REF = {
    "Male": {(20, 29): [29.0, 32.1, 40.1, 48.0, 55.2, 61.8, 66.3], (30, 39): [27.2, 30.2, 35.9, 42.4, 49.2, 56.5, 59.8],
             (40, 49): [24.2, 26.8, 31.9, 37.8, 45.0, 52.1, 55.6], (50, 59): [20.9, 22.8, 27.1, 32.6, 39.7, 45.6, 50.7],
             (60, 69): [17.4, 19.8, 23.7, 28.2, 34.5, 40.3, 43.0], (70, 79): [16.3, 17.1, 20.4, 24.4, 30.4, 36.6, 39.7]},
    "Female": {(20, 29): [21.7, 23.9, 30.5, 37.6, 44.7, 51.3, 56.0], (30, 39): [19.0, 20.9, 25.3, 30.2, 36.1, 41.4, 45.8],
               (40, 49): [17.0, 18.8, 22.1, 26.7, 32.4, 38.4, 41.7], (50, 59): [16.0, 17.3, 19.9, 23.4, 27.6, 32.0, 35.9],
               (60, 69): [13.4, 14.6, 17.2, 20.0, 23.8, 27.0, 29.4], (70, 79): [13.1, 13.6, 15.6, 18.3, 20.8, 23.1, 24.1]},
}

# Resting pulse rate, beats/min, counted after ~4 minutes seated rest.
# Ostchega et al., National Health Statistics Reports no. 41, 2011
# (NHANES 1999-2008), Tables 2 and 3.
RHR_REF = {
    "Male": {(16, 19): [52, 56, 61, 69, 78, 87, 92], (20, 39): [52, 55, 61, 69, 76, 84, 89],
             (40, 59): [52, 55, 61, 68, 77, 85, 90], (60, 79): [50, 54, 60, 67, 75, 84, 91],
             (80, 120): [51, 54, 61, 68, 78, 86, 94]},
    "Female": {(16, 19): [58, 62, 69, 77, 85, 94, 99], (20, 39): [57, 60, 66, 74, 82, 89, 95],
               (40, 59): [56, 59, 64, 71, 79, 86, 92], (60, 79): [56, 59, 64, 70, 78, 86, 92],
               (80, 120): [56, 59, 64, 71, 77, 85, 93]},
}

# Steps per day: one overall figure for US adults aged 20+ (not split by age or sex).
# Tudor-Locke et al., Int J Behav Nutr Phys Act 2010 (NHANES 2005-2006, hip-worn
# ActiGraph accelerometer, steps censored to a pedometer-like scale).
STEPS_REF_US_ADULTS = 6564

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

    .stApp {{
        background:
          radial-gradient(1200px 500px at 15% -10%, rgba(57,135,229,.16), transparent 60%),
          radial-gradient(900px 400px at 95% 0%, rgba(47,196,143,.10), transparent 55%),
          {C["bg"]};
        color: {C["ink"]};
    }}
    .stApp::before {{
        content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
        background-image: radial-gradient(rgba(255,255,255,.045) 1px, transparent 1px);
        background-size: 26px 26px;
    }}
    section[data-testid="stSidebar"] {{ background: {C["surface2"]}; border-right: 1px solid {C["line"]}; }}
    header[data-testid="stHeader"] {{ background: transparent; }}
    .block-container {{ padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1280px; }}
    h1, h2, h3, p, li, div {{ font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}

    .hero {{ display: flex; align-items: center; gap: 1.5rem; }}
    .hero-text {{ flex: 1 1 auto; min-width: 0; }}
    .hero-title {{ font-size: 2.4rem !important; font-weight: 800; letter-spacing: -0.03em; line-height: 1.08;
                   margin: 0 0 .35rem 0;
                   background: linear-gradient(92deg, #FFFFFF 0%, #BFD6F7 55%, {C["aqua"]} 100%);
                   -webkit-background-clip: text; background-clip: text; color: transparent; }}
    .hero-sub   {{ color: {C["ink2"]}; font-size: 1rem !important; max-width: 760px; line-height: 1.55; margin: 0; }}
    .telemetry {{ font-family: {MONO}; font-size: .74rem; color: {C["aqua"]}; letter-spacing: .04em;
                  margin: .8rem 0 .2rem 0; }}
    .telemetry .dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: {C["aqua"]};
                       box-shadow: 0 0 10px {C["aqua"]}; margin-right: .45rem; animation: blink 1.6s infinite; }}
    @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .25; }} }}
    .pills {{ margin: .6rem 0 .4rem 0; display: flex; flex-wrap: wrap; gap: .4rem; }}
    .pill {{ font-family: {MONO}; font-size: .7rem; font-weight: 600; padding: .28rem .65rem; border-radius: 6px;
             background: rgba(255,255,255,.03); border: 1px solid {C["line"]}; color: {C["ink2"]}; }}
    .pill.accent {{ background: rgba(57,135,229,.18); border-color: rgba(57,135,229,.6); color: #CFE2FB; }}
    .pill.planned {{ border-style: dashed; }}

    /* animated pulse strip in the hero */
    .pulse-wrap {{ flex: 0 0 300px; }}
    .pulse-wrap svg {{ width: 100%; height: auto; display: block; }}
    .pulse-line {{ fill: none; stroke: {C["aqua"]}; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
                   stroke-dasharray: 900; stroke-dashoffset: 900; animation: draw 4s linear infinite;
                   filter: drop-shadow(0 0 6px rgba(47,196,143,.8)); }}
    .pulse-ghost {{ fill: none; stroke: rgba(47,196,143,.18); stroke-width: 2.2; }}
    @keyframes draw {{ 0% {{ stroke-dashoffset: 900; }} 80% {{ stroke-dashoffset: 0; }} 100% {{ stroke-dashoffset: 0; }} }}

    .kpi {{ background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.012)), {C["surface"]};
            border: 1px solid {C["line"]}; border-radius: 14px;
            padding: .95rem 1.1rem .85rem 1.1rem; box-shadow: 0 8px 24px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.04);
            min-height: 150px; display: flex; flex-direction: column; }}
    .kpi-label {{ font-family: {MONO}; font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
                  color: {C["ink2"]}; margin-bottom: .3rem; }}
    .kpi-value {{ font-size: 1.9rem; font-weight: 800; color: {C["ink"]}; letter-spacing: -0.02em; line-height: 1.1;
                  white-space: nowrap; }}
    .kpi-unit  {{ font-size: .9rem; font-weight: 600; color: {C["ink2"]}; margin-left: .2rem; }}
    .kpi-sub   {{ font-size: .76rem; color: {C["ink2"]}; margin-top: .35rem; }}
    .kpi-sub b {{ color: {C["ink"]}; }}
    .kpi-spark {{ margin-top: auto; padding-top: .45rem; display: flex; justify-content: flex-end; }}

    .section {{ display: flex; align-items: baseline; gap: .7rem; margin: 1.6rem 0 .6rem 0; }}
    .section-bar {{ width: 4px; height: 20px; border-radius: 2px; background: {C["blue"]}; align-self: center;
                    box-shadow: 0 0 10px rgba(57,135,229,.7); }}
    .section h3 {{ font-size: 1.1rem; font-weight: 700; color: {C["ink"]}; margin: 0; white-space: nowrap; }}
    .section span {{ font-family: {MONO}; font-size: .76rem; color: {C["ink2"]}; }}

    .note {{ background: {C["surface"]}; border: 1px solid {C["line"]}; border-left: 3px solid {C["blue"]};
             border-radius: 12px; padding: .9rem 1.1rem; line-height: 1.55; font-size: .92rem; color: {C["ink"]}; }}
    .note.warn {{ border-left-color: {C["orange"]}; }}
    .note.good {{ border-left-color: {C["aqua"]}; }}
    .note h4 {{ margin: 0 0 .3rem 0; font-size: .95rem; color: {C["ink"]}; }}
    .note code {{ font-family: {MONO}; font-size: .8rem; color: #BFD6F7; background: rgba(57,135,229,.12);
                  padding: .05rem .3rem; border-radius: 4px; }}
    .eq {{ background: rgba(57,135,229,.10); border: 1px solid rgba(57,135,229,.25); border-radius: 8px;
           padding: .45rem .8rem; font-family: {MONO}; font-size: .84rem; color: #CFE2FB; display: inline-block; margin: .25rem 0; }}
    .footer {{ text-align: center; color: {C["ink3"]}; font-size: .76rem; font-family: {MONO}; margin-top: 2.5rem; }}

    div[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 14px !important; background: {C["surface"]};
        border: 1px solid {C["line"]} !important; box-shadow: 0 8px 24px rgba(0,0,0,.25); }}
    div[data-testid="stTab"] p {{ font-weight: 600; font-size: .92rem; }}
    .diagram svg {{ width: 100%; height: auto; display: block; }}

    /* ---- Phone / narrow screens only (laptop layout above is untouched) ---- */
    @media (max-width: 768px) {{
        .block-container {{ padding-top: 3rem; padding-left: 1rem; padding-right: 1rem; }}
        /* hero: stack the text above the pulse strip instead of side by side */
        .hero {{ flex-direction: column; align-items: stretch; gap: .9rem; }}
        .hero-title {{ font-size: 1.9rem !important; }}
        .hero-sub {{ font-size: .93rem !important; max-width: none; }}
        .pulse-wrap {{ flex: 0 0 auto; width: 100%; max-width: 340px; }}
        .telemetry {{ line-height: 1.7; }}
        /* section headers: let the title wrap and drop the subtitle to its own line */
        .section {{ flex-wrap: wrap; row-gap: .15rem; }}
        .section h3 {{ white-space: normal; flex: 1 1 0; min-width: 0; }}
        .section span {{ flex: 0 0 100%; }}
        .kpi {{ min-height: 0; }}
        .kpi-value {{ font-size: 1.7rem; }}
        /* sensor schematic: keep its labels readable, scroll sideways instead of shrinking */
        .diagram {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
        .diagram svg {{ min-width: 680px; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 1. Data loading
# =============================================================================
REQUIRED_COLS = {"avg_hr", "avg_hr_naive", "monitored_hours", "workout_minutes", "trimp_edwards", *ZONE_COLS}


@st.cache_data
def load_daily() -> pd.DataFrame:
    df = pd.read_csv("daily_summary.csv", parse_dates=["date"])
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            "daily_summary.csv is from the old pipeline (missing "
            f"{sorted(missing)}). Re-run: python build_daily_summary.py"
        )
    for optional in ("hrv_sdnn_ms", "vo2_max"):      # only in exports where the Watch recorded them
        if optional not in df.columns:
            df[optional] = np.nan
    return df


@st.cache_data
def load_hourly() -> pd.DataFrame | None:
    if not os.path.exists("hourly_hr.csv"):
        return None
    return pd.read_csv("hourly_hr.csv", parse_dates=["date"])


@st.cache_data
def load_sampling() -> pd.DataFrame | None:
    if not os.path.exists("sampling_profile.csv"):
        return None
    return pd.read_csv("sampling_profile.csv")


if not os.path.exists("daily_summary.csv"):
    st.error("`daily_summary.csv` not found. Build it with `python parse_health_data.py` "
             "then `python build_daily_summary.py`.")
    st.stop()

try:
    df_all = load_daily()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

hourly_all = load_hourly()
sampling = load_sampling()


# =============================================================================
# 2. Shared helpers
# =============================================================================
def fmt(value, spec, fallback="—"):
    return format(value, spec) if pd.notna(value) else fallback


def sparkline_svg(values: pd.Series, color: str, w: int = 110, h: int = 26) -> str:
    """Tiny inline SVG line for the KPI cards (no JS, no extra library)."""
    v = pd.Series(values).dropna().to_numpy(dtype=float)
    if len(v) < 2:
        return ""
    lo, hi = v.min(), v.max()
    span = (hi - lo) or 1.0
    xs = np.linspace(2, w - 2, len(v))
    ys = h - 3 - (v - lo) / span * (h - 6)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity=".9"/>'
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="2.6" fill="{color}"/></svg>')


def kpi(col, label, value, unit="", sub="", spark: pd.Series | None = None, color=C["blue"]):
    svg = sparkline_svg(spark, color) if spark is not None else ""
    spark_html = f'<div class="kpi-spark">{svg}</div>' if svg else ""
    col.markdown(
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>'
        f'<div class="kpi-sub">{sub}</div>{spark_html}</div>',
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str = ""):
    st.markdown(
        f'<div class="section"><div class="section-bar"></div><h3>{title}</h3>'
        f'<span>{subtitle}</span></div>', unsafe_allow_html=True)


def note(html: str, kind: str = ""):
    st.markdown(f'<div class="note {kind}">{html}</div>', unsafe_allow_html=True)


def pulse_svg() -> str:
    """Animated PPG-style waveform for the hero (pure SVG + CSS, no JS)."""
    w, h = 300, 90
    t = np.linspace(0, 3.0, 400)
    y = np.zeros_like(t)
    for tb in (0.35, 1.25, 2.15):
        y += np.exp(-((t - tb) / 0.09) ** 2) + 0.28 * np.exp(-((t - tb - 0.26) / 0.12) ** 2)
    xs = t / 3.0 * (w - 10) + 5
    ys = h - 14 - y / y.max() * (h - 30)
    d = "M " + " L ".join(f"{x:.1f},{yy:.1f}" for x, yy in zip(xs, ys))
    return (f'<div class="pulse-wrap"><svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<path class="pulse-ghost" d="{d}"/><path class="pulse-line" d="{d}"/>'
            f'<text x="6" y="{h-2}" font-family="{MONO}" font-size="8" fill="{C["ink3"]}">PPG · synthetic · 72 bpm</text>'
            f'</svg></div>')


def sensor_cross_section_svg() -> str:
    """Original schematic of a wrist-worn optical (PPG) heart-rate sensor."""
    g, b, o, ink, ink2, line = C["aqua"], C["blue"], C["orange"], C["ink"], C["ink2"], C["line"]
    return f"""
<div class="diagram"><svg viewBox="0 0 760 330" xmlns="http://www.w3.org/2000/svg" font-family="Inter, Helvetica, Arial, sans-serif">
  <defs>
    <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{g}" stop-opacity=".55"/><stop offset="1" stop-color="{g}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="skin" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3B2A2E"/><stop offset="1" stop-color="#2A1E24"/>
    </linearGradient>
    <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="{ink2}"/></marker>
  </defs>

  <!-- sensor module (underside of a generic wrist wearable) -->
  <rect x="150" y="18" width="330" height="62" rx="18" fill="#161D2B" stroke="{line}"/>
  <text x="315" y="36" text-anchor="middle" font-size="10" fill="{ink2}" letter-spacing="1.5">SENSOR MODULE · BACK OF WEARABLE</text>
  <rect x="205" y="48" width="26" height="18" rx="4" fill="{g}"/>
  <rect x="399" y="48" width="26" height="18" rx="4" fill="{g}"/>
  <rect x="268" y="46" width="42" height="22" rx="4" fill="#2A3447" stroke="{b}"/>
  <rect x="320" y="46" width="42" height="22" rx="4" fill="#2A3447" stroke="{b}"/>
  <text x="218" y="92" text-anchor="middle" font-size="10" fill="{g}">green LED · 525 nm</text>
  <text x="412" y="92" text-anchor="middle" font-size="10" fill="{g}">green LED · 525 nm</text>
  <text x="315" y="92" text-anchor="middle" font-size="10" fill="#9FC3F5">photodiodes</text>

  <!-- tissue -->
  <rect x="60" y="112" width="510" height="176" rx="6" fill="url(#skin)"/>
  <rect x="60" y="112" width="510" height="22" fill="#4A3338"/>
  <line x1="60" y1="190" x2="570" y2="190" stroke="#4A3338" stroke-dasharray="4 4"/>
  <text x="66" y="127" font-size="10" fill="{ink2}">epidermis</text>
  <text x="66" y="160" font-size="10" fill="{ink2}">dermis · capillary bed</text>
  <text x="66" y="215" font-size="10" fill="{ink2}">subcutaneous tissue</text>
  <!-- capillaries -->
  <g stroke="#C94A5A" stroke-width="1.2" opacity=".7">
    <path d="M110,140 q20,14 40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0" fill="none"/>
    <path d="M100,172 q20,-12 40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0 t40,0" fill="none"/>
  </g>
  <!-- artery -->
  <ellipse cx="315" cy="245" rx="190" ry="26" fill="#7A1F2E" stroke="#C94A5A" stroke-width="2"/>
  <ellipse cx="315" cy="245" rx="190" ry="18" fill="#B2283B" opacity=".9"/>
  <text x="315" y="249" text-anchor="middle" font-size="11" fill="#FFD9DE" font-weight="600">artery — blood volume rises with every systole</text>

  <!-- light paths -->
  <path d="M218,66 L170,175 Q315,215 460,175 L412,66 Z" fill="url(#beam)" opacity=".9"/>
  <path d="M218,66 Q253,270 289,66" fill="none" stroke="{g}" stroke-width="2" stroke-dasharray="5 4"/>
  <path d="M412,66 Q377,270 341,66" fill="none" stroke="{g}" stroke-width="2" stroke-dasharray="5 4"/>
  <text x="315" y="205" text-anchor="middle" font-size="10" fill="#CFF5E4">scattered light returns to the photodiodes (“banana” path)</text>

  <!-- AC / DC callouts -->
  <g font-size="10">
    <rect x="590" y="118" width="160" height="58" rx="8" fill="#111723" stroke="{line}"/>
    <text x="600" y="136" fill="{ink}" font-weight="600">DC component</text>
    <text x="600" y="151" fill="{ink2}">steady absorption by tissue,</text>
    <text x="600" y="164" fill="{ink2}">bone and venous blood</text>
    <rect x="590" y="188" width="160" height="72" rx="8" fill="#111723" stroke="{o}"/>
    <text x="600" y="206" fill="{ink}" font-weight="600">AC component · 1–2 % of DC</text>
    <text x="600" y="221" fill="{ink2}">extra absorption each beat as</text>
    <text x="600" y="234" fill="{ink2}">arterial volume (path length ℓ)</text>
    <text x="600" y="247" fill="{ink2}">increases → the pulse signal</text>
    <line x1="590" y1="224" x2="520" y2="238" stroke="{o}" marker-end="url(#arr)"/>
  </g>

  <!-- output waveform -->
  <g transform="translate(60,272)">
    <text x="0" y="42" font-size="10" fill="{ink2}">I = I₀·e^(−ε·c·ℓ)   →   photodiode current   →   band-pass 0.5–5 Hz   →   peak detection   →   HR, HRV</text>
  </g>
</svg></div>"""


def ref_row(table: dict, sex_key: str, age_years: int):
    """Look up the reference row for a sex and age. Returns (label, values) or None."""
    for (lo, hi), vals in table[sex_key].items():
        if lo <= age_years <= hi:
            return (f"{lo}+" if hi >= 120 else f"{lo}–{hi}"), vals
    return None


def ordinal(n: float) -> str:
    n = int(round(n))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def estimate_percentile(value: float, vals: list) -> str:
    """Place a value on a published percentile table by linear interpolation
    between the tabulated percentiles. Outside the table it is only bounded."""
    if pd.isna(value):
        return "—"
    if value < vals[0]:
        return "below the 5th percentile"
    if value > vals[-1]:
        return "above the 95th percentile"
    return f"about the {ordinal(np.interp(value, vals, REF_PCTS))} percentile"


def percentile_strip(vals: list, value: float, lo: float, hi: float, unit: str, color: str, name: str) -> go.Figure:
    """Horizontal reference strip: nested 5–95 / 10–90 / 25–75 bands, median tick,
    and my own value (marker) with the range of my values in the window (whisker)."""
    fig = go.Figure()
    bands = [(0, 6, "rgba(154,163,181,0.14)", "5th–95th"), (1, 5, "rgba(154,163,181,0.24)", "10th–90th"),
             (2, 4, "rgba(154,163,181,0.40)", "25th–75th")]
    for i, j, fill, label in bands:
        fig.add_trace(go.Bar(y=[""], x=[vals[j] - vals[i]], base=vals[i], orientation="h", width=0.62,
                             marker_color=fill, marker_line_width=0, name=f"Reference {label}",
                             hovertemplate=f"{label}: {vals[i]:g}–{vals[j]:g} {unit}<extra></extra>"))
    fig.add_shape(type="line", x0=vals[3], x1=vals[3], y0=-0.31, y1=0.31, line=dict(color="#E6EBF5", width=2))
    for p, v in zip(REF_PCTS, vals):
        fig.add_annotation(x=v, y=0.34, yanchor="bottom", text=f"{p}th<br><b>{v:g}</b>", showarrow=False,
                           font=dict(size=10, color=C["ink2"]))
    if pd.notna(lo) and pd.notna(hi) and hi > lo:
        fig.add_trace(go.Scatter(x=[lo, hi], y=["", ""], mode="lines", line=dict(color=color, width=3),
                                 name="My range in this window",
                                 hovertemplate="my range: " + f"{lo:.1f}–{hi:.1f} {unit}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[value], y=[""], mode="markers", name=name,
                             marker=dict(color=color, size=16, symbol="diamond", line=dict(color=C["surface"], width=2)),
                             hovertemplate=f"{name}: {value:.1f} {unit}<extra></extra>"))
    fig = base_layout(fig, 230, xtitle=unit)
    span = max(vals[-1], hi if pd.notna(hi) else value, value) - min(vals[0], lo if pd.notna(lo) else value, value)
    fig.update_layout(barmode="overlay", hovermode="closest", margin=dict(l=10, r=10, t=40, b=10))
    fig.update_xaxes(range=[min(vals[0], lo if pd.notna(lo) else value, value) - 0.06 * span,
                            max(vals[-1], hi if pd.notna(hi) else value, value) + 0.06 * span], showgrid=False)
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[-0.45, 0.8])
    return fig


def base_layout(fig: go.Figure, height=360, ytitle="", xtitle="", legend=True) -> go.Figure:
    """One consistent chart style: recessive grid, thin marks, legend on top."""
    fig.update_layout(
        height=height, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=30 if legend else 10, b=10),
        font=dict(family="Inter, -apple-system, Segoe UI, Helvetica, Arial", color=C["ink"], size=12),
        hovermode="x unified", hoverlabel=dict(bgcolor="#1A2232", bordercolor=C["line"], font_size=12,
                                                font_color=C["ink"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11)),
        showlegend=legend,
    )
    fig.update_xaxes(title=xtitle, showgrid=False, zeroline=False, linecolor=C["grid"],
                     tickfont=dict(color=C["ink2"]), title_font=dict(color=C["ink2"]))
    fig.update_yaxes(title=ytitle, gridcolor=C["grid"], zeroline=False, tickfont=dict(color=C["ink2"]),
                     title_font=dict(color=C["ink2"]))
    return fig


def show(fig: go.Figure):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# =============================================================================
# 3. Sidebar controls
# =============================================================================
with st.sidebar:
    st.markdown("### Controls")
    min_date, max_date = df_all["date"].min().date(), df_all["date"].max().date()
    date_range = st.date_input("Date range", value=(min_date, max_date),
                               min_value=min_date, max_value=max_date)
    age = st.number_input("Age (for HRmax estimate)", min_value=10, max_value=90, value=20, step=1,
                          help="HRmax ≈ 220 − age (Fox formula). Zones in the pipeline use 200 bpm.")
    hr_max_est = 220 - age
    sex = st.radio("Sex (for reference tables)", ["Male", "Female"], horizontal=True,
                   help="Published reference values are split by age and sex. Used only on the "
                        "Population context tab and the VO₂max chart.")
    hide_low = st.toggle("Hide low-coverage days (< 2 h monitored)", value=False,
                         help="Days where the watch was worn but recorded less than two hours of heart-rate "
                              "data. Days it was not worn at all have no heart-rate values to begin with.")
    st.markdown("---")
    st.markdown(
        f"""<div style="font-size:.82rem;color:{C['ink2']};line-height:1.5">
        <b style="color:{C['ink']}">Data source</b><br>Apple Watch export (PPG heart rate, HRV, VO₂max, steps, active energy),
        aggregated to day level. Raw per-second samples stay local; only aggregates are published.<br><br>
        <b style="color:{C['ink']}">HRmax</b>: {hr_max_est} bpm (estimate) &nbsp;·&nbsp;
        observed peak {fmt(df_all['max_hr'].max(), '.0f')} bpm</div>""",
        unsafe_allow_html=True)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = (pd.Timestamp(d) for d in date_range)
else:
    start, end = df_all["date"].min(), df_all["date"].max()

df = df_all[(df_all["date"] >= start) & (df_all["date"] <= end)].copy()
if hide_low:
    df = df[~df["low_coverage"]]
if df.empty:
    st.warning("No data in the selected range. Widen the filter.")
    st.stop()

hr_days = df.dropna(subset=["avg_hr"])

# Calendar-complete copy: one row per calendar day, NaN where there is no data.
# Line charts are drawn from this so they BREAK across days the watch was not
# worn, instead of drawing a misleading straight line through the gap.
cal = (df.set_index("date")
         .reindex(pd.date_range(df["date"].min(), df["date"].max(), freq="D"))
         .rename_axis("date").reset_index())
HAS_HRV = bool(df["hrv_sdnn_ms"].notna().sum() >= 3)
HAS_VO2 = bool(df["vo2_max"].notna().sum() >= 2)
n_no_hr = int(cal["avg_hr"].isna().sum())


def rolling_baseline(series: pd.Series, window: int = 7, min_periods: int = 3):
    """Rolling mean and SD on a calendar-indexed series (NaN on unworn days)."""
    return (series.rolling(window, min_periods=min_periods).mean(),
            series.rolling(window, min_periods=min_periods).std())


hourly = None
if hourly_all is not None:
    hourly = hourly_all[(hourly_all["date"] >= start) & (hourly_all["date"] <= end)]
    if hide_low:
        hourly = hourly[hourly["date"].isin(df["date"])]


# =============================================================================
# 4. Hero header + KPI row
# =============================================================================
st.markdown(
    '<div class="hero"><div class="hero-text">'
    '<p class="hero-title">Wearable Health Insights</p>'
    '<p class="hero-sub">A biomedical-signal dashboard built on my own Apple Watch data. It corrects for the '
    'sensor\'s adaptive sampling, breaks heart rate into physiological training zones, tracks HRV and resting-HR '
    'baselines, maps the circadian rhythm, audits signal quality, and reproduces the statistics independently in '
    'MATLAB. Trend tool, not a diagnostic one.</p>'
    '<div class="pills"><span class="pill accent">Python · pandas</span><span class="pill">Plotly</span>'
    '<span class="pill">SciPy signal processing</span><span class="pill">MATLAB · Statistics Toolbox</span>'
    '<span class="pill">Streamlit</span><span class="pill planned">Phase 2 · ESP32 + MAX30102 · SolidWorks</span></div>'
    '</div>' + pulse_svg() + '</div>',
    unsafe_allow_html=True)

period = f"{df['date'].min():%b %d} – {df['date'].max():%b %d, %Y}"
n_samples = int(df["hr_samples"].sum(skipna=True))
st.markdown(
    f'<div class="telemetry"><span class="dot"></span>WINDOW {df["date"].min():%Y-%m-%d} → {df["date"].max():%Y-%m-%d}'
    f' &nbsp;·&nbsp; {len(df)} DAYS &nbsp;·&nbsp; {len(hr_days)} WITH HR &nbsp;·&nbsp; {n_samples:,} PPG SAMPLES'
    f' &nbsp;·&nbsp; {fmt(df["monitored_hours"].sum(), ".0f")} H MONITORED &nbsp;·&nbsp; SOURCE: APPLE WATCH (PPG · ACCEL)</div>',
    unsafe_allow_html=True)

rest_recent = df["resting_hr"].dropna()
half = max(len(rest_recent) // 2, 1)
rest_delta = (rest_recent.iloc[half:].mean() - rest_recent.iloc[:half].mean()) if len(rest_recent) >= 8 else np.nan
hrv_vals, vo2_vals = df["hrv_sdnn_ms"].dropna(), df["vo2_max"].dropna()

k = st.columns(4)
kpi(k[0], "Heart rate", fmt(hr_days["avg_hr"].mean(), ".0f"), "bpm",
    f"time-weighted · naive mean <b>{fmt(hr_days['avg_hr_naive'].mean(), '.0f')}</b>",
    hr_days["avg_hr"], C["blue"])
kpi(k[1], "Resting HR", fmt(rest_recent.mean(), ".0f"), "bpm",
    f"2nd half vs 1st half of window: <b>{fmt(rest_delta, '+.1f')}</b>", rest_recent, C["aqua"])
kpi(k[2], "HRV · SDNN", fmt(hrv_vals.mean(), ".0f"), "ms",
    f"<b>{len(hrv_vals)}</b> days measured · range {fmt(hrv_vals.min(), '.0f')}–{fmt(hrv_vals.max(), '.0f')}"
    if HAS_HRV else "not recorded in this export", hrv_vals if HAS_HRV else None, C["violet"])
kpi(k[3], "VO₂max (est.)", fmt(vo2_vals.iloc[-1] if HAS_VO2 else np.nan, ".1f"), "mL/kg/min",
    f"latest of <b>{len(vo2_vals)}</b> estimates · peak {fmt(vo2_vals.max(), '.1f')}"
    if HAS_VO2 else "not recorded in this export", vo2_vals if HAS_VO2 else None, C["red"])
st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
k = st.columns(4)
kpi(k[0], "Steps", fmt(df["total_steps"].mean(), ",.0f"), "/day",
    f"peak <b>{fmt(df['total_steps'].max(), ',.0f')}</b>", df["total_steps"], C["orange"])
kpi(k[1], "Active energy", fmt(df["active_energy_kcal"].mean(), ".0f"), "kcal/day",
    f"total <b>{fmt(df['active_energy_kcal'].sum(), ',.0f')}</b> kcal", df["active_energy_kcal"], C["yellow"])
kpi(k[2], "Workout time", fmt(hr_days["workout_minutes"].mean(), ".0f"), "min/day",
    "detected from 5-s sampling bursts", hr_days["workout_minutes"], C["magenta"])
kpi(k[3], "Signal coverage", fmt(hr_days["monitored_hours"].mean(), ".1f"), "h/worn day",
    f"<b>{n_no_hr}</b> days not worn · <b>{int(df['low_coverage'].sum())}</b> low-coverage",
    hr_days["monitored_hours"], C["blue"])

# =============================================================================
# 5. Tabs
# =============================================================================
tab_over, tab_cardio, tab_ctx, tab_circ, tab_quality, tab_sensor, tab_stats, tab_data = st.tabs([
    "Overview", "Cardiovascular", "Population context", "Circadian rhythm", "Signal quality",
    "Sensor science", "Statistics", "Data & methods"])

# ----------------------------------------------------------------------------- Overview
with tab_over:
    section("Heart rate over time", "time-weighted daily mean · bars = that day's min–max range · gaps = watch not worn")
    with st.container(border=True):
        dense = len(cal) > 90
        fig = go.Figure()
        fig.add_trace(go.Bar(x=hr_days["date"], y=hr_days["max_hr"] - hr_days["min_hr"], base=hr_days["min_hr"],
                             name="Daily min–max range", marker_color="rgba(57,135,229,0.20)", marker_line_width=0,
                             customdata=np.stack([hr_days["min_hr"], hr_days["max_hr"]], axis=-1),
                             hovertemplate="range %{customdata[0]:.0f}–%{customdata[1]:.0f} bpm"))
        fig.add_trace(go.Scatter(x=cal["date"], y=cal["avg_hr_naive"], mode="lines", name="Mean HR (naive sample mean)",
                                 line=dict(color="#7C8699", width=1.3, dash="dot"), hovertemplate="%{y:.0f} bpm"))
        fig.add_trace(go.Scatter(x=cal["date"], y=cal["avg_hr"], mode="lines+markers", name="Mean HR (time-weighted)",
                                 line=dict(color=C["blue"], width=2), marker=dict(size=4 if dense else 6),
                                 hovertemplate="%{y:.0f} bpm"))
        fig.add_trace(go.Scatter(x=cal["date"], y=cal["resting_hr"], mode="lines+markers", name="Resting HR (Apple)",
                                 line=dict(color=C["aqua"], width=1.8), marker=dict(size=4 if dense else 6),
                                 hovertemplate="%{y:.0f} bpm"))
        show(base_layout(fig, 420, ytitle="bpm"))
    _bias = (hr_days["avg_hr_naive"] - hr_days["avg_hr"]).mean()
    note("<b>Reading this chart.</b> The dotted grey line is what a naive <code>mean()</code> of the samples gives. "
         f"It runs about <b>{fmt(_bias, '.0f')} bpm</b> hotter than the solid blue line on average because the watch "
         "records every ~5 s during workouts but only every few minutes at rest, so exercise is over-represented in "
         "a plain average. The blue line weights each sample by the time it was in force — see <b>Signal quality</b>. "
         f"Lines break where the watch was not worn ({n_no_hr} of {len(cal)} days in this window); nothing is interpolated.")

    c1, c2 = st.columns(2)
    with c1:
        section("Daily steps", "movement volume")
        with st.container(border=True):
            fig = go.Figure(go.Bar(x=df["date"], y=df["total_steps"], marker_color=C["orange"],
                                   marker_line_width=0, hovertemplate="%{y:,.0f} steps"))
            fig.update_traces(marker=dict(cornerradius=4))
            fig.add_hline(y=df["total_steps"].mean(), line=dict(color=C["ink2"], width=1, dash="dot"),
                          annotation_text=f"mean {df['total_steps'].mean():,.0f}", annotation_position="top left",
                          annotation_font_color=C["ink2"], annotation_bgcolor="rgba(17,23,35,.85)")
            show(base_layout(fig, 300, ytitle="steps", legend=False))
    with c2:
        section("Active energy", "movement intensity (kcal above resting metabolism)")
        with st.container(border=True):
            fig = go.Figure(go.Bar(x=df["date"], y=df["active_energy_kcal"], marker_color=C["yellow"],
                                   marker_line_width=0, hovertemplate="%{y:.0f} kcal"))
            fig.update_traces(marker=dict(cornerradius=4))
            fig.add_hline(y=df["active_energy_kcal"].mean(), line=dict(color=C["ink2"], width=1, dash="dot"),
                          annotation_text=f"mean {df['active_energy_kcal'].mean():.0f}", annotation_position="top left",
                          annotation_font_color=C["ink2"], annotation_bgcolor="rgba(17,23,35,.85)")
            show(base_layout(fig, 300, ytitle="kcal", legend=False))

# ----------------------------------------------------------------------------- Cardiovascular
with tab_cardio:
    section("Time in heart-rate zones", f"minutes per day · zones as % of HRmax (pipeline uses 200 bpm)")
    with st.container(border=True):
        fig = go.Figure()
        for col, label, color in zip(ZONE_COLS, ZONE_LABELS, ZONE_RAMP):
            fig.add_trace(go.Bar(x=hr_days["date"], y=hr_days[col], name=label, marker_color=color,
                                 marker_line=dict(color=C["surface"], width=1 if len(hr_days) <= 60 else 0), hovertemplate="%{y:.0f} min"))
        fig.update_layout(barmode="stack", bargap=0.25)
        fig = base_layout(fig, 380, ytitle="minutes")
        fig.update_layout(legend_traceorder="normal")
        show(fig)

    c1, c2 = st.columns([1.1, 1])
    with c1:
        section("Zone definitions", f"for HRmax = {hr_max_est} bpm (sidebar age)")
        edges = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        total_min = hr_days[ZONE_COLS].sum()
        zone_tbl = pd.DataFrame({
            "Zone": ZONE_LABELS,
            "% HRmax": [f"{int(edges[i]*100)}–{int(edges[i+1]*100)} %" for i in range(5)],
            "bpm": [f"{edges[i]*hr_max_est:.0f}–{edges[i+1]*hr_max_est:.0f}" for i in range(5)],
            "Physiology": ["Recovery; fat oxidation dominant", "Aerobic base; comfortable conversation",
                           "Tempo; aerobic capacity builds", "Near lactate threshold; anaerobic contribution rises",
                           "VO₂max effort; sustainable only briefly"],
            "Total min": total_min.round(0).astype(int).values,
        })
        st.dataframe(zone_tbl, hide_index=True, width="stretch")
        note("Zones are a <b>relative-intensity</b> scale: the same 150 bpm is Zone 3 for a 20-year-old and Zone 5 "
             "for a 60-year-old. Fox's 220 − age is the simplest HRmax estimate; the observed peak in this data "
             f"({fmt(df_all['max_hr'].max(), '.0f')} bpm) is a useful sanity check against it. "
             "Minutes below 50 % HRmax are rest and not counted.")
    with c2:
        section("Training load", "Edwards TRIMP = Σ (minutes in zone k × k)")
        with st.container(border=True):
            fig = go.Figure()
            fig.add_trace(go.Bar(x=hr_days["date"], y=hr_days["trimp_edwards"], marker_color=C["violet"],
                                 marker_line_width=0, name="Daily load", hovertemplate="%{y:.0f}"))
            roll, _ = rolling_baseline(cal.set_index("date")["trimp_edwards"])
            fig.add_trace(go.Scatter(x=roll.index, y=roll.values, mode="lines", name="7-day rolling mean",
                                     line=dict(color="#E6EBF5", width=2), hovertemplate="%{y:.0f}"))
            fig.update_traces(selector=dict(type="bar"), marker=dict(cornerradius=4))
            show(base_layout(fig, 330, ytitle="TRIMP (a.u.)"))
        note("TRIMP (training impulse) turns a day's HR profile into one load number by weighting harder zones more. "
             "A rising rolling mean = accumulating training stress; a load spike followed by a higher resting HR "
             "the next morning is the classic under-recovery signature coaches watch for.")

    def baseline_chart(column: str, color: str, rgba: str, unit: str, label: str):
        """Daily values + 7-day rolling mean ± 1 SD band, broken across unworn days.
        Returns the days sitting > 2 SD from the baseline of the PRECEDING days."""
        series = cal.set_index("date")[column]
        rm, rs = rolling_baseline(series)
        fig = go.Figure()
        # Draw the band one contiguous run at a time so it never bridges a gap.
        valid = (rm.notna() & rs.notna()).to_numpy()
        run_id = np.cumsum(np.r_[True, valid[1:] != valid[:-1]])
        first = True
        for rid in np.unique(run_id[valid]):
            idx = rm.index[(run_id == rid) & valid]
            if len(idx) < 2:
                continue
            hi, lo = (rm + rs).loc[idx], (rm - rs).loc[idx]
            fig.add_trace(go.Scatter(x=list(idx) + list(idx[::-1]), y=list(hi) + list(lo[::-1]), fill="toself",
                                     fillcolor=rgba, mode="lines", line=dict(width=0), hoverinfo="skip",
                                     name="±1 SD band", showlegend=first, legendgroup="band"))
            first = False
        fig.add_trace(go.Scatter(x=rm.index, y=rm, mode="lines", name="7-day rolling mean",
                                 line=dict(color=color, width=2.2), hovertemplate="%{y:.1f} " + unit))
        fig.add_trace(go.Scatter(x=series.index, y=series, mode="markers", name=label,
                                 marker=dict(color="#E6EBF5", size=5 if len(cal) > 90 else 7),
                                 hovertemplate="%{y:.0f} " + unit))
        show(base_layout(fig, 320, ytitle=unit))
        # Flag against a longer, stricter reference (14 days, at least 7 valid) so a
        # noisy 3-point SD cannot manufacture "anomalies".
        ref_mean, ref_sd = rolling_baseline(series, window=14, min_periods=7)
        prev_mean, prev_sd = ref_mean.shift(1), ref_sd.shift(1)
        return series[(series - prev_mean).abs() > 2 * prev_sd.where(prev_sd > 0)]

    def describe_outliers(outliers: pd.Series) -> str:
        if outliers.empty:
            return "No day deviates more than 2 SD from the 14-day baseline of the days before it."
        dates = ", ".join(d.strftime("%b %d") for d in outliers.index[:8])
        more = f" and {len(outliers) - 8} more" if len(outliers) > 8 else ""
        return (f"<b>{len(outliers)}</b> day(s) sit more than 2 SD from the 14-day baseline of the preceding days "
                f"({dates}{more}).")

    section("Resting heart rate baseline", "Apple's daily estimate · 7-day rolling mean ± 1 SD")
    if df["resting_hr"].notna().sum() >= 3:
        with st.container(border=True):
            rest_out = baseline_chart("resting_hr", C["aqua"], "rgba(47,196,143,0.16)", "bpm", "Daily resting HR")
        note("Resting HR is one of the most information-dense wearable signals: it falls with aerobic fitness and "
             "rises with fatigue, illness, dehydration or poor sleep. Tracking it against its <i>own</i> rolling "
             "baseline — rather than a population norm — is how wearables flag anomalies. "
             + describe_outliers(rest_out))
    else:
        st.info("Not enough resting-heart-rate days in this range to draw a baseline.")

    section("Heart-rate variability", "SDNN from the Watch's short PPG windows · 7-day rolling mean ± 1 SD")
    if HAS_HRV:
        with st.container(border=True):
            hrv_out = baseline_chart("hrv_sdnn_ms", C["violet"], "rgba(156,140,242,0.18)", "ms", "Daily mean SDNN")
        note("<b>What SDNN is.</b> A healthy heart does not beat like a metronome: the gap between beats (the "
             "inter-beat interval) lengthens and shortens with breathing and autonomic tone. SDNN is simply the "
             "standard deviation of those intervals in a measurement window, in milliseconds:"
             "<br><span class='eq'>SDNN = √( Σ (IBIᵢ − mean IBI)² / (N − 1) )</span><br>"
             "Higher resting HRV generally reflects stronger parasympathetic (vagal) influence; it tends to drop "
             "with fatigue, stress or illness, which is why it is paired with resting HR as a recovery marker. "
             "Two caveats an engineer should state: the Watch derives this from <i>PPG</i> pulse intervals rather "
             "than ECG R-R intervals, and from ~1-minute windows rather than the 24-hour recordings clinical SDNN "
             "norms are based on — so compare it to its own baseline, never to clinical reference ranges. "
             + describe_outliers(hrv_out))
    else:
        st.info("No HRV (SDNN) values in this window — the Watch only records them in some conditions.")

    section("Cardiorespiratory fitness", "Apple's VO₂max estimate — updated only after qualifying outdoor walks / runs")
    if HAS_VO2:
        vo2 = df.dropna(subset=["vo2_max"])
        c1, c2 = st.columns([1.4, 1])
        with c1:
            with st.container(border=True):
                fig = go.Figure(go.Scatter(x=vo2["date"], y=vo2["vo2_max"], mode="lines+markers", name="VO₂max estimate",
                                           line=dict(color=C["red"], width=2, shape="hv"), marker=dict(size=8),
                                           hovertemplate="%{y:.1f} mL/kg/min"))
                fig = base_layout(fig, 300, ytitle="mL/kg/min", legend=False)
                _vref = ref_row(VO2_REF, sex, age)
                if _vref:
                    fig.add_hrect(y0=_vref[1][2], y1=_vref[1][4], fillcolor="rgba(154,163,181,0.14)", line_width=0,
                                  annotation_text=f"US reference 25th–75th pct · {sex.lower()} {_vref[0]} · lab-measured",
                                  annotation_position="top left", annotation_font=dict(size=10, color=C["ink2"]))
                    fig.add_hline(y=_vref[1][3], line=dict(color=C["ink2"], width=1, dash="dot"))
                fig.update_xaxes(range=[cal["date"].min(), cal["date"].max()])
                show(fig)
        with c2:
            note("<b>VO₂max</b> is the maximum rate at which the body can take up and use oxygen — the gold-standard "
                 "measure of aerobic fitness, properly measured with a metabolic cart during a maximal test. "
                 "A wearable cannot measure oxygen; it <i>estimates</i> VO₂max from the relationship between pace "
                 "(GPS + accelerometer) and heart-rate response during outdoor walks and runs. That makes it a "
                 f"sparse, model-based signal: only <b>{len(vo2)}</b> estimates in this window, drawn as steps "
                 "because the value simply holds until the next qualifying workout. Useful for direction of travel; "
                 "not a lab measurement.")
    else:
        st.info("No VO₂max estimates in this window — the Watch only produces one after a qualifying outdoor walk or run.")

# ----------------------------------------------------------------------------- Population context
with tab_ctx:
    note("<h4>What this tab is — and is not</h4>"
         "It places three of my numbers next to <b>published US reference data</b> for the age and sex chosen in the "
         "sidebar, so a reader can see roughly where they sit in a population. It is context, not a health "
         "assessment: nothing here is labelled normal or abnormal. Reference data is <b>national</b> and split by age "
         "and sex only — no published tables exist at city or state level, so there is no \"regional\" comparison. "
         "Each comparison also crosses a <b>measurement-method gap</b> (a wearable's estimate vs a laboratory or "
         "clinical measurement), which is spelled out under each chart.", "warn")

    # ---- VO2max ---------------------------------------------------------------
    section("VO₂max", "my wearable estimate vs lab-measured US reference (FRIEND registry)")
    vref = ref_row(VO2_REF, sex, age)
    if not HAS_VO2:
        st.info("No VO₂max estimates in this window.")
    elif vref is None:
        st.info("The FRIEND reference tables cover ages 20–79; no reference row exists for the selected age.")
    else:
        v_latest, v_med = vo2_vals.iloc[-1], vo2_vals.median()
        with st.container(border=True):
            show(percentile_strip(vref[1], v_latest, vo2_vals.min(), vo2_vals.max(), "mL/kg/min", C["red"],
                                  "My latest estimate"))
        note(f"Reference: <b>{sex.lower()}, {vref[0]} years</b>. My latest estimate ({v_latest:.1f}) sits at "
             f"<b>{estimate_percentile(v_latest, vref[1])}</b>; across this window my {len(vo2_vals)} estimates ranged "
             f"{vo2_vals.min():.1f}–{vo2_vals.max():.1f} (median {v_med:.1f}, {estimate_percentile(v_med, vref[1])}). "
             "<br><b>Method gap:</b> the reference values were <i>measured</i> — expired-gas analysis during a maximal "
             "treadmill test. Mine are <i>estimated</i> by the watch from pace and heart-rate response on outdoor "
             "walks and runs, with no gas measurement. A wearable estimate can be off for any one "
             "individual, so the percentile is a rough placement, and the registry itself is a sample of people who "
             "came in for exercise testing rather than a random sample of the country.")

    # ---- Resting HR -----------------------------------------------------------
    section("Resting heart rate", "my daily Apple estimates vs US resting pulse reference (NHANES 1999–2008)")
    rref = ref_row(RHR_REF, sex, age)
    if rest_recent.empty:
        st.info("No resting-heart-rate values in this window.")
    elif rref is None:
        st.info("The adult reference rows used here start at age 16; no reference row exists for the selected age.")
    else:
        r_med = rest_recent.median()
        with st.container(border=True):
            show(percentile_strip(rref[1], r_med, rest_recent.quantile(.05), rest_recent.quantile(.95), "bpm",
                                  C["aqua"], "My median resting HR"))
        note(f"Reference: <b>{sex.lower()}, {rref[0]} years</b>. My median daily resting HR ({r_med:.0f} bpm over "
             f"{len(rest_recent)} days) sits at <b>{estimate_percentile(r_med, rref[1])}</b>; the bar shows the middle "
             f"90 % of my days ({rest_recent.quantile(.05):.0f}–{rest_recent.quantile(.95):.0f} bpm). "
             "<br><b>Method gap:</b> the survey value is a pulse counted once, by an examiner, after about four minutes "
             "of seated rest in a clinic. Apple's figure is an algorithmic daily estimate built from background PPG "
             "readings while still and awake. They target the same quantity but are not the same measurement, so small "
             "differences in percentile should not be over-read.")

    # ---- Steps ----------------------------------------------------------------
    section("Daily steps", "my mean vs the US adult average (NHANES 2005–2006) — the loosest of the three")
    s1, s2, s3 = st.columns(3)
    my_steps = df["total_steps"].mean()
    kpi(s1, "My mean", fmt(my_steps, ",.0f"), "steps/day", f"{int(df['total_steps'].notna().sum())} days in window",
        color=C["orange"])
    kpi(s2, "US adults 20+", f"{STEPS_REF_US_ADULTS:,}", "steps/day", "hip accelerometer, pedometer-scaled")
    kpi(s3, "Ratio", fmt(my_steps / STEPS_REF_US_ADULTS, ".2f"), "×", "my mean ÷ reference mean")
    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
    note("<b>Why this one is only a rough guide.</b> The reference is a single figure for all US adults aged 20 and "
         "over — it is not split by age or sex — measured with a hip-worn research accelerometer in 2005–2006, with "
         "low-intensity steps removed to mimic a pedometer. Mine come from a wrist watch plus phone two decades "
         "later, with different step-detection algorithms and no such censoring. Different sensor location, different "
         "algorithm, different era: read the ratio as \"more or less than a typical adult\", not as a precise multiple.")

    # ---- HRV: deliberately no comparison --------------------------------------
    section("Heart-rate variability", "deliberately not compared")
    note("No reference line is drawn for HRV. Published SDNN norms come from <b>24-hour ECG</b> recordings; the watch "
         "reports SDNN from <b>~1-minute optical (PPG)</b> windows taken a few times a day. SDNN grows with recording "
         "length — a full day contains slow circadian swings a one-minute window cannot — so the two numbers are on "
         "different scales, and plotting one against the other would be a category error. HRV is tracked against my "
         "own baseline instead (Cardiovascular tab). Mean heart rate, zone minutes and TRIMP have no population "
         "norms at all, for the same reason: they depend on how and when the device samples.")

    section("Sources")
    note("<ul style='margin:.1rem 0 0 1rem;padding:0'>"
         "<li><b>VO₂max</b> — Kaminsky et al., <i>Mayo Clinic Proceedings</i> 2015, FRIEND registry, Table 3. "
         "7,783 maximal treadmill tests with gas analysis, US adults 20–79 without cardiovascular disease.</li>"
         "<li><b>Resting heart rate</b> — Ostchega et al., <i>National Health Statistics Reports</i> no. 41, 2011, "
         "Tables 2–3. NHANES 1999–2008; pulse counted after about four minutes of seated rest.</li>"
         "<li><b>Steps per day</b> — Tudor-Locke et al., <i>Int J Behav Nutr Phys Act</i> 2010. NHANES 2005–2006, "
         "3,522 US adults aged 20+; hip-worn ActiGraph accelerometer, censored steps.</li></ul>")
    st.caption("Percentiles between tabulated values are linearly interpolated; values outside the 5th–95th range are "
               "reported only as below/above. Reference numbers are transcribed from the cited tables.")

# ----------------------------------------------------------------------------- Circadian
with tab_circ:
    if hourly is None or hourly.empty:
        st.info("hourly_hr.csv not found — re-run `python build_daily_summary.py` to generate the hour-level table.")
    else:
        section("Heart rate by hour of day", "time-weighted mean per hour across the window")
        with st.container(border=True):
            n_hr_dates = hourly["date"].nunique()
            if n_hr_dates > 60:
                # Long window: one row per week (monitored-minute-weighted) keeps the map readable.
                wk = hourly.assign(week=hourly["date"].dt.to_period("W-SUN").dt.start_time)
                pivot = (wk.groupby(["week", "hour"])
                           .apply(lambda d: np.average(d["hr_tw"], weights=d["monitored_min"])
                                  if d["monitored_min"].sum() else np.nan, include_groups=False)
                           .unstack("hour").reindex(columns=range(24)))
                y_labels = ["wk of " + d.strftime("%b %d") for d in pivot.index]
                st.caption(f"Window spans {n_hr_dates} days with data, so rows are weeks (Mon–Sun), each cell "
                           "weighted by monitored minutes. Narrow the date range to 60 days or fewer for one row per day.")
            else:
                pivot = hourly.pivot(index="date", columns="hour", values="hr_tw").reindex(columns=range(24))
                y_labels = list(pivot.index.strftime("%b %d"))
            fig = go.Figure(go.Heatmap(
                z=pivot.values, x=[f"{h:02d}:00" for h in range(24)], y=y_labels,
                colorscale=[[0, "#15243D"], [0.5, "#2E6FC0"], [1, "#9ED0FF"]], zmin=55, zmax=150,
                colorbar=dict(title="bpm", thickness=12, len=0.8, tickfont=dict(color=C["ink2"])), xgap=2, ygap=2,
                hovertemplate="%{y} · %{x}<br>%{z:.0f} bpm<extra></extra>", hoverongaps=False))
            fig = base_layout(fig, max(380, 16 * len(pivot) + 60), legend=False)
            fig.update_layout(hovermode="closest")
            fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=10))
            fig.update_xaxes(tickangle=0, tickvals=[f"{h:02d}:00" for h in range(0, 24, 3)])
            show(fig)
        c1, c2 = st.columns([1.3, 1])
        with c1:
            section("Average 24-hour profile", "weighted by monitored minutes; band = interquartile range across days")
            with st.container(border=True):
                prof = (hourly.groupby("hour")
                        .apply(lambda d: pd.Series({
                            "mean": np.average(d["hr_tw"], weights=d["monitored_min"]) if d["monitored_min"].sum() else np.nan,
                            "q25": d["hr_tw"].quantile(.25), "q75": d["hr_tw"].quantile(.75),
                            "mins": d["monitored_min"].sum()}), include_groups=False)
                        .reindex(range(24)))
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=prof.index, y=prof["q75"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=prof.index, y=prof["q25"], line=dict(width=0), fill="tonexty",
                                         fillcolor="rgba(57,135,229,0.16)", name="Interquartile range", hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=prof.index, y=prof["mean"], mode="lines+markers", name="Mean HR",
                                         line=dict(color=C["blue"], width=2.2), marker=dict(size=6),
                                         hovertemplate="%{y:.0f} bpm"))
                fig = base_layout(fig, 320, ytitle="bpm", xtitle="hour of day")
                fig.update_xaxes(tickvals=list(range(0, 24, 3)), ticktext=[f"{h:02d}:00" for h in range(0, 24, 3)])
                show(fig)
        with c2:
            section("Monitoring density", "minutes of HR data per hour slot")
            with st.container(border=True):
                fig = go.Figure(go.Bar(x=prof.index, y=prof["mins"] / max(hourly["date"].nunique(), 1), marker_color=C["magenta"],
                                       marker_line_width=0, hovertemplate="%{y:.0f} min/day"))
                fig.update_traces(marker=dict(cornerradius=4))
                fig = base_layout(fig, 320, ytitle="min per worn day", xtitle="hour of day", legend=False)
                fig.update_xaxes(tickvals=list(range(0, 24, 3)), ticktext=[f"{h:02d}:00" for h in range(0, 24, 3)])
                show(fig)
        night = prof.loc[0:5, "mean"].mean()
        day = prof.loc[12:20, "mean"].mean()
        note(f"<b>Circadian physiology.</b> Heart rate follows a ~24 h rhythm driven by the autonomic nervous system: "
             f"parasympathetic (vagal) tone dominates at night, sympathetic tone during the day. Here the overnight "
             f"mean (00–05 h) is <b>{fmt(night, '.0f')} bpm</b> versus <b>{fmt(day, '.0f')} bpm</b> through the "
             f"afternoon/evening. The afternoon-evening hot spots in the heatmap are workouts. Note that overnight "
             f"coverage is thin (right chart) — the watch was often charging — which is why coverage is reported, "
             f"not hidden.")

# ----------------------------------------------------------------------------- Signal quality
with tab_quality:
    section("Sampling bias: naive mean vs time-weighted mean", "the single biggest correction in this project")
    with st.container(border=True):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=hr_days["date"], y=hr_days["avg_hr_naive"] - hr_days["avg_hr"], name="Bias (naive − weighted)",
                             marker_color=C["orange"], marker_line_width=0, hovertemplate="+%{y:.1f} bpm"))
        fig.update_traces(marker=dict(cornerradius=4))
        show(base_layout(fig, 300, ytitle="bpm overestimate"))
    bias = (hr_days["avg_hr_naive"] - hr_days["avg_hr"])
    note(f"<h4>Why a plain average is wrong for this sensor</h4>"
         f"The Watch samples adaptively: about every 5 s in workout mode, every few minutes otherwise, and not at all on "
         f"the charger. Averaging the <i>samples</i> therefore weights a 60-minute run with ~700 readings against a "
         f"quiet afternoon with ~40. The time-weighted mean assigns each sample the duration until the next one "
         f"(capped at 10 min so unmonitored gaps don't count):"
         f"<br><span class='eq'>HR̄ = Σ (HRᵢ · Δtᵢ) / Σ Δtᵢ</span><br>"
         f"Across this window the naive mean overstates heart rate by <b>{fmt(bias.mean(), '.1f')} bpm on average</b> "
         f"and by up to <b>{fmt(bias.max(), '.1f')} bpm</b> on the heaviest training day. "
         f"This matters downstream: the Statistics tab shows how much of the 'energy vs HR' correlation "
         f"is really this artefact.", "warn")

    c1, c2 = st.columns(2)
    with c1:
        section("Daily monitored time", "hours of valid HR coverage; grey = flagged low coverage")
        with st.container(border=True):
            colors = np.where(hr_days["low_coverage"], "#3A4252", C["magenta"])
            fig = go.Figure(go.Bar(x=hr_days["date"], y=hr_days["monitored_hours"], marker_color=colors,
                                   marker_line_width=0, hovertemplate="%{y:.1f} h"))
            fig.update_traces(marker=dict(cornerradius=4))
            fig.add_hline(y=2, line=dict(color=C["orange"], width=1, dash="dot"),
                          annotation_text="2 h threshold", annotation_position="top left", annotation_font_color=C["orange"],
                          annotation_bgcolor="rgba(17,23,35,.85)")
            show(base_layout(fig, 320, ytitle="hours", legend=False))
    with c2:
        section("Sensor duty cycle", "distribution of gaps between consecutive HR samples (whole dataset)")
        if sampling is not None:
            with st.container(border=True):
                fig = go.Figure(go.Bar(x=sampling["gap_bucket"], y=sampling["share"] * 100, marker_color=C["blue"],
                                       marker_line_width=0, hovertemplate="%{y:.1f} % of samples<br>%{customdata:,} samples",
                                       customdata=sampling["samples"]))
                fig.update_traces(marker=dict(cornerradius=4))
                show(base_layout(fig, 320, ytitle="% of samples", legend=False))
        else:
            st.info("sampling_profile.csv not found — re-run the pipeline.")
    _dense = f"{sampling['share'].iloc[0] * 100:.0f} %" if sampling is not None else "most"
    note("<b>Signal-integrity reporting</b> is a core medical-device habit: a number without its coverage is not "
         "interpretable. Every daily value here carries <code>hr_samples</code>, <code>monitored_hours</code> and a "
         "<code>low_coverage</code> flag, and the dashboard greys out thin days rather than silently dropping them. "
         f"The duty-cycle histogram shows the two sampling regimes directly: {_dense} of all samples arrive ≤ 10 s "
         "apart (workouts) yet represent a minority of wall-clock time. "
         f"<b>Wear pattern:</b> the watch was not worn on {n_no_hr} of {len(cal)} days in this window, and wear is "
         "not random — it is more likely on training days — so worn days over-represent activity. That is a "
         "selection effect, stated here rather than corrected for.", "good")

# ----------------------------------------------------------------------------- Sensor science
with tab_sensor:
    section("How a wrist wearable measures heart rate", "photoplethysmography (PPG) — original schematic, not to scale")
    with st.container(border=True):
        st.markdown(sensor_cross_section_svg(), unsafe_allow_html=True)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        note("<h4>Optical principle</h4>"
             "Green LEDs (~525 nm) shine into the skin and photodiodes measure the light that returns. "
             "Haemoglobin absorbs green light strongly, so every heartbeat pushes a pulse of blood into the "
             "capillaries and the returned light dips. The slow baseline (tissue, bone, venous blood) is the "
             "<b>DC</b> component; the beat-to-beat ripple is the <b>AC</b> component, typically only 1–2 % of DC. "
             "Attenuation follows the Beer–Lambert law:"
             "<br><span class='eq'>I = I₀ · e^(−ε · c · ℓ)</span><br>"
             "where <i>ε</i> is haemoglobin's extinction coefficient, <i>c</i> its concentration and <i>ℓ</i> the "
             "optical path length — the path length changes with each pulse, which is what we detect.")
        note("<h4>Why green, and why it is hard</h4>"
             "Green has a shorter penetration depth than red/IR, so it is less sensitive to motion of deeper tissue — "
             "good for a wrist device that moves. The price is sensitivity to skin tone, ambient light and cold "
             "(vasoconstriction shrinks the AC signal). Motion artefacts live in the same 0.5–4 Hz band as the pulse, "
             "which is why the Watch samples densely only during workouts (motion is known) and uses the accelerometer "
             "as a reference channel. The duty cycle you saw in <b>Signal quality</b> is a power-budget decision "
             "made by the firmware.")
    with c2:
        note("<h4>From light to a number</h4>"
             "<ol style='margin:.2rem 0 0 1rem;padding:0'>"
             "<li>Photodiode current → trans-impedance amplifier → ADC (digitised at tens to hundreds of Hz)</li>"
             "<li>Band-pass filter (≈0.5–5 Hz) removes DC drift, respiration and high-frequency noise</li>"
             "<li>Peak detection finds each systolic upstroke</li>"
             "<li>HR = 60 / mean inter-beat interval; variability of those intervals is HRV</li>"
             "<li>Quality gating: reject windows where accelerometer energy is high or the signal-to-noise ratio is low</li>"
             "</ol>")
        note("<h4>PPG vs ECG</h4> ECG measures the heart's <i>electrical</i> depolarisation (the R-peak); PPG measures "
             "the <i>mechanical</i> pressure wave arriving at the wrist ~200 ms later. PPG is convenient and continuous, "
             "ECG is the clinical reference. Consumer HRV from PPG is reliable at rest, not during motion — "
             "a limitation worth stating in any wearable study.")

    section("Interactive PPG simulator", "synthetic waveform → band-pass filter → peak detection → heart-rate estimate")
    s1, s2, s3 = st.columns(3)
    true_hr = s1.slider("Simulated heart rate (bpm)", 40, 180, 72, 1)
    noise = s2.slider("Sensor noise (relative to pulse amplitude)", 0.0, 0.6, 0.15, 0.05)
    motion = s3.toggle("Add a motion artefact burst", value=False)

    fs = 100.0
    t = np.arange(0, 10, 1 / fs)
    period = 60.0 / true_hr
    ppg = np.zeros_like(t)
    rng = np.random.default_rng(7)
    beat_times = np.arange(0.3, t[-1], period)
    for tb in beat_times:
        # Each pulse = systolic peak + smaller, later dicrotic (reflected) wave.
        ppg += 1.00 * np.exp(-((t - tb) / (0.11 * period)) ** 2)
        ppg += 0.22 * np.exp(-((t - tb - 0.30 * period) / (0.14 * period)) ** 2)
    raw = 10.0 + ppg + 0.35 * np.sin(2 * np.pi * 0.25 * t)          # DC offset + respiratory baseline wander
    raw += noise * rng.standard_normal(t.size)
    if motion:
        burst = (t > 4.0) & (t < 5.8)
        raw += burst * 1.0 * np.sin(2 * np.pi * 1.6 * t)   # 1.6 Hz = inside the pulse band

    sos = signal.butter(3, [0.5, 5.0], btype="bandpass", fs=fs, output="sos")
    filt = signal.sosfiltfilt(sos, raw)
    # Peak detector: refractory period of 0.3 s (max 200 bpm), and height/prominence
    # thresholds relative to the signal's own 98th percentile so it adapts to gain.
    ref = np.percentile(filt, 98)
    peaks, _ = signal.find_peaks(filt, distance=int(0.3 * fs), height=0.35 * ref, prominence=0.3 * ref)
    edge = 0.4                                  # drop filtfilt edge transients
    peaks = peaks[(t[peaks] > edge) & (t[peaks] < t[-1] - edge)]
    expected_beats = int(((beat_times > edge) & (beat_times < t[-1] - edge)).sum())
    ibi = np.diff(t[peaks])
    est_hr = 60.0 / ibi.mean() if ibi.size else np.nan
    sdnn_ms = ibi.std() * 1000 if ibi.size > 1 else np.nan

    with st.container(border=True):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t, y=raw - raw.mean(), mode="lines", name="Raw photodiode signal (AC + wander + noise)",
                                 line=dict(color="#6B7486", width=1.2), hovertemplate="%{y:.2f}"))
        fig.add_trace(go.Scatter(x=t, y=filt, mode="lines", name="Band-passed 0.5–5 Hz",
                                 line=dict(color=C["blue"], width=2), hovertemplate="%{y:.2f}"))
        fig.add_trace(go.Scatter(x=t[peaks], y=filt[peaks], mode="markers", name="Detected systolic peaks",
                                 marker=dict(color=C["orange"], size=9, symbol="circle"), hovertemplate="beat @ %{x:.2f} s"))
        if motion:
            fig.add_vrect(x0=4.0, x1=5.8, fillcolor=C["red"], opacity=0.07, line_width=0,
                          annotation_text="motion artefact", annotation_position="top left", annotation_font_color=C["red"])
        fig = base_layout(fig, 340, ytitle="a.u.", xtitle="time (s)")
        fig.update_layout(hovermode="closest")
        show(fig)
    r1, r2, r3, r4 = st.columns(4)
    kpi(r1, "True HR", f"{true_hr}", "bpm", "simulator input")
    kpi(r2, "Estimated HR", fmt(est_hr, ".1f"), "bpm", f"error <b>{fmt(est_hr - true_hr, '+.1f')}</b> bpm", color=C["orange"])
    kpi(r3, "Beats detected", f"{len(peaks)}", "", f"expected <b>{expected_beats}</b> in the analysed window")
    kpi(r4, "SDNN (HRV)", fmt(sdnn_ms, ".0f"), "ms", "should be ~0 for a perfectly regular synthetic pulse", color=C["aqua"])
    note("Turn the noise up: the estimate stays stable through moderate noise because the band-pass filter "
         "removes most of it, then starts dropping beats at high heart rates where each pulse is narrow — the "
         "same regime where real wrist sensors struggle. Enable the motion burst: a 1.6 Hz artefact sits "
         "inside the pulse band, so filtering alone cannot remove it; spurious peaks appear and SDNN explodes. That is exactly why real devices gate on accelerometer data and "
         "why the watch's dense workout sampling is paired with motion-aware algorithms. The same "
         "<code>scipy.signal</code> chain (Butterworth SOS filter → <code>find_peaks</code>) is what the Phase 2 "
         "MAX30102 prototype will run on its raw photodiode stream.")

# ----------------------------------------------------------------------------- Statistics
def render_statistics():
    """Statistics tab (own function so an early return never stops the other tabs)."""
    section("Does activity predict heart rate?", "Pearson & Spearman correlations, computed live in Python")

    def corr_block(x: pd.Series, y: pd.Series):
        s = pd.concat([x, y], axis=1).dropna()
        if len(s) < 4:
            return None
        r, p = stats.pearsonr(s.iloc[:, 0], s.iloc[:, 1])
        rho, p_s = stats.spearmanr(s.iloc[:, 0], s.iloc[:, 1])
        return dict(n=len(s), r=r, p=p, rho=rho, p_s=p_s, data=s)

    pairs = {
        "Active energy vs mean HR (time-weighted)": ("active_energy_kcal", "avg_hr"),
        "Active energy vs mean HR (naive)": ("active_energy_kcal", "avg_hr_naive"),
        "Steps vs mean HR (time-weighted)": ("total_steps", "avg_hr"),
        "Active energy vs workout minutes": ("active_energy_kcal", "workout_minutes"),
        "Training load (TRIMP) vs next-day resting HR": ("trimp_edwards", "resting_hr_next"),
        "HRV (SDNN) vs resting HR, same day": ("hrv_sdnn_ms", "resting_hr"),
        "Training load (TRIMP) vs next-day HRV": ("trimp_edwards", "hrv_next"),
    }
    # "Next day" must mean the next CALENDAR day, so shift on the calendar-complete
    # frame - shifting a frame with missing days would pair Monday with Thursday.
    work = cal.copy()
    work["resting_hr_next"] = work["resting_hr"].shift(-1)
    work["hrv_next"] = work["hrv_sdnn_ms"].shift(-1)
    rows, results = [], {}
    for label, (xc, yc) in pairs.items():
        res = corr_block(work[xc], work[yc])
        results[label] = res
        if res:
            rows.append({"Comparison": label, "n days": res["n"], "Pearson r": round(res["r"], 3),
                         "p": f"{res['p']:.3g}", "Spearman ρ": round(res["rho"], 3), "p (ρ)": f"{res['p_s']:.3g}",
                         "Significant (α = .05)": "yes" if res["p"] < .05 else "no"})
    available = [k for k, v in results.items() if v]
    if not available:
        st.info("Select at least four days with heart-rate data to compute correlations.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    choice = st.selectbox("Scatter plot", available)
    res = results[choice]
    xc, yc = pairs[choice]
    with st.container(border=True):
        s = res["data"]
        x, y = s.iloc[:, 0].to_numpy(), s.iloc[:, 1].to_numpy()
        lr = stats.linregress(x, y)
        xg = np.linspace(x.min(), x.max(), 100)
        yhat = lr.intercept + lr.slope * xg
        # 95 % confidence band for the mean response
        n = len(x)
        resid = y - (lr.intercept + lr.slope * x)
        se = np.sqrt((resid ** 2).sum() / (n - 2))
        sxx = ((x - x.mean()) ** 2).sum()
        tcrit = stats.t.ppf(0.975, n - 2)
        band = tcrit * se * np.sqrt(1 / n + (xg - x.mean()) ** 2 / sxx)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xg, y=yhat + band, line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=xg, y=yhat - band, line=dict(width=0), fill="tonexty", fillcolor="rgba(255,122,69,0.16)",
                                 name="95 % CI of fit", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=xg, y=yhat, mode="lines", name=f"OLS fit  (y = {lr.intercept:.1f} + {lr.slope:.3g}·x)",
                                 line=dict(color=C["orange"], width=2)))
        fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name="Daily values", marker=dict(color=C["blue"], size=9,
                                 line=dict(color=C["surface"], width=1.5)),
                                 customdata=s.index.map(lambda i: work.loc[i, "date"].strftime("%b %d")),
                                 hovertemplate="%{customdata}<br>x = %{x:,.0f}<br>y = %{y:.1f}<extra></extra>"))
        fig = base_layout(fig, 400, xtitle=xc.replace("_", " "), ytitle=yc.replace("_", " "))
        fig.update_layout(hovermode="closest")
        show(fig)
    st.caption(f"n = {res['n']} · Pearson r = {res['r']:.3f} (p = {res['p']:.3g}) · R² = {res['r']**2:.3f} · "
               f"Spearman ρ = {res['rho']:.3f} (p = {res['p_s']:.3g})")

    e_tw, e_nv = results["Active energy vs mean HR (time-weighted)"], results["Active energy vs mean HR (naive)"]
    if e_tw and e_nv:
        shrink = (1 - e_tw["r"] ** 2 / e_nv["r"] ** 2) * 100 if e_nv["r"] else np.nan
        if e_tw["p"] < 0.05 and e_tw["p_s"] < 0.05:
            verdict = (f"The relationship survives the correction and is statistically significant in this "
                       f"{e_tw['n']}-day window, but it is a <b>modest</b> effect: active energy explains about "
                       f"{e_tw['r'] ** 2 * 100:.0f} % of the day-to-day variance in mean heart rate, not the "
                       f"{e_nv['r'] ** 2 * 100:.0f} % the naive metric suggests.")
        else:
            verdict = (f"In this {e_tw['n']}-day window the corrected relationship is modest and not robustly "
                       f"significant — widen the date range for more statistical power.")
        note(f"<h4>What the sampling correction changed</h4>"
             f"With the naive sample mean, active energy and heart rate look strongly related "
             f"(r = {e_nv['r']:.2f}, p = {e_nv['p']:.2g}). With the time-weighted mean the association shrinks to "
             f"r = {e_tw['r']:.2f} (p = {e_tw['p']:.2g}; Spearman ρ = {e_tw['rho']:.2f}, p = {e_tw['p_s']:.2g}) — "
             f"roughly <b>{fmt(shrink, '.0f')} % of the apparent explained variance was the sampling artefact</b>: the "
             f"sensor records more samples on workout days, which inflates the naive mean and active energy together. "
             f"That is a <b>confound</b>, not physiology. {verdict}", "warn")
    h_r = results.get("HRV (SDNN) vs resting HR, same day")
    if h_r:
        direction = "negative" if h_r["r"] < 0 else "positive"
        note(f"<h4>HRV and resting heart rate</h4>"
             f"Daily SDNN and resting HR show a {direction} correlation (r = {h_r['r']:.2f}, p = {h_r['p']:.2g}, "
             f"n = {h_r['n']}). A negative sign is the textbook expectation: both are governed by the same autonomic "
             f"balance, so days with stronger vagal tone show a slower resting heart <i>and</i> more beat-to-beat "
             f"variability. There is also a purely mathematical contribution — a slower heart has longer inter-beat "
             f"intervals, and longer intervals have more room to vary — so the two are not independent measurements.",
             "good")
    note("<b>Hypothesis framing.</b> H₀: no monotonic association between daily active energy and daily mean heart rate. "
         "Pearson tests a <i>linear</i> relationship and is sensitive to outliers; Spearman tests any <i>monotonic</i> one "
         "on ranks and is robust to them, so both are reported — where they disagree sharply (as for energy vs "
         "workout minutes) an outlier is driving Pearson. Steps vs HR is the planned negative control "
         "(volume ≠ intensity). TRIMP vs next-day resting HR and next-day HRV are exploratory recovery hypotheses, "
         "paired on consecutive <i>calendar</i> days only; several comparisons are tested here without "
         "multiple-comparison correction, so single borderline p-values should be read as leads, not findings.")

    section("Independent reproduction in MATLAB", "correlation_analysis.m · Statistics and Machine Learning Toolbox")
    if os.path.exists("energy_vs_hr_correlation.png"):
        c1, c2 = st.columns([1.3, 1])
        with c1:
            with st.container(border=True):
                st.image("energy_vs_hr_correlation.png", width="stretch")
        with c2:
            note("The same <code>daily_summary.csv</code> is analysed a second time in MATLAB (<code>corr</code>, "
                 "<code>fitlm</code>) and the figure is saved for the dashboard to display. Running the statistics in "
                 "two independent toolchains and checking they agree is standard verification practice in regulated "
                 "medical-device work (think design verification: two methods, one answer). If the figure's numbers "
                 "differ from the live table above, the MATLAB script has not been re-run since the pipeline changed.")
    else:
        st.info("Run `correlation_analysis.m` in MATLAB to generate the reproduction figure.")


with tab_stats:
    render_statistics()
# ----------------------------------------------------------------------------- Data & methods
with tab_data:
    section("Pipeline", "from a 100+ MB Apple Health XML export to this page")
    st.graphviz_chart(f"""
    digraph G {{
      rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.45;
      node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, margin="0.18,0.1",
            color="{C['line']}", fillcolor="{C['surface']}", fontcolor="{C['ink']}"];
      edge [color="{C['ink3']}", arrowsize=0.7];
      xml   [label="export.xml\nApple Health · 100s of MB", fillcolor="{C['surface2']}"];
      parse [label="parse_health_data.py\nstreaming iterparse → per-metric CSVs"];
      build [label="build_daily_summary.py\nlocal-time days · time-weighted HR · zones · TRIMP · coverage"];
      daily [label="daily_summary.csv · hourly_hr.csv · sampling_profile.csv", fillcolor="#15243D", color="{C['blue']}"];
      mat   [label="correlation_analysis.m (MATLAB)\nindependent statistics → energy_vs_hr_correlation.png", fillcolor="#3A2416", color="{C['orange']}"];
      app   [label="app.py — Streamlit · Plotly · SciPy\nthis dashboard", fillcolor="#15243D", color="{C['blue']}"];
      {{ rank=same; xml; parse; }}
      {{ rank=same; mat; app; }}
      xml -> parse; parse -> build; build -> daily; daily -> app; daily -> mat; mat -> app;
    }}
    """, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        note("<h4>Methods</h4>"
             "<ul style='margin:.2rem 0 0 1rem;padding:0'>"
             "<li><b>Streaming parse</b> — <code>ElementTree.iterparse</code> with per-element <code>clear()</code>; memory stays flat.</li>"
             "<li><b>Local-time bucketing</b> — timestamps carry a UTC offset; days are formed in America/Los_Angeles so an evening workout is not split across two dates.</li>"
             "<li><b>Time-weighted mean</b> — each HR sample weighted by its hold time (gap to next sample, capped at 10 min).</li>"
             "<li><b>Zones</b> — 50/60/70/80/90 % of HRmax = 220 − age; minutes accumulated from the same hold times.</li>"
             "<li><b>Workout detection</b> — samples ≤ 15 s apart (the Watch's workout-mode cadence).</li>"
             "<li><b>Training load</b> — Edwards TRIMP, Σ minutes-in-zone × zone index.</li>"
             "<li><b>Baselines</b> — 7-day rolling mean ± 1 SD on calendar days (≥ 3 valid days); anomaly = > 2 SD from the preceding 14-day baseline (≥ 7 valid days).</li>"
             "<li><b>Population context</b> — published US percentile tables by age and sex (FRIEND, NHANES); my value placed by linear interpolation between tabulated percentiles.</li>"
             "<li><b>Gaps</b> — unworn days stay empty; nothing is interpolated, and next-day pairs use consecutive calendar days only.</li>"
             "<li><b>Statistics</b> — Pearson & Spearman with two-sided p-values; OLS with 95 % CI of the mean response.</li>"
             "</ul>")
    with c2:
        note("<h4>Limitations (stated on purpose)</h4>"
             "<ul style='margin:.2rem 0 0 1rem;padding:0'>"
             f"<li>n = 1 person, {len(df_all)} days: trends, not population claims.</li>"
             "<li>Wear is intermittent and non-random (more likely on training days), so worn days over-represent activity.</li>"
             "<li>Overnight coverage is thin (charging), so nocturnal HR is under-sampled.</li>"
             "<li>Apple's resting HR, active energy and VO₂max are themselves model outputs, not raw sensor values.</li>"
             "<li>HRV is PPG-derived SDNN from ~1-minute windows — not comparable to 24-h ECG clinical norms.</li>"
             "<li>Workout detection from sampling cadence is a proxy, not Apple's workout log (a workout left running inflates it).</li>"
             "<li>Several correlations are tested without multiple-comparison correction.</li>"
             "<li>Population comparisons cross a measurement-method gap (wearable estimate vs lab/clinic) and are national, not regional.</li>"
             "<li>Nothing here is diagnostic.</li></ul>", "warn")

    section("Daily table", "every value the charts above are built from")
    show_cols = ["date", "avg_hr", "avg_hr_naive", "min_hr", "max_hr", "resting_hr", "hrv_sdnn_ms", "vo2_max", "total_steps",
                 "active_energy_kcal", "workout_minutes", "trimp_edwards", *ZONE_COLS,
                 "hr_samples", "monitored_hours", "low_coverage"]
    table = df[show_cols].copy()
    table["date"] = table["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(table.round(1), hide_index=True, width="stretch", height=380)
    st.download_button("Download selected range as CSV", df[show_cols].to_csv(index=False).encode(),
                       file_name="daily_summary_selected.csv", mime="text/csv")

st.markdown('<p class="footer">Built by Nabeel Abdel · Biomedical Engineering, San José State University · '
            'Python · pandas · Plotly · SciPy · Streamlit · MATLAB</p>', unsafe_allow_html=True)
