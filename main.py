"""
main.py - Collect, clean and save weather data for the default Indian cities.

Usage:
    python main.py              -> save data/weather_data.csv
    python main.py --history    -> also append this run to data/weather_history.csv
For the interactive search app run:  streamlit run app.py
"""

import argparse
import json
import sys
import time

import pandas as pd

import weather_core as wc


def main():
    parser = argparse.ArgumentParser(description="Collect real-time weather data.")
    parser.add_argument("--history", action="store_true", help="append this run to data/weather_history.csv")
    args = parser.parse_args()

    api_key = wc.load_api_key()
    if not api_key:
        sys.exit("ERROR: OPENWEATHER_API_KEY not set.\nCreate a .env file (copy .env.example) and add your real key.")

    records, failures = [], {}
    for i, city in enumerate(wc.DEFAULT_CITIES, 1):
        print(f"[{i}/{len(wc.DEFAULT_CITIES)}] Fetching {city}...", end=" ")
        try:
            w = wc.fetch_current(f"{city},IN", api_key)
            w["city"] = city
            records.append({k: w[k] for k in wc.COLUMNS})
            print("OK")
        except wc.WeatherError as e:
            msg = str(e)
            print(f"FAILED ({msg})")
            failures[city] = msg
            if "401" in msg:
                sys.exit("\nERROR: invalid API key - stopping.")
        time.sleep(0.5)

    if not records:
        sys.exit("\nERROR: No data collected. Existing CSV files were left unchanged.")

    df, stats = wc.clean_and_validate(pd.DataFrame(records, columns=wc.COLUMNS))
    if df.empty:
        sys.exit("\nERROR: All records failed validation. Nothing was saved.")

    wc.DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(wc.CURRENT_CSV, index=False, encoding="utf-8")
    added = wc.append_csv(df, wc.HISTORY_CSV) if args.history else 0

    summary = {"cities_requested": len(wc.DEFAULT_CITIES), "cities_collected": len(df),
               "failed_cities": failures, **stats, "history_rows_added": added}
    wc.SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nCollected {len(df)} of {len(wc.DEFAULT_CITIES)} cities -> {wc.CURRENT_CSV}")
    if args.history:
        print(f"History updated -> {wc.HISTORY_CSV} (+{added} rows)")
    if failures:
        print("Failed cities:", ", ".join(failures))


if __name__ == "__main__":
    main()
