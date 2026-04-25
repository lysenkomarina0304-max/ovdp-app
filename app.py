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
        return df
    return pd.DataFrame(columns=[
        "name","quantity","coupon","date1","date2","maturity","nominal"
    ])

def save_data(df):
    df.to_json(DATA_FILE)

portfolio = load_data()

# -------------------------
# SIDEBAR: ADD BOND
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
    st.sidebar.success("Додано")

# -------------------------
# IMPORT EXCEL
# -------------------------
st.sidebar.header("📥 Імпорт Excel")

file = st.sidebar.file_uploader("Завантаж Excel")

if file:
    df = pd.read_excel(file)
    
    # Переконуємось що дати — datetime
    for col in ["date1","date2","maturity"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    
    portfolio = df
    save_data(portfolio)
    st.sidebar.success("Імпортовано")

# -------------------------
# VALIDATION
# -------------------------
if portfolio.empty:
    st.warning("Додай ОВДП в портфель")
    st.stop()

# -------------------------
# CASHFLOW ENGINE
# -------------------------
def generate(df):
    events = []

    for _, b in df.iterrows():

        # пропускаємо криві дані
        if pd.isna(b["maturity"]) or pd.isna(b["date1"]) or pd.isna(b["date2"]):
            continue

        maturity = pd.to_datetime(b["maturity"])
        d1 = pd.to_datetime(b["date1"])
        d2 = pd.to_datetime(b["date2"])

        for start in [d1, d2]:
            d = start

            while d <= maturity:

                if d >= TODAY:
                    amount = b["coupon"] * b["quantity"]

                    if d == maturity:
                        amount += b["nominal"] * b["quantity"]

                    events.append({
                        "date": d,
                        "name": b["name"],
                        "amount": amount
                    })

                d += relativedelta(months=6)

    return pd.DataFrame(events)

events = generate(portfolio)

if events.empty:
    st.warning("Немає майбутніх виплат")
    st.stop()

# -------------------------
# PREP DATA
# -------------------------
events["year"] = events["date"].dt.year
events["month"] = events["date"].dt.strftime("%m.%Y")

# -------------------------
# YEAR FILTER
# -------------------------
years = sorted(events["year"].unique())
year_filter = st.selectbox("📅 Обрати рік", ["Всі"] + years)

filtered = events if year_filter == "Всі" else events[events["year"] == year_filter]

# -------------------------
# MONTHLY AGGREGATION
# -------------------------
monthly = filtered.groupby("month")["amount"].sum().reset_index()

# -------------------------
# KPI
# -------------------------
st.title("💼 ОВДП Dashboard")

total = (portfolio["nominal"] * portfolio["quantity"]).sum()
annual = monthly["amount"].sum()
avg = annual / 12

col1, col2, col3 = st.columns(3)
col1.metric("Портфель", f"{total:,.0f} ₴")
col2.metric("Річний дохід", f"{annual:,.0f} ₴")
col3.metric("Сер. місяць", f"{avg:,.0f} ₴")

# наступна виплата
next_payment = events.sort_values("date").iloc[0]
st.info(f"📅 Наступна виплата: {next_payment['date'].date()} → {next_payment['amount']:,.0f} ₴")

# -------------------------
# CASHFLOW CHART
# -------------------------
st.subheader("📈 Cashflow")
st.line_chart(monthly.set_index("month"))

# -------------------------
# SCENARIO (Було vs Стало)
# -------------------------
st.subheader("🔮 Було vs Стало")

qty_s = st.number_input("Кількість (сценарій)", 0)
coupon_s = st.number_input("Купон (сценарій)", 0)

if st.button("Розрахувати сценарій"):

    added_year = qty_s * coupon_s * 2
    st.success(f"+{added_year:,.0f} ₴ / рік")

    monthly["new"] = monthly["amount"] + added_year / 12

    st.line_chart(monthly.set_index("month")[["amount","new"]])
