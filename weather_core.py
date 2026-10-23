"""weather_core.py - shared logic used by both main.py (CLI) and app.py (Streamlit)."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CURRENT_CSV = DATA_DIR / "weather_data.csv"
HISTORY_CSV = DATA_DIR / "weather_history.csv"
SEARCH_LOG_CSV = DATA_DIR / "search_log.csv"
SUMMARY_JSON = DATA_DIR / "collection_summary.json"

CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
TIMEOUT = 10
PLACEHOLDER_KEY = "your_api_key_here"

DEFAULT_CITIES = [
    "Pune", "Mumbai", "Delhi", "Bengaluru",
    "Hyderabad", "Chennai", "Kolkata", "Jaipur",
]

COLUMNS = [
    "city", "temperature", "feels_like", "humidity", "pressure",
    "wind_speed", "cloudiness", "weather_description", "collected_at",
]
NUMERIC_COLUMNS = ["temperature", "feels_like", "humidity", "pressure", "wind_speed", "cloudiness"]
VALID_RANGES = {
    "temperature": (-50, 60), "feels_like": (-70, 70), "humidity": (0, 100),
    "pressure": (800, 1100), "wind_speed": (0, 100), "cloudiness": (0, 100),
}


class WeatherError(Exception):
    """Any problem fetching weather. The message is safe to show to the user."""


def load_api_key():
    load_dotenv(BASE_DIR / ".env")
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    return "" if key == PLACEHOLDER_KEY else key


def _get(url, params):
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise WeatherError("Request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise WeatherError("Connection failed. Check your internet.")
    except requests.exceptions.RequestException as e:
        raise WeatherError(f"Request error: {e}")

    if r.status_code == 401:
        raise WeatherError("API key rejected (401). Check the key; new keys can take up to a few hours to activate.")
    if r.status_code == 404:
        raise WeatherError("City not found. Try a different spelling, or use 'City,CountryCode' (e.g. Paris,FR).")
    if r.status_code == 429:
        raise WeatherError("API rate limit reached. Wait a minute and retry.")
    if r.status_code != 200:
        raise WeatherError(f"Unexpected API response (HTTP {r.status_code}).")
    try:
        return r.json()
    except ValueError:
        raise WeatherError("API returned unreadable data.")


def fetch_current(query, api_key):
    """Current weather for ANY city. `query` can be 'Pune', 'Pune,IN', 'London,GB'."""
    query = query.strip()
    if not query:
        raise WeatherError("Please type a city name.")
    data = _get(CURRENT_URL, {"q": query, "appid": api_key, "units": "metric"})
    try:
        main, wind = data.get("main", {}), data.get("wind", {})
        tz = data.get("timezone", 0)
        local = lambda ts: (datetime.fromtimestamp(ts, timezone.utc) + timedelta(seconds=tz)).strftime("%H:%M")
        sys_ = data.get("sys", {})
        return {
            "city": data["name"],
            "country": sys_.get("country", ""),
            "lat": data["coord"]["lat"],
            "lon": data["coord"]["lon"],
            "temperature": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "temp_min": main.get("temp_min"),
            "temp_max": main.get("temp_max"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
            "wind_speed": wind.get("speed"),
            "cloudiness": data.get("clouds", {}).get("all"),
            "visibility_km": (data["visibility"] / 1000) if "visibility" in data else None,
            "weather_description": data["weather"][0]["description"],
            "icon": data["weather"][0]["icon"],
            "sunrise": local(sys_["sunrise"]) if "sunrise" in sys_ else None,
            "sunset": local(sys_["sunset"]) if "sunset" in sys_ else None,
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except (KeyError, IndexError, TypeError):
        raise WeatherError("Response could not be read (unexpected format).")


def fetch_forecast(lat, lon, api_key):
    """5-day / 3-hour forecast as a DataFrame."""
    data = _get(FORECAST_URL, {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"})
    rows = []
    for item in data.get("list", []):
        rows.append({
            "time": pd.to_datetime(item["dt_txt"]),
            "temperature": item["main"]["temp"],
            "humidity": item["main"]["humidity"],
            "wind_speed": item["wind"]["speed"],
            "rain_chance_%": round(item.get("pop", 0) * 100),
            "description": item["weather"][0]["description"],
        })
    return pd.DataFrame(rows)


def clean_and_validate(df):
    """Clean + validate a DataFrame of weather records. Returns (clean_df, stats)."""
    stats = {}
    df = df.copy()
    df["city"] = df["city"].astype(str).str.strip()
    df["weather_description"] = df["weather_description"].fillna("unknown").astype(str).str.strip().str.lower()
    for c in NUMERIC_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].replace([np.inf, -np.inf], np.nan).astype(np.float64)

    n = len(df)
    df = df.drop_duplicates(subset=["city", "collected_at"])
    stats["duplicates_removed"] = n - len(df)

    n = len(df)
    df = df.dropna(subset=NUMERIC_COLUMNS)
    stats["rows_dropped_missing"] = n - len(df)

    ok = pd.Series(True, index=df.index)
    for c, (lo, hi) in VALID_RANGES.items():
        ok &= df[c].between(lo, hi)
    stats["rows_dropped_invalid"] = int((~ok).sum())
    return df[ok].reset_index(drop=True)[COLUMNS], stats


def append_csv(df, path):
    """Append rows to a CSV, skipping (city, collected_at) pairs already stored."""
    DATA_DIR.mkdir(exist_ok=True)
    new = df
    exists = path.exists()
    if exists:
        old = pd.read_csv(path, encoding="utf-8")
        known = set(zip(old["city"], old["collected_at"]))
        new = df[[(c, t) not in known for c, t in zip(df["city"], df["collected_at"])]]
    if new.empty:
        return 0
    new.to_csv(path, mode="a", header=not exists, index=False, encoding="utf-8")
    return len(new)


def log_search(record):
    """Save a user's searched city (cleaned) to data/search_log.csv."""
    df, _ = clean_and_validate(pd.DataFrame([record], columns=COLUMNS))
    return append_csv(df, SEARCH_LOG_CSV) if not df.empty else 0
