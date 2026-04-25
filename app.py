import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import os

st.set_page_config(layout="wide")

DATA_FILE = "portfolio.json"

# -------------------------
# LOAD / SAVE
# -------------------------
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_json(DATA_FILE)
    return pd.DataFrame(columns=[
        "name","quantity","coupon","date1","date2","maturity","nominal"
    ])

def save_data(df):
    df.to_json(DATA_FILE)

portfolio = load_data()

# -------------------------
# ADD BOND
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
# IMPORT EXCEL
# -------------------------
st.sidebar.header("📥 Імпорт Excel")
file = st.sidebar.file_uploader("Завантаж Excel")

if file:
    df = pd.read_excel(file)
    portfolio = df
    save_data(portfolio)

# -------------------------
# CASHFLOW
# -------------------------
TODAY = datetime.today()

def generate(df):
    events = []
    for _, b in df.iterrows():
        for start in [b["date1"], b["date2"]]:
            d = pd.to_datetime(start)
            while d <= b["maturity"]:
                if d >= TODAY:
                    amount = b["coupon"] * b["quantity"]
                    if d == b["maturity"]:
                        amount += b["nominal"] * b["quantity"]

                    events.append({
                        "date": d,
                        "name": b["name"],
                        "amount": amount
                    })
                d += relativedelta(months=6)
    return pd.DataFrame(events)

events = generate(portfolio)

if not events.empty:
    events["year"] = events["date"].dt.year
    events["month"] = events["date"].dt.strftime("%m.%Y")

# -------------------------
# FILTER YEAR
# -------------------------
year_filter = st.selectbox("📅 Обрати рік", ["Всі"] + sorted(events["year"].unique().tolist()) if not events.empty else ["Всі"])

filtered = events if year_filter == "Всі" else events[events["year"] == year_filter]

# -------------------------
# MONTHLY
# -------------------------
monthly = filtered.groupby("month")["amount"].sum().reset_index()

# -------------------------
# KPI
# -------------------------
st.title("💼 ОВДП Dashboard")

if not events.empty:
    total = (portfolio["nominal"] * portfolio["quantity"]).sum()
    annual = monthly["amount"].sum()
    avg = annual / 12

    col1, col2, col3 = st.columns(3)
    col1.metric("Портфель", f"{total:,.0f} ₴")
    col2.metric("Річний дохід", f"{annual:,.0f} ₴")
    col3.metric("Сер. місяць", f"{avg:,.0f} ₴")

# -------------------------
# CHART
# -------------------------
st.subheader("📈 Cashflow")
st.line_chart(monthly.set_index("month"))

# -------------------------
# SCENARIO
# -------------------------
st.subheader("🔮 Було vs Стало")

qty_s = st.number_input("Кількість (сценарій)", 0)
coupon_s = st.number_input("Купон (сценарій)", 0)

if st.button("Розрахувати сценарій"):
    add_year = qty_s * coupon_s * 2
    st.success(f"+{add_year:,.0f} ₴ / рік")

    monthly["new"] = monthly["amount"] + add_year/12
    st.line_chart(monthly.set_index("month")[["amount","new"]])
