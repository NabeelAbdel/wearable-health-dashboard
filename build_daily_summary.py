"""
build_daily_summary.py

Takes the raw, minute-by-minute CSVs (one row per sensor reading) and
collapses them into one row per day - the shape a dashboard actually
needs. Nobody wants to see 19,000 individual heart rate dots; they want
to see "what was my average heart rate each day this month."

Author: Nabeel Abdel
"""

import pandas as pd


def load_and_date(csv_path):
    """Read a CSV and add a clean 'date' column (just the day, no time)."""
    df = pd.read_csv(csv_path)
    df["start_date"] = pd.to_datetime(df["start_date"], utc=True)
    # .dt.date strips the time off, leaving just the calendar day - the key
    # to group by, so "all readings from June 15th" land in one bucket.
    df["date"] = df["start_date"].dt.date
    return df


def main():
    hr = load_and_date("heart_rate.csv")
    steps = load_and_date("steps.csv")
    energy = load_and_date("active_energy.csv")
    resting = load_and_date("resting_heart_rate.csv")

    # groupby("date") clusters all rows sharing the same day.
    # .agg(...) then tells pandas which math to do on each cluster.
    daily_hr = hr.groupby("date")["value"].agg(
        avg_hr="mean", min_hr="min", max_hr="max"
    ).reset_index()

    daily_steps = steps.groupby("date")["value"].sum().reset_index()
    daily_steps.columns = ["date", "total_steps"]

    daily_energy = energy.groupby("date")["value"].sum().reset_index()
    daily_energy.columns = ["date", "active_energy_kcal"]

    daily_resting = resting.groupby("date")["value"].mean().reset_index()
    daily_resting.columns = ["date", "resting_hr"]

    # Merge stitches the separate daily tables together into one,
    # matching rows up by their shared "date" column.
    # how="outer" keeps every day that appears in ANY of the tables,
    # even if another metric is missing data for that day.
    daily = daily_hr.merge(daily_steps, on="date", how="outer")
    daily = daily.merge(daily_energy, on="date", how="outer")
    daily = daily.merge(daily_resting, on="date", how="outer")

    daily = daily.sort_values("date")

    # Scope to the period with consistent Apple Watch data. Before this date
    # there is only sporadic iPhone step data and no heart rate - mostly empty
    # rows that would just be noise in the dashboard. Applying the filter here,
    # at the presentation boundary, keeps the earlier aggregation logic clean.
    WATCH_START_DATE = "2026-05-05"
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily[daily["date"] >= WATCH_START_DATE]

    daily.to_csv("daily_summary.csv", index=False)
    print(f"Built daily_summary.csv with {len(daily)} days of data (scoped to Watch period)")
    print(daily.tail())


if __name__ == "__main__":
    main()
