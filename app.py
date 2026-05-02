import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os

st.set_page_config(layout="wide")

DATA_FILE = "portfolio.json"
TODAY = datetime.today()

# -------------------------
# LOAD / SAVE
# -------------------------
def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_json(DATA_FILE)
        for col in ["date1","date2","maturity"]:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    return pd.DataFrame(columns=[
        "name","quantity","coupon","date1","date2","maturity","nominal"
    ])

def save_data(df):
    df.to_json(DATA_FILE)

portfolio = load_data()

# -------------------------
# ADD
# -------------------------
st.sidebar.header("➕ Додати ОВДП")

name = st.sidebar.text_input("Назва")
qty = st.sidebar.number_input("Кількість", 0)
coupon = st.sidebar.number_input("Купон", 0)
d1 = st.sidebar.date_input("Дата 1")
d2 = st.sidebar.date_input("Дата 2")
mat = st.sidebar.date_input("Погашення")
nominal = st.sidebar.number_input("Номінал", 1000)

if st.sidebar.button("Додати"):
    new = pd.DataFrame([{
        "name": name,
        "quantity": qty,
        "coupon": coupon,
        "date1": pd.to_datetime(d1),
        "date2": pd.to_datetime(d2),
        "maturity": pd.to_datetime(mat),
        "nominal": nominal
    }])
    portfolio = pd.concat([portfolio, new], ignore_index=True)
    save_data(portfolio)

# -------------------------
# IMPORT
# -------------------------
file = st.sidebar.file_uploader("📥 Імпорт Excel")

if file:
    df = pd.read_excel(file)
    for col in ["date1","date2","maturity"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    portfolio = df
    save_data(portfolio)

# -------------------------
# VALIDATION
# -------------------------
if portfolio.empty:
    st.warning("Додай ОВДП")
    st.stop()

# -------------------------
# GENERATE
# -------------------------
def generate(df):
    events = []

    for _, b in df.iterrows():
        if pd.isna(b["maturity"]) or pd.isna(b["date1"]) or pd.isna(b["date2"]):
            continue

        maturity = b["maturity"]

        for start in [b["date1"], b["date2"]]:
            d = start

            while d <= maturity:

                if d >= TODAY:

                    # купон
                    events.append({
                        "date": d,
                        "name": b["name"],
                        "type": "coupon",
                        "amount": b["coupon"] * b["quantity"],
                        "principal": 0
                    })

                    # погашення
                    if d == maturity:
                        events.append({
                            "date": d,
                            "name": b["name"],
                            "type": "maturity",
                            "amount": 0,
                            "principal": b["nominal"] * b["quantity"]
                        })

                d += relativedelta(months=6)

    return pd.DataFrame(events)

events = generate(portfolio)

if events.empty:
    st.warning("Немає майбутніх виплат")
    st.stop()

events["month"] = events["date"].dt.to_period("M").astype(str)

# -------------------------
# SPLIT
# -------------------------
income = events[events["type"] == "coupon"]
principal = events[events["type"] == "maturity"]

monthly_income = income.groupby("month")["amount"].sum().reset_index()

# -------------------------
# GAP GRAPH (важливо)
# -------------------------
all_months = pd.date_range(
    start=events["date"].min(),
    end=events["date"].max(),
    freq="MS"
).to_period("M").astype(str)

gap_df = pd.DataFrame({"month": all_months})
gap_df = gap_df.merge(monthly_income, on="month", how="left")
gap_df["amount"] = gap_df["amount"].fillna(0)

# -------------------------
# KPI
# -------------------------
st.title("💼 ОВДП Dashboard")

total = (portfolio["nominal"] * portfolio["quantity"]).sum()
annual = monthly_income["amount"].sum()
avg = annual / 12

c1,c2,c3 = st.columns(3)
c1.metric("Портфель", f"{total:,.0f} ₴")
c2.metric("Річний дохід", f"{annual:,.0f} ₴")
c3.metric("Сер. місяць", f"{avg:,.0f} ₴")

# -------------------------
# VIEW
# -------------------------
view = st.radio("Режим",
    ["📈 Дохід", "📊 Провали", "📅 Виплати", "💼 Портфель"],
    horizontal=True)

# -------------------------
# GRAPH 1 (дохід)
# -------------------------
if view == "📈 Дохід":
    st.line_chart(monthly_income.set_index("month"))

# -------------------------
# GRAPH 2 (провали)
# -------------------------
elif view == "📊 Провали":
    st.bar_chart(gap_df.set_index("month"))

# -------------------------
# EVENTS
# -------------------------
elif view == "📅 Виплати":
    st.dataframe(events.sort_values("date"))

# -------------------------
# PORTFOLIO
# -------------------------
elif view == "💼 Портфель":

    edited = st.data_editor(portfolio, num_rows="dynamic")

    if st.button("💾 Зберегти"):
        save_data(edited)

    to_delete = st.selectbox("Видалити", portfolio["name"])

    if st.button("❌ Видалити"):
        portfolio = portfolio[portfolio["name"] != to_delete]
        save_data(portfolio)
