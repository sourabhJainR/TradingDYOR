import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="TradingDYOR",layout="wide")
st.title("TradingDYOR")
st.caption("Evidence-first research, multi-strategy validation and adaptive reassessment.")

api=st.sidebar.text_input("API", "http://127.0.0.1:8000")
ticker=st.sidebar.text_input("Ticker","MSFT").upper()
price=st.sidebar.number_input("Price",0.0,100000.0,500.0)
pe=st.sidebar.number_input("P/E",0.0,1000.0,30.0)
rev=st.sidebar.number_input("Revenue growth", -2.0,5.0,0.15)
earn=st.sidebar.number_input("Earnings growth", -2.0,5.0,0.20)
roe=st.sidebar.number_input("ROE", -2.0,5.0,0.20)
de=st.sidebar.number_input("Debt/equity",0.0,20.0,0.5)
mom=st.sidebar.number_input("12m momentum",-2.0,5.0,0.15)
vol=st.sidebar.number_input("90d volatility",0.0,5.0,0.30)
coverage=st.sidebar.slider("Evidence coverage",0.0,1.0,0.80)

if st.button("Evaluate"):
    payload={"ticker":ticker,"price":price,"pe":pe,"revenue_growth":rev,"earnings_growth":earn,
             "roe":roe,"debt_to_equity":de,"momentum_12m":mom,"volatility_90d":vol,
             "evidence_coverage":coverage}
    r=requests.post(f"{api}/research/score",json=payload,timeout=30)
    r.raise_for_status()
    d=r.json()
    c1,c2,c3=st.columns(3)
    c1.metric("Action",d["action"])
    c2.metric("Score",f'{d["score"]:+.2f}')
    c3.metric("Confidence",f'{d["confidence"]:.0%}')
    st.subheader("Evidence and model reasons")
    st.write(d["key_reasons"])
    st.subheader("Risks")
    st.write(d["risks"])
    st.subheader("Invalidation")
    st.write(d["invalidation"])

st.divider()
st.subheader("Production roadmap")
st.write("Browser collection -> point-in-time store -> universe scan -> walk-forward backtests -> monthly learning -> Top 5 Buy/Hold/Sell evidence views.")
