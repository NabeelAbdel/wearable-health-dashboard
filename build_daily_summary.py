"""
build_daily_summary.py

Turns the raw, reading-by-reading CSVs (one row per sensor sample) into the
two small, day-level tables the dashboard reads:

    daily_summary.csv   one row per day   - heart rate, zones, activity, HRV, VO2max, signal quality
    hourly_hr.csv       one row per hour  - time-weighted HR by date x hour (circadian view)
    sampling_profile.csv  histogram of the gaps between HR samples (sensor duty-cycle view)

Why this file does more than a simple groupby().mean()
------------------------------------------------------
The Apple Watch does NOT sample heart rate at a fixed rate. During a workout
it records roughly every 5 seconds; at rest it records every few minutes;
on the charger it records nothing. A plain average of the samples therefore
over-weights exercise (thousands of dense workout samples swamp a few dozen
resting samples). On this dataset that inflates the daily mean by ~15 bpm.

The fix is a TIME-WEIGHTED mean: each sample is weighted by how long it is
"in force" (the gap until the next sample, capped so that hours with the
watch off do not count). This is the standard way to average a signal that
was sampled non-uniformly - it approximates the integral of HR over time
divided by the monitored time.

Everything else here (heart-rate zones, monitored hours, training load)
falls out of the same per-sample duration, so it is computed once.

Author: Nabeel Abdel
"""

import os

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOCAL_TZ = "America/Los_Angeles"   # Apple stamps every reading with a UTC offset;
                                   # we bucket days in the wearer's local time so
                                   # an evening run is not pushed into "tomorrow".
WATCH_START_DATE = "2026-05-05"    # First day with consistent Apple Watch data.
MAX_SAMPLE_HOLD_SEC = 600          # A sample is assumed valid for at most 10 min.
                                   # Longer gaps = watch off / charging = unmonitored.
WORKOUT_GAP_SEC = 15               # Samples <=15 s apart only happen in workout mode.

AGE_YEARS = 20
HR_MAX = 220 - AGE_YEARS           # Fox formula. Simple, widely used, and the
                                   # dashboard lets the viewer override it.

# Standard five-zone model expressed as a fraction of HRmax.
# Zone 1 = 50-60 %, Zone 2 = 60-70 %, ... Zone 5 = 90-100 %.
ZONE_EDGES = [0.50, 0.60, 0.70, 0.80, 0.90, np.inf]
ZONE_NAMES = ["zone1_min", "zone2_min", "zone3_min", "zone4_min", "zone5_min"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_local(csv_path: str) -> pd.DataFrame:
    """Read a raw export CSV and add local-time 'ts' and 'date' columns."""
    df = pd.read_csv(csv_path)
    # utc=True parses the mixed "-07:00" offsets correctly; tz_convert then
    # moves every timestamp into the wearer's local clock before we take .date
    ts = pd.to_datetime(df["start_date"], utc=True).dt.tz_convert(LOCAL_TZ)
    df["ts"] = ts
    df["date"] = ts.dt.date
    return df.sort_values("ts").reset_index(drop=True)


def add_sample_durations(hr: pd.DataFrame) -> pd.DataFrame:
    """
    For each HR sample, compute how long it is 'in force':
    the gap to the next sample, capped at MAX_SAMPLE_HOLD_SEC.
    Also flag workout-mode samples (dense, <= WORKOUT_GAP_SEC apart).
    """
    gap = hr["ts"].shift(-1).sub(hr["ts"]).dt.total_seconds()
    hr["gap_sec"] = gap
    hr["dur_sec"] = gap.clip(upper=MAX_SAMPLE_HOLD_SEC).fillna(0.0)
    hr["is_workout_mode"] = gap <= WORKOUT_GAP_SEC
    hr["zone"] = pd.cut(hr["value"] / HR_MAX, bins=ZONE_EDGES, labels=ZONE_NAMES,
                        right=False)  # below 50 % HRmax -> NaN -> "rest"
    return hr


def time_weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    w = weights.sum()
    return float((values * weights).sum() / w) if w > 0 else np.nan


def summarise_heart_rate(hr: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-sample HR rows into one row per day."""
    rows = []
    for date, d in hr.groupby("date"):
        dur = d["dur_sec"]
        zone_min = (d.groupby("zone", observed=False)["dur_sec"].sum() / 60.0)
        rows.append({
            "date": date,
            # Two versions of "average HR" so the bias is visible in the data:
            "avg_hr_naive": d["value"].mean(),            # plain mean of samples
            "avg_hr": time_weighted_mean(d["value"], dur),  # time-weighted (correct)
            "min_hr": d["value"].min(),
            "max_hr": d["value"].max(),
            "hr_samples": len(d),
            "monitored_hours": dur.sum() / 3600.0,
            "workout_minutes": d.loc[d["is_workout_mode"], "dur_sec"].sum() / 60.0,
            # Edwards' TRIMP: minutes in zone k x k, k = 1..5. A simple, published
            # training-load score that rewards intensity, not just duration.
            "trimp_edwards": sum((k + 1) * zone_min.get(name, 0.0)
                                 for k, name in enumerate(ZONE_NAMES)),
            **{name: zone_min.get(name, 0.0) for name in ZONE_NAMES},
        })
    return pd.DataFrame(rows)


def summarise_hourly(hr: pd.DataFrame) -> pd.DataFrame:
    """Time-weighted HR for every (date, hour) cell - feeds the circadian heatmap."""
    hr = hr.assign(hour=hr["ts"].dt.hour)
    out = (hr.groupby(["date", "hour"])
             .apply(lambda d: pd.Series({
                 "hr_tw": time_weighted_mean(d["value"], d["dur_sec"]),
                 "monitored_min": d["dur_sec"].sum() / 60.0,
                 "samples": len(d),
             }), include_groups=False)
             .reset_index())
    out["date"] = pd.to_datetime(out["date"])
    return out


def sampling_profile(hr: pd.DataFrame) -> pd.DataFrame:
    """
    Histogram of the time between consecutive HR samples. This is the sensor's
    duty cycle made visible: a spike at ~5 s is workout mode, a hump at several
    minutes is background monitoring, anything over 10 min is the watch off.
    """
    edges = [0, 10, 30, 60, 300, 600, 3600, np.inf]
    labels = ["<=10 s", "10-30 s", "30-60 s", "1-5 min", "5-10 min", "10-60 min", "> 1 h"]
    binned = pd.cut(hr["gap_sec"].dropna(), bins=edges, labels=labels, right=True)
    counts = binned.value_counts().reindex(labels, fill_value=0)
    return pd.DataFrame({"gap_bucket": labels, "samples": counts.values,
                         "share": (counts.values / counts.sum()).round(4)})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    hr = add_sample_durations(load_local("heart_rate.csv"))
    steps = load_local("steps.csv")
    energy = load_local("active_energy.csv")
    resting = load_local("resting_heart_rate.csv")

    daily_hr = summarise_heart_rate(hr)

    daily_steps = steps.groupby("date")["value"].sum().rename("total_steps").reset_index()
    daily_energy = energy.groupby("date")["value"].sum().rename("active_energy_kcal").reset_index()
    # Apple writes one resting-HR estimate per day; mean() just collapses duplicates.
    daily_resting = resting.groupby("date")["value"].mean().rename("resting_hr").reset_index()

    daily = (daily_hr.merge(daily_steps, on="date", how="outer")
                     .merge(daily_energy, on="date", how="outer")
                     .merge(daily_resting, on="date", how="outer"))

    # Optional metrics - only present if the Watch recorded them in this export.
    # HRV (SDNN) is Apple's standard-deviation-of-beat-intervals, measured in
    # short windows a few times a day; VO2max is Apple's estimate, updated
    # after qualifying outdoor walks/runs. Both collapse to one value per day.
    for csv_name, col in (("hrv_sdnn.csv", "hrv_sdnn_ms"), ("vo2_max.csv", "vo2_max")):
        if os.path.exists(csv_name):
            extra = load_local(csv_name).groupby("date")["value"].mean().rename(col).reset_index()
            daily = daily.merge(extra, on="date", how="outer")
        else:
            daily[col] = np.nan
            print(f"{csv_name} not found - {col} column left empty")

    daily = daily.sort_values("date")

    # Scope to the Watch period: before it there is only sparse iPhone step data.
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily[daily["date"] >= WATCH_START_DATE].reset_index(drop=True)

    # Signal-quality flag: a day that HAS heart-rate data but < 2 h of monitored
    # time is too thin to trust its daily averages. Kept as a column so the
    # dashboard can grey it out rather than silently dropping it. Days with no
    # heart-rate data at all (watch not worn) simply have NaN heart-rate columns.
    daily["low_coverage"] = daily["monitored_hours"].notna() & (daily["monitored_hours"] < 2.0)

    num = daily.select_dtypes("number").columns
    daily[num] = daily[num].round(3)
    daily.to_csv("daily_summary.csv", index=False)

    hourly = summarise_hourly(hr)
    hourly = hourly[hourly["date"] >= WATCH_START_DATE].copy()
    hourly[["hr_tw", "monitored_min"]] = hourly[["hr_tw", "monitored_min"]].round(3)
    hourly.to_csv("hourly_hr.csv", index=False)

    sampling_profile(hr).to_csv("sampling_profile.csv", index=False)

    # ---- console report -------------------------------------------------
    with_hr = daily.dropna(subset=["avg_hr"])
    bias = (with_hr["avg_hr_naive"] - with_hr["avg_hr"]).mean()
    print(f"Built daily_summary.csv: {len(daily)} days ({daily['date'].min():%Y-%m-%d} "
          f"to {daily['date'].max():%Y-%m-%d}), {len(with_hr)} with heart-rate data")
    print(f"Built hourly_hr.csv:     {len(hourly)} date x hour cells")
    print("Built sampling_profile.csv")
    print(f"HRmax used for zones:    {HR_MAX} bpm (220 - {AGE_YEARS})")
    print(f"Mean sampling bias:      naive mean exceeds time-weighted mean by {bias:.1f} bpm")
    print(f"Low-coverage days:       {int(daily['low_coverage'].sum())} (HR data but < 2 h)")
    print(f"Days without HR data:    {int(daily['avg_hr'].isna().sum())}")
    print(f"HRV (SDNN) days:         {int(daily['hrv_sdnn_ms'].notna().sum())}")
    print(f"VO2max days:             {int(daily['vo2_max'].notna().sum())}")
    print(daily[["date", "avg_hr_naive", "avg_hr", "monitored_hours",
                 "workout_minutes", "trimp_edwards"]].tail().to_string(index=False))


if __name__ == "__main__":
    main()
