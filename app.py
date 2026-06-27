"""
app.py

Wearable Health Insights Dashboard - v1

A simple, honest dashboard for exploring trends in heart rate,
resting heart rate, activity, and energy burn from Apple Watch data.

This is a WELLNESS tool, not a diagnostic one - it shows trends in
your own data, it does not interpret or flag medical conditions.

Run with: streamlit run app.py

Author: Nabeel Abdel
"""

import os
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Wearable Health Insights",
    page_icon="❤️",
    layout="wide",
)

# --- Custom styling ----------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: #FAFAF8; }
    .block-container { padding-top: 2.5rem; max-width: 1200px; }

    .dash-title {
        font-size: 2.1rem; font-weight: 700; color: #1D1D1F;
        letter-spacing: -0.02em; margin-bottom: 0;
    }
    .dash-subtitle {
        color: #86868B; font-size: 0.95rem; max-width: 640px; line-height: 1.5;
    }

    .cards-caption {
        color: #86868B; font-size: 0.82rem; margin: 0.2rem 0 0.9rem 0;
    }

    .metric-card {
        background: #FFFFFF; border: 1px solid #E5E5E7; border-radius: 14px;
        padding: 1.1rem 1.3rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .metric-label {
        font-size: 0.78rem; font-weight: 600; color: #86868B;
        text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.35rem;
    }
    .metric-value { font-size: 1.9rem; font-weight: 700; color: #1D1D1F; }
    .metric-sub { font-size: 0.82rem; font-weight: 600; color: #86868B; margin-top: 0.3rem; }

    .section-label { display: flex; align-items: center; gap: 0.6rem; margin: 1.5rem 0 0.9rem 0; }
    .section-bar { width: 4px; height: 22px; border-radius: 2px; }
    .section-bar.blue { background: #0071E3; }
    .section-bar.coral { background: #E8503A; }
    .section-title { font-size: 1.15rem; font-weight: 700; color: #1D1D1F; margin: 0; }

    .chart-caption {
        font-size: 0.82rem; font-weight: 600; color: #86868B;
        text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 0.4rem;
    }
    .insight-card {
        background: #FFFFFF; border: 1px solid #E5E5E7; border-left: 4px solid #0071E3;
        border-radius: 10px; padding: 1rem 1.2rem; margin-top: 0.9rem; line-height: 1.55;
    }
    .footer-note { font-size: 0.78rem; color: #86868B; text-align: center; margin-top: 2.5rem; }

    /* Style Streamlit's own bordered containers as the "cards", instead
       of manually-inserted divs - avoids the empty stray-box bug since
       this targets Streamlit's real container element directly. */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Load data -------------------------------------------------------
@st.cache_data
def load_data():
    """Load the daily summary built from real Apple Watch data."""
    return pd.read_csv("daily_summary.csv", parse_dates=["date"])


if not os.path.exists("daily_summary.csv"):
    st.error(
        "daily_summary.csv not found. Build it from an Apple Health export with:\n\n"
        "`python parse_health_data.py` then `python build_daily_summary.py`"
    )
    st.stop()

df = load_data()

# --- Header ------------------------------------------------------------
st.markdown('<p class="dash-title">⌚ Wearable Health Insights</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="dash-subtitle">A wellness trend tool built from personal Apple Watch data — '
    'Python for the data pipeline and dashboard, MATLAB for the statistical analysis. '
    'This surfaces patterns over time; it does not diagnose or flag medical conditions.</p>',
    unsafe_allow_html=True,
)

# --- Sidebar: date range filter ----------------------------------------
st.sidebar.markdown("### Filters")
min_date, max_date = df["date"].min(), df["date"].max()
date_range = st.sidebar.date_input(
    "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date,
)

if len(date_range) == 2:
    start, end = date_range
    filtered = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
else:
    filtered = df

# Guard against an empty selection (e.g. a single-day range with no data)
# so the metric/chart code below never indexes into an empty frame.
if filtered.empty:
    st.warning("No data in the selected date range. Try widening the filter.")
    st.stop()

# --- Top-line summary metrics: averages across the selected range --------
# Each card shows the average for the selected window (not a single day, which
# is noisy and can be a partial, still-syncing day), with the daily low-high
# range underneath so the spread is obvious at a glance. The direction of the
# trend over time is left to the line charts below.
period_label = f"{filtered['date'].min():%b %d} – {filtered['date'].max():%b %d}"
st.markdown(
    f'<p class="cards-caption">Averages across the selected range ({period_label}). '
    "The smaller line shows each metric's daily low–high.</p>",
    unsafe_allow_html=True,
)


def render_metric(col, label, value, sub=None):
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ""
    col.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def fmt(value, spec, fallback="N/A"):
    """Format a value, returning a fallback when it is missing (NaN)."""
    return format(value, spec) if pd.notna(value) else fallback


def rng(col, spec):
    """Daily low-high range string for a column over the selected window."""
    lo, hi = filtered[col].min(), filtered[col].max()
    if pd.isna(lo) or pd.isna(hi):
        return None
    return f"range {format(lo, spec)}–{format(hi, spec)}"


col1, col2, col3, col4 = st.columns(4)
render_metric(col1, "Avg Heart Rate", f"{fmt(filtered['avg_hr'].mean(), '.0f')} bpm",
              rng("avg_hr", ".0f"))
render_metric(col2, "Resting HR", f"{fmt(filtered['resting_hr'].mean(), '.0f')} bpm",
              rng("resting_hr", ".0f"))
render_metric(col3, "Steps", f"{fmt(filtered['total_steps'].mean(), ',.0f')}",
              rng("total_steps", ",.0f"))
render_metric(col4, "Active Energy", f"{fmt(filtered['active_energy_kcal'].mean(), '.0f')} kcal",
              rng("active_energy_kcal", ".0f"))

st.divider()

# --- Heart rate trend chart -----------------------------------------------
st.markdown(
    '<div class="section-label"><div class="section-bar blue"></div>'
    '<p class="section-title">Heart Rate Trends</p></div>',
    unsafe_allow_html=True,
)
with st.container(border=True):
    hr_chart_data = filtered.set_index("date")[["avg_hr", "min_hr", "max_hr", "resting_hr"]]
    hr_chart_data.columns = ["Average HR", "Min HR", "Max HR", "Resting HR"]
    st.line_chart(hr_chart_data, color=["#0071E3", "#9BC9F2", "#E8503A", "#F2B9AE"])

st.divider()

# --- Activity trends -------------------------------------------------------
st.markdown(
    '<div class="section-label"><div class="section-bar coral"></div>'
    '<p class="section-title">Activity Trends</p></div>',
    unsafe_allow_html=True,
)
act_col1, act_col2 = st.columns(2)
with act_col1:
    with st.container(border=True):
        st.markdown('<div class="chart-caption">Daily Steps</div>', unsafe_allow_html=True)
        st.bar_chart(filtered.set_index("date")[["total_steps"]], color="#0071E3")
with act_col2:
    with st.container(border=True):
        st.markdown('<div class="chart-caption">Active Energy Burned (kcal)</div>', unsafe_allow_html=True)
        st.bar_chart(filtered.set_index("date")[["active_energy_kcal"]], color="#E8503A")

st.divider()

# --- MATLAB correlation analysis -------------------------------------
st.markdown(
    '<div class="section-label"><div class="section-bar blue"></div>'
    '<p class="section-title">Statistical Analysis: Activity vs Heart Rate</p></div>',
    unsafe_allow_html=True,
)
st.caption(
    "This analysis was performed in MATLAB using the Statistics and "
    "Machine Learning Toolbox (correlation + linear regression). MATLAB "
    "runs this separately - this dashboard simply shows its saved output. "
    "The trend charts above and this figure are drawn from the same real "
    "recorded period."
)

if os.path.exists("energy_vs_hr_correlation.png"):
    with st.container(border=True):
        st.image("energy_vs_hr_correlation.png",
                 caption="Active Energy Burned vs Average Heart Rate (R=0.536, p<0.001)")
    st.markdown(
        '<div class="insight-card"><b>Interpretation:</b> Active energy burned shows a '
        "statistically significant positive correlation with average heart rate "
        "(R-squared ≈ 0.29), meaning days with more energy burned tend to have higher "
        "average heart rates. This makes physiological sense - active energy captures "
        "workout intensity, not just movement volume, so it tracks more closely with "
        "heart rate than simple step count does.</div>",
        unsafe_allow_html=True,
    )
else:
    st.info("Run correlation_analysis.m in MATLAB to generate this plot.")

# --- Raw data, for transparency ----------------------------------------
with st.expander("View underlying daily data"):
    st.dataframe(filtered, width="stretch")

st.markdown(
    '<p class="footer-note">Built with Python, pandas, Streamlit, and MATLAB.</p>',
    unsafe_allow_html=True,
)
