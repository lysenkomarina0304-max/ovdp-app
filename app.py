import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import plotly.graph_objects as go
 
st.set_page_config(layout="wide", page_title="ОВДП Портфель")
 
DATA_FILE = "portfolio.json"
TODAY = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
 
# -------------------------
# LOAD / SAVE
# -------------------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_json(DATA_FILE)
            for col in ["date1", "date2", "maturity"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=[
        "name", "quantity", "coupon", "date1", "date2", "maturity", "nominal"
    ])
 
def save_data(df):
    df_copy = df.copy()
    df_copy.to_json(DATA_FILE, date_format="iso")
 
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_data()
 
# -------------------------
# COUPON GENERATION
# -------------------------
def generate_coupon_schedule(row):
    """
    Generates all coupon payment dates between date1 and maturity
    with monthly step from date2 as the cycle anchor.
    Returns list of (payment_date, amount) tuples.
    """
    payments = []
    try:
        d1 = pd.Timestamp(row["date1"])
        d2 = pd.Timestamp(row["date2"])
        mat = pd.Timestamp(row["maturity"])
        nominal = float(row["nominal"])
        coupon_rate = float(row["coupon"])
        qty = int(row["quantity"])
 
        if pd.isna(d1) or pd.isna(d2) or pd.isna(mat):
            return payments
 
        # Calculate period length in months (d1 → d2)
        months_diff = (d2.year - d1.year) * 12 + (d2.month - d1.month)
        if months_diff <= 0:
            months_diff = 1  # fallback: monthly
 
        # Coupon amount per payment
        periods_per_year = 12 / months_diff
        coupon_amount = nominal * (coupon_rate / 100) / periods_per_year * qty
 
        # Walk from d2 forward by months_diff until maturity
        current = d2
        while current <= mat:
            payments.append((current, round(coupon_amount, 2)))
            current = current + relativedelta(months=months_diff)
 
        # Final principal repayment
        payments.append((mat, round(nominal * qty, 2)))
 
    except Exception:
        pass
    return payments
 
# -------------------------
# SIDEBAR — ADD BOND
# -------------------------
st.sidebar.header("➕ Додати ОВДП")
 
with st.sidebar.form("add_form", clear_on_submit=True):
    name    = st.text_input("Назва")
    qty     = st.number_input("Кількість", min_value=0, step=1, value=1)
    coupon  = st.number_input("Купон (%)", min_value=0.0, step=0.1, value=0.0)
    d1      = st.date_input("Дата початку купону")
    d2      = st.date_input("Дата першого купону")
    mat     = st.date_input("Погашення")
    nominal = st.number_input("Номінал", min_value=1, value=1000)
    submitted = st.form_submit_button("Додати")
 
if submitted and name:
    new = pd.DataFrame([{
        "name":     name,
        "quantity": qty,
        "coupon":   coupon,
        "date1":    pd.to_datetime(d1),
        "date2":    pd.to_datetime(d2),
        "maturity": pd.to_datetime(mat),
        "nominal":  nominal,
    }])
    st.session_state.portfolio = pd.concat(
        [st.session_state.portfolio, new], ignore_index=True
    )
    save_data(st.session_state.portfolio)
    st.sidebar.success(f"Додано: {name}")
 
# -------------------------
# SIDEBAR — IMPORT EXCEL
# -------------------------
st.sidebar.markdown("---")
file = st.sidebar.file_uploader("📥 Імпорт Excel", type=["xlsx", "xls"])
if file:
    try:
        df_imp = pd.read_excel(file)
        for col in ["date1", "date2", "maturity"]:
            if col in df_imp.columns:
                df_imp[col] = pd.to_datetime(df_imp[col], errors="coerce")
        st.session_state.portfolio = df_imp
        save_data(st.session_state.portfolio)
        st.sidebar.success("Імпорт успішний")
    except Exception as e:
        st.sidebar.error(f"Помилка імпорту: {e}")
 
# -------------------------
# SIDEBAR — DELETE BOND
# -------------------------
portfolio = st.session_state.portfolio
 
if not portfolio.empty:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🗑️ Видалити")
    del_name = st.sidebar.selectbox("Оберіть ОВДП", portfolio["name"].tolist())
    if st.sidebar.button("Видалити"):
        idx = portfolio[portfolio["name"] == del_name].index
        if not idx.empty:
            st.session_state.portfolio = portfolio.drop(idx[0]).reset_index(drop=True)
            save_data(st.session_state.portfolio)
            st.rerun()
 
# -------------------------
# MAIN — GUARD
# -------------------------
portfolio = st.session_state.portfolio
 
if portfolio.empty:
    st.warning("Портфель порожній. Додай ОВДП через панель зліва.")
    st.stop()
 
# -------------------------
# BUILD CASH FLOW TABLE
# -------------------------
all_payments = []
for _, row in portfolio.iterrows():
    schedule = generate_coupon_schedule(row)
    for pay_date, amount in schedule:
        is_principal = (pay_date == pd.Timestamp(row["maturity"])) and (amount == row["nominal"] * row["quantity"])
        all_payments.append({
            "bond":      row["name"],
            "date":      pay_date,
            "amount":    amount,
            "type":      "Погашення" if is_principal else "Купон",
            "past":      pay_date < pd.Timestamp(TODAY),
        })
 
df_cf = pd.DataFrame(all_payments)
 
if df_cf.empty:
    st.info("Немає грошових потоків — перевір дати ОВДП.")
    st.stop()
 
df_future = df_cf[~df_cf["past"]].copy()
df_past   = df_cf[df_cf["past"]].copy()
 
# -------------------------
# METRICS
# -------------------------
st.title("📊 ОВДП Портфель")
 
total_invested = (portfolio["nominal"] * portfolio["quantity"]).sum()
total_future   = df_future["amount"].sum() if not df_future.empty else 0
total_received = df_past["amount"].sum() if not df_past.empty else 0
next_payment   = df_future["date"].min() if not df_future.empty else None
 
col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Інвестовано", f"{total_invested:,.0f} ₴")
col2.metric("📈 Майбутні виплати", f"{total_future:,.0f} ₴")
col3.metric("✅ Отримано", f"{total_received:,.0f} ₴")
col4.metric("📅 Наступна виплата", next_payment.strftime("%d.%m.%Y") if next_payment else "—")
 
st.markdown("---")
 
# -------------------------
# CHART — Monthly Cash Flow
# -------------------------
df_chart = (
    df_future.groupby(pd.Grouper(key="date", freq="ME"))["amount"]
    .sum()
    .reset_index()
)
df_chart.columns = ["Місяць", "Сума"]
 
fig = go.Figure()
fig.add_bar(
    x=df_chart["Місяць"],
    y=df_chart["Сума"],
    marker_color="#2563eb",
    name="Виплати",
)
fig.update_layout(
    title="Майбутні грошові потоки по місяцях",
    xaxis_title="Місяць",
    yaxis_title="Сума (₴)",
    plot_bgcolor="white",
    paper_bgcolor="white",
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)
 
# -------------------------
# CHART — By bond (pie)
# -------------------------
col_pie, col_tbl = st.columns([1, 2])
 
with col_pie:
    bond_totals = df_future.groupby("bond")["amount"].sum().reset_index()
    fig2 = go.Figure(go.Pie(
        labels=bond_totals["bond"],
        values=bond_totals["amount"],
        hole=0.4,
    ))
    fig2.update_layout(title="Структура виплат по ОВДП")
    st.plotly_chart(fig2, use_container_width=True)
 
with col_tbl:
    st.subheader("📋 Майбутні виплати")
    display = df_future[["date","bond","type","amount"]].copy()
    display["date"] = display["date"].dt.strftime("%d.%m.%Y")
    display.columns = ["Дата","ОВДП","Тип","Сума (₴)"]
    display = display.sort_values("Дата").reset_index(drop=True)
    st.dataframe(display, use_container_width=True, height=350)
 
# -------------------------
# PORTFOLIO TABLE
# -------------------------
st.markdown("---")
st.subheader("📁 Позиції портфеля")
port_display = portfolio.copy()
for col in ["date1","date2","maturity"]:
    if col in port_display.columns:
        port_display[col] = port_display[col].dt.strftime("%d.%m.%Y")
port_display["Вартість"] = portfolio["nominal"] * portfolio["quantity"]
port_display.columns = ["Назва","Кількість","Купон (%)","Дата 1","Дата 2","Погашення","Номінал","Вартість (₴)"]
st.dataframe(port_display, use_container_width=True)
 
