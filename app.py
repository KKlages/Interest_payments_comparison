import streamlit as st
import pandas as pd
from fredapi import Fred
from datetime import datetime, timedelta
import os # To potentially use environment variables for API key

# --- Configuration ---
# Use Streamlit secrets for API key in deployment (secrets.toml)
# Example secrets.toml:
# [fred]
# api_key = "YOUR_API_KEY_HERE"
# Fallback to environment variable or direct input (less secure for sharing)
try:
    # Try getting API key from Streamlit secrets first
    FRED_API_KEY = "b00c06dbff945a913813d006b4268cca"
except (FileNotFoundError, KeyError):
     # Fallback: Try environment variable
    FRED_API_KEY = os.environ.get("FRED_API_KEY")
    if not FRED_API_KEY:
         # Last resort: Use st.text_input (display warning)
        st.sidebar.warning("Enter your FRED API Key below (Using secrets or environment variables is recommended for security). Get one here: https://fred.stlouisfed.org/docs/api/api_key.html")
        FRED_API_KEY = st.sidebar.text_input("FRED API Key", type="password")


# Define the historical comparison date
HISTORICAL_DATE_STR = "2025-04-01"
HISTORICAL_DATE = pd.to_datetime(HISTORICAL_DATE_STR)

# FRED Series IDs for different US Treasury Constant Maturities (Examples)
# Find more series IDs here: https://fred.stlouisfed.org/categories/115
FRED_SERIES = {
    "3-Month Treasury Bill": "DGS3MO", # Secondary Market Rate
    "1-Year Treasury": "DGS1",
    "5-Year Treasury": "DGS5",
    "10-Year Treasury": "DGS10",
    "30-Year Treasury": "DGS30",
}

# --- Helper Functions ---

@st.cache_data(ttl=3600) # Cache data for 1 hour
def get_fred_rate(_fred_client, series_id, date):
    """Fetches FRED rate for a specific series ID on or just before a given date."""
    # Try fetching data for a small window around the date to handle weekends/holidays
    start_date = date - timedelta(days=7)
    end_date = date
    try:
        data = _fred_client.get_series(series_id, observation_start=start_date, observation_end=end_date)
        # Drop missing values and get the last available data point in the window
        data = data.dropna()
        if not data.empty:
            # Return the rate and the actual date it corresponds to
            return data.iloc[-1], data.index[-1]
        else:
            return None, None # No data found in the window
    except Exception as e:
        st.error(f"Error fetching historical FRED data for {series_id}: {e}")
        return None, None

@st.cache_data(ttl=900) # Cache current data for 15 minutes
def get_current_fred_rate(_fred_client, series_id):
    """Fetches the most recent FRED rate for a series ID."""
    try:
        # Get the most recent data point
        data = _fred_client.get_series(series_id)
        data = data.dropna()
        if not data.empty:
             # Return the rate and the actual date it corresponds to
            return data.iloc[-1], data.index[-1]
        else:
            return None, None
    except Exception as e:
        st.error(f"Error fetching current FRED data for {series_id}: {e}")
        return None, None

# --- Streamlit App UI ---

st.set_page_config(layout="wide")
st.title("🇺🇸 US Refinanced Debt Interest Cost Calculator")
st.markdown(f"""
This app calculates the **additional annual interest cost** the US would face
if it refinanced a certain amount of maturing debt *today* compared to refinancing
it on **{HISTORICAL_DATE_STR}**.

It uses U.S. Treasury constant maturity rates fetched from FRED (Federal Reserve Economic Data).
""")

# --- Input Section ---
st.sidebar.header("Inputs")

# Check if API key is available
if not FRED_API_KEY:
    st.warning("Please enter your FRED API Key in the sidebar to proceed.")
    st.stop() # Stop execution if no API key

# Initialize FRED client (only once API key is confirmed)
try:
    fred = Fred(api_key=FRED_API_KEY)
except Exception as e:
    st.error(f"Failed to initialize FRED client. Check your API key. Error: {e}")
    st.stop()


# Maturity Selection
selected_maturity_name = st.sidebar.selectbox(
    "Select Treasury Maturity for Rate Comparison:",
    options=list(FRED_SERIES.keys()),
    index=3 # Default to 10-Year Treasury
)
selected_series_id = FRED_SERIES[selected_maturity_name]

# Debt Amount Input
debt_amount_billions = st.sidebar.number_input(
    "Amount of Debt to Refinance (in Billions USD):",
    min_value=1.0,
    value=100.0,
    step=10.0,
    format="%.1f"
)
debt_amount = debt_amount_billions * 1_000_000_000 # Convert to dollars

# --- Calculation and Display Section ---
st.header("Results")

col1, col2, col3 = st.columns(3)

# Fetch Historical Rate
historical_rate, historical_rate_date = get_fred_rate(fred, selected_series_id, HISTORICAL_DATE)
with col1:
    st.subheader(f"Rate on {HISTORICAL_DATE_STR}")
    if historical_rate is not None:
        st.metric(label=f"{selected_maturity_name} Yield (as of {historical_rate_date.strftime('%Y-%m-%d')})",
                  value=f"{historical_rate:.2f}%")
    else:
        st.error(f"Could not retrieve rate for {HISTORICAL_DATE_STR}.")

# Fetch Current Rate
current_rate, current_rate_date = get_current_fred_rate(fred, selected_series_id)
with col2:
    st.subheader("Current Rate")
    if current_rate is not None:
        st.metric(label=f"{selected_maturity_name} Yield (as of {current_rate_date.strftime('%Y-%m-%d')})",
                  value=f"{current_rate:.2f}%")
    else:
        st.error("Could not retrieve the current rate.")

# Calculate Difference
with col3:
    st.subheader("Rate Difference")
    if historical_rate is not None and current_rate is not None:
        rate_difference = current_rate - historical_rate
        st.metric(label="Change in Yield",
                  value=f"{rate_difference:.2f}%",
                  delta=f"{rate_difference:.2f}% pts") # Use delta for visual indication
    else:
        st.info("Cannot calculate difference without both rates.")

st.divider() # Visual separator

st.subheader("Interest Cost Calculation")

if historical_rate is not None and current_rate is not None:
    # Calculate interest costs
    # Convert percentage rates to decimals for calculation
    historical_interest_cost = debt_amount * (historical_rate / 100)
    current_interest_cost = debt_amount * (current_rate / 100)
    additional_cost = current_interest_cost - historical_interest_cost

    st.write(f"For refinancing **${debt_amount_billions:,.1f} billion** of debt:")

    cost_col1, cost_col2, cost_col3 = st.columns(3)

    with cost_col1:
        st.metric(label=f"Est. Annual Interest Cost at {historical_rate:.2f}%",
                  value=f"${historical_interest_cost:,.2f}")

    with cost_col2:
        st.metric(label=f"Est. Annual Interest Cost at {current_rate:.2f}%",
                  value=f"${current_interest_cost:,.2f}")

    with cost_col3:
        # Determine delta color based on increase/decrease
        delta_color = "inverse" if additional_cost < 0 else "normal"
        st.metric(label="Additional Annual Interest Cost",
                  value=f"${additional_cost:,.2f}",
                  delta=f"${additional_cost:,.2f}",
                  delta_color=delta_color)

    st.markdown(f"""
    *This calculation assumes the entire debt amount is refinanced using the **{selected_maturity_name}** rate.*
    *Positive additional cost means current rates are higher than on {HISTORICAL_DATE_STR}, leading to higher interest payments.*
    *Negative additional cost means current rates are lower.*
    """)

else:
    st.warning("Interest cost cannot be calculated because one or both rates are missing.")

st.markdown("---")
st.caption(f"Data sourced from FRED. Historical rate target date: {HISTORICAL_DATE_STR}. Current rate fetched: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Rate data may have a slight reporting lag.")

