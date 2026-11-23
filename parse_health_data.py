"""
parse_health_data.py

Reads Apple Health's raw export.xml and pulls out just the metrics this
project uses, saving each as its own clean CSV (one row per sensor reading).

Why it is written this way
--------------------------
Apple's export.xml can be hundreds of MB and contains *everything* Apple
Health has ever recorded. Loading it with a normal XML parser would build the
whole document tree in memory. Instead we use `iterparse`, which streams the
file element by element: each <Record> is handed to us as soon as its closing
tag is read, we copy out the four attributes we care about, then we clear the
element so memory stays flat no matter how large the export is.

Metrics extracted
-----------------
heart_rate              PPG-derived heart rate samples (bpm)
resting_heart_rate      Apple's once-a-day resting estimate (bpm)
steps                   step counts per short interval
active_energy           active energy burned per short interval (kcal)
hrv_sdnn                heart-rate variability, SDNN (ms)  - present only if the
                        Watch recorded it; used for the recovery view when available
vo2_max                 Apple's estimated VO2max (mL/kg/min) - optional, same note

Usage:
    python parse_health_data.py                     # reads apple_health_export/export.xml
    python parse_health_data.py path/to/export.xml  # custom path

Author: Nabeel Abdel
"""

import sys
import xml.etree.ElementTree as ET

import pandas as pd

# Map Apple's verbose HealthKit identifiers to the short names used downstream.
METRICS_WE_WANT = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
    "HKQuantityTypeIdentifierVO2Max": "vo2_max",
}

DEFAULT_PATH = "apple_health_export/export.xml"


def parse_export(xml_path: str) -> dict[str, list[dict]]:
    """Stream through export.xml and collect rows for each wanted metric."""
    data = {short_name: [] for short_name in METRICS_WE_WANT.values()}
    n_records = 0

    # events=("end",) -> we get each element once it is completely read.
    for _event, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag != "Record":
            continue
        n_records += 1
        short_name = METRICS_WE_WANT.get(elem.get("type"))
        if short_name is not None:
            try:
                value = float(elem.get("value"))
            except (TypeError, ValueError):
                value = None   # a handful of records carry non-numeric values; skip them
            if value is not None:
                data[short_name].append({
                    "value": value,
                    "unit": elem.get("unit"),
                    "start_date": elem.get("startDate"),
                    "end_date": elem.get("endDate"),
                    "source": elem.get("sourceName"),
                })
        # CRITICAL for memory: drop the element once we have what we need.
        elem.clear()

    print(f"Scanned {n_records:,} <Record> elements")
    return data


def main(xml_path: str = DEFAULT_PATH) -> None:
    print(f"Parsing {xml_path} ... this can take a minute for a large export.")
    data = parse_export(xml_path)

    for short_name, rows in data.items():
        if not rows:
            print(f"  {short_name:20s}: not present in this export (skipped)")
            continue
        df = pd.DataFrame(rows)
        # Parse the timestamps so downstream code can sort / group by day.
        # utc=True handles the per-record UTC offsets Apple writes ("-07:00").
        df["start_date"] = pd.to_datetime(df["start_date"], utc=True)
        df = df.sort_values("start_date")
        out_path = f"{short_name}.csv"
        df.to_csv(out_path, index=False)
        print(f"  {short_name:20s}: {len(df):>8,} rows -> {out_path}")

    print("Done.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH)
