# Weather Explorer

Search live weather for any city, see a 5-day forecast, compare cities, and save data to CSV.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
```
Open `.env` and paste your free key from https://openweathermap.org/api
(new keys can take up to a few hours to activate).

## Run
```bash
streamlit run app.py            # interactive web app
python main.py --history        # batch-collect 8 Indian cities into CSV
```

## Files
- `weather_core.py` - API calls, cleaning, validation, CSV saving (shared)
- `app.py` - Streamlit UI (Search / Compare / Saved data tabs)
- `main.py` - command-line collector
- `data/` - generated CSVs (weather_data, weather_history, search_log)
