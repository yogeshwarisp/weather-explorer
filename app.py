"""app.py - Streamlit weather dashboard. Run:  streamlit run app.py"""

import time

import pandas as pd
import streamlit as st

import weather_core as wc

st.set_page_config(page_title="Weather Explorer", page_icon="🌦️", layout="wide")


# ------------------------------------------------------------ cached calls
@st.cache_data(ttl=300, show_spinner=False)
def get_current(query, key):
    return wc.fetch_current(query, key)


@st.cache_data(ttl=900, show_spinner=False)
def get_forecast(lat, lon, key):
    return wc.fetch_forecast(lat, lon, key)


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = wc.load_api_key()
    try:
        api_key = api_key or st.secrets.get("OPENWEATHER_API_KEY", "")
    except Exception:
        pass
    if not api_key:
        api_key = st.text_input("OpenWeather API key", type="password",
                                help="Or put it in a .env file as OPENWEATHER_API_KEY").strip()
    else:
        st.success("API key loaded ✅")
    save_searches = st.checkbox("Save my searches to CSV", value=True)
    st.caption("Tip: use 'City,CountryCode' for other countries, e.g. London,GB")

st.title("🌦️ Weather Explorer")
st.write("Search any city in the world and get live weather, a 5-day forecast and comparisons.")

if not api_key:
    st.warning("Add your OpenWeather API key in the sidebar (or in a `.env` file) to start.")
    st.stop()

tab_search, tab_compare, tab_history = st.tabs(["🔍 Search city", "📊 Compare cities", "🗂️ Saved data"])

# ------------------------------------------------------------- search tab
with tab_search:
    with st.form("search_form"):
        c1, c2 = st.columns([4, 1])
        query = c1.text_input("City", value=st.session_state.get("last_query", "Pune,IN"),
                              placeholder="e.g. Pune, Tokyo, New York,US")
        c2.write("")
        c2.write("")
        go = c2.form_submit_button("Search", )

    quick = st.columns(len(wc.DEFAULT_CITIES))
    for col, city in zip(quick, wc.DEFAULT_CITIES):
        if col.button(city, key=f"quick_{city}"):
            query, go = city, True

    if go:
        st.session_state["last_query"] = query
        st.session_state["do_search"] = query

    target = st.session_state.get("do_search")
    if target:
        try:
            with st.spinner(f"Fetching weather for {target}..."):
                w = get_current(target, api_key)
                forecast = get_forecast(w["lat"], w["lon"], api_key)
        except wc.WeatherError as e:
            st.error(f"❌ {e}")
        else:
            st.subheader(f"{w['city']}, {w['country']}")
            left, right = st.columns([1, 4])
            left.image(f"https://openweathermap.org/img/wn/{w['icon']}@4x.png", width=120)
            right.markdown(f"### {w['weather_description'].title()}  ·  {w['temperature']:.1f} °C")
            right.caption(f"Updated {w['collected_at']}")

            m = st.columns(5)
            m[0].metric("Feels like", f"{w['feels_like']:.1f} °C")
            m[1].metric("Humidity", f"{w['humidity']} %")
            m[2].metric("Wind", f"{w['wind_speed']} m/s")
            m[3].metric("Pressure", f"{w['pressure']} hPa")
            m[4].metric("Cloudiness", f"{w['cloudiness']} %")
            m2 = st.columns(4)
            m2[0].metric("Min / Max", f"{w['temp_min']:.0f}° / {w['temp_max']:.0f}°")
            if w["visibility_km"] is not None:
                m2[1].metric("Visibility", f"{w['visibility_km']:.1f} km")
            m2[2].metric("Sunrise (local)", w["sunrise"] or "-")
            m2[3].metric("Sunset (local)", w["sunset"] or "-")

            if save_searches:
                wc.log_search({k: w[k] for k in wc.COLUMNS})

            st.markdown("#### 5-day forecast")
            if not forecast.empty:
                chart = forecast.set_index("time")
                a, b = st.columns(2)
                a.caption("Temperature (°C)")
                a.line_chart(chart["temperature"])
                b.caption("Chance of rain (%)")
                b.bar_chart(chart["rain_chance_%"])
                with st.expander("Forecast table"):
                    st.dataframe(forecast, width="stretch", hide_index=True)
            st.map(pd.DataFrame({"lat": [w["lat"]], "lon": [w["lon"]]}), zoom=8)

# ------------------------------------------------------------ compare tab
with tab_compare:
    picks = st.multiselect("Cities", wc.DEFAULT_CITIES, default=wc.DEFAULT_CITIES[:4])
    extra = st.text_input("Add more cities (comma separated)", placeholder="Nagpur, Nashik, Dubai,AE")
    if st.button("Compare"):
        names = picks + [c.strip() for c in extra.split(",") if c.strip()]
        rows, failed = [], {}
        bar = st.progress(0.0)
        for i, name in enumerate(names, 1):
            try:
                w = get_current(name if "," in name or name not in wc.DEFAULT_CITIES else f"{name},IN", api_key)
                rows.append({k: w[k] for k in wc.COLUMNS})
            except wc.WeatherError as e:
                failed[name] = str(e)
            bar.progress(i / len(names))
            time.sleep(0.2)
        for name, err in failed.items():
            st.warning(f"{name}: {err}")
        if rows:
            df, stats = wc.clean_and_validate(pd.DataFrame(rows, columns=wc.COLUMNS))
            st.dataframe(df, width="stretch", hide_index=True)
            st.bar_chart(df.set_index("city")[["temperature", "feels_like"]])
            st.bar_chart(df.set_index("city")["humidity"])
            st.download_button("⬇️ Download CSV", df.to_csv(index=False), "comparison.csv", "text/csv")

# ------------------------------------------------------------ saved tab
with tab_history:
    if wc.SEARCH_LOG_CSV.exists():
        log = pd.read_csv(wc.SEARCH_LOG_CSV)
        st.write(f"**{len(log)}** saved searches")
        st.dataframe(log.sort_values("collected_at", ascending=False), width="stretch", hide_index=True)
        cities = sorted(log["city"].unique())
        sel = st.selectbox("Temperature trend for", cities)
        trend = log[log["city"] == sel].set_index("collected_at")["temperature"]
        if len(trend) > 1:
            st.line_chart(trend)
        else:
            st.caption("Search this city a few more times (at different times) to see a trend.")
        st.download_button("⬇️ Download search log", log.to_csv(index=False), "search_log.csv", "text/csv")
    else:
        st.info("No saved searches yet. Search a city in the first tab.")
