"""
parse_health_data.py

Reads Apple Health's raw export.xml and pulls out only the four metrics
this dashboard uses (heart rate, steps, resting heart rate, active
energy), saving each as its own clean CSV file.

Why it is built this way:
Apple's export.xml can be hundreds of MB and contains *everything* Apple
Health has ever recorded. Loading the whole file into memory at once
would be slow and memory-heavy. Instead this script uses `iterparse`,
which reads the file piece by piece, processes each <Record> as it is
found, then discards it before moving on. Memory usage stays flat no
matter how big the file is.

Author: Nabeel Abdel
"""

import xml.etree.ElementTree as ET
import pandas as pd

# Map Apple's verbose internal type names to the short names used here.
WANTED_METRICS = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
}


def parse_export(xml_path):
    # One empty list per metric, to collect rows before turning into a DataFrame.
    data = {short_name: [] for short_name in WANTED_METRICS.values()}

    # iterparse streams through the file. The "end" event hands back an element
    # once its closing tag is reached, so all of its attributes are fully read.
    context = ET.iterparse(xml_path, events=("end",))

    for event, elem in context:
        if elem.tag == "Record":
            record_type = elem.get("type")
            if record_type in WANTED_METRICS:
                short_name = WANTED_METRICS[record_type]
                data[short_name].append({
                    "value": float(elem.get("value")),
                    "unit": elem.get("unit"),
                    "start_date": elem.get("startDate"),
                    "end_date": elem.get("endDate"),
                    "source": elem.get("sourceName"),
                })

            # Critical for memory: once the needed fields are pulled from this
            # element, clear it. Without this, iterparse still builds up the
            # whole tree internally and the streaming benefit is lost.
            elem.clear()

    return data


if __name__ == "__main__":
    print("Parsing export.xml... this may take a minute for a large file.")
    data = parse_export("apple_health_export/export.xml")

    for short_name, rows in data.items():
        df = pd.DataFrame(rows)
        # Convert the date strings into real datetime objects so the data can
        # later be sorted, filtered, and grouped by day/week easily.
        df["start_date"] = pd.to_datetime(df["start_date"])
        df = df.sort_values("start_date")

        out_path = f"{short_name}.csv"
        df.to_csv(out_path, index=False)
        print(f"  {short_name}: {len(df)} rows -> {out_path}")

    print("Done.")
