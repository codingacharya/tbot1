import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import datetime

from ta.momentum import RSIIndicator, WilliamsRIndicator
from ta.volatility import BollingerBands
from ta.trend import ADXIndicator, SMAIndicator

st.set_page_config("NIFTY Options Algo Bot", layout="wide")

# =====================================================
# CONFIG
# =====================================================
MIN_BARS = 160

# =====================================================
# LOAD STOCKS
# =====================================================
@st.cache_data
def load_stocks():
    df = pd.read_csv("nifty_stocks.csv")
    return df["Stock"].dropna().unique().tolist()

stocks = load_stocks()

# =====================================================
# FETCH DATA (SAFE)
# =====================================================
@st.cache_data
def fetch_data(symbol):
    df = yf.download(
        symbol,
        period="5d",
        interval="5m",
        progress=False,
        auto_adjust=False
    )

    if df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna()

# =====================================================
# INDICATORS (100% SAFE)
# =====================================================
def add_indicators(df):
    df = df.copy()

    close = pd.Series(df["Close"].values.flatten(), index=df.index)
    high  = pd.Series(df["High"].values.flatten(), index=df.index)
    low   = pd.Series(df["Low"].values.flatten(), index=df.index)

    bb60  = BollingerBands(close, window=60)
    bb105 = BollingerBands(close, window=105)
    bb150 = BollingerBands(close, window=150)

    df["BB60"]  = ((bb60.bollinger_hband()  - bb60.bollinger_lband())  / close) * 100
    df["BB105"] = ((bb105.bollinger_hband() - bb105.bollinger_lband()) / close) * 100
    df["BB150"] = ((bb150.bollinger_hband() - bb150.bollinger_lband()) / close) * 100

    df["RSI20"]    = RSIIndicator(close, 20).rsi()
    df["WILLR28"]  = WilliamsRIndicator(high, low, close, 28).williams_r()

    dmi6  = ADXIndicator(high, low, close, 6)
    dmi20 = ADXIndicator(high, low, close, 20)

    df["+DI6"]  = dmi6.adx_pos()
    df["-DI6"]  = dmi6.adx_neg()
    df["+DI20"] = dmi20.adx_pos()
    df["-DI20"] = dmi20.adx_neg()

    df["MA8"] = SMAIndicator(close, 8).sma_indicator()

    return df

# =====================================================
# STRATEGY LOGIC
# =====================================================
def apply_strategy(df):
    df = df.copy()

    for col in ["Close", "MA8", "+DI20", "-DI20"]:
        df[col] = pd.Series(df[col].values.flatten(), index=df.index)

    df["CALL_ENTRY"] = (
        (df["BB60"] <= 35) &
        (df["RSI20"].between(65, 100)) &
        (df["WILLR28"].between(-20, 0)) &
        (df["+DI6"] >= 40) & (df["-DI6"] <= 12) &
        (df["+DI20"] >= 35) & (df["-DI20"] <= 15)
    )

    df["PUT_ENTRY"] = (
        (df["BB60"] <= 35) &
        (df["RSI20"].between(1, 40)) &
        (df["WILLR28"].between(-100, -80)) &
        (df["-DI6"] >= 35) & (df["+DI6"] <= 15) &
        (df["-DI20"] >= 30) & (df["+DI20"] <= 15)
    )

    di_diff = (df["+DI20"] - df["-DI20"]).abs()

    df["CALL_EXIT"] = (di_diff < 10) | (df["Close"] < df["MA8"])
    df["PUT_EXIT"]  = (di_diff < 10) | (df["Close"] > df["MA8"])

    return df

# =====================================================
# PIPELINE
# =====================================================
frames = []

for stock in stocks:
    raw = fetch_data(stock)
    if raw is not None and len(raw) >= MIN_BARS:
        ind = add_indicators(raw)
        ind["Stock"] = stock
        frames.append(ind)

if not frames:
    st.error("❌ No valid data")
    st.stop()

df = pd.concat(frames, ignore_index=True)

df = apply_strategy(df)

df["Time"] = df["Datetime"].dt.time
df = df[df["Time"] >= datetime.time(10, 0)]

# =====================================================
# DASHBOARD
# =====================================================
st.title("📊 NIFTY CALL & PUT Algo Dashboard")

cols = [
    "Stock", "Datetime",
    "BB60", "RSI20", "WILLR28",
    "+DI6", "-DI6", "+DI20", "-DI20"
]

tab1, tab2 = st.tabs(["📈 CALL SIGNALS", "📉 PUT SIGNALS"])

with tab1:
    call_df = df[df["CALL_ENTRY"] & ~df["CALL_EXIT"]]
    st.dataframe(call_df[cols], use_container_width=True)

with tab2:
    put_df = df[df["PUT_ENTRY"] & ~df["PUT_EXIT"]]
    st.dataframe(put_df[cols], use_container_width=True)

st.caption("✅ Fully Stable | TA Safe | Zerodha Ready")
