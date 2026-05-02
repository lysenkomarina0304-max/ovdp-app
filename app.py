import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="ОВДП Dashboard")

DATA_FILE = "portfolio.json"
TODAY = pd.Timestamp(datetime.today().date())

# ─────────────────────────────────────────
# LOAD / SAVE
# ─────────────────────────────────────────
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
    return pd.DataFrame(columns=["name","quantity","coupon","date1","date2","maturity","nominal"])

def save_data(df):
    df.to_json(DATA_FILE, date_format="iso")

if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_data()

# ─────────────────────────────────────────
# CASHFLOW ENGINE  (ключова логіка)
# ─────────────────────────────────────────
def generate_cashflows(df):
    """
    Повертає DataFrame з колонками:
      date, name, type ('coupon' / 'maturity'), amount, month (Period)

    Тип A — є date1 і date2 → цикл кожні 6 міс до maturity
    Тип B — є тільки date1  → 1 купон + погашення
    """
    rows = []

    for _, r in df.iterrows():
        name     = r["name"]
        qty      = int(r["quantity"])
        coupon   = float(r["coupon"])      # купон на 1 облігацію
        nominal  = float(r["nominal"])
        mat      = pd.Timestamp(r["maturity"])
        d1       = pd.Timestamp(r["date1"]) if pd.notna(r["date1"]) else None
        d2       = pd.Timestamp(r["date2"]) if pd.notna(r.get("date2")) else None

        coupon_total = coupon * qty
        nominal_total = nominal * qty

        # ── Тип B: тільки date1 (останній купон перед погашенням) ──
        if d1 is not None and (d2 is None or pd.isna(d2)):
            # 1 купон
            rows.append({"date": d1, "name": name, "type": "coupon",   "amount": coupon_total})
            # погашення в maturity (купон вже врахований вище, якщо d1 == mat — без дублю)
            if d1.to_period("M") != mat.to_period("M"):
                rows.append({"date": mat, "name": name, "type": "maturity", "amount": nominal_total})
            else:
                # d1 == maturity: купон вже є, додаємо тільки номінал
                rows.append({"date": mat, "name": name, "type": "maturity", "amount": nominal_total})

        # ── Тип A: є date1 і date2 → 6-місячний цикл ──
        elif d1 is not None and d2 is not None:
            months_step = 6  # стандарт ОВДП

            # Генеруємо купони: перший = d1, потім кожні 6 міс
            current = d1
            seen_months = set()

            while current <= mat:
                m = current.to_period("M")
                key = (name, "coupon", m)
                if key not in seen_months:
                    rows.append({"date": current, "name": name, "type": "coupon", "amount": coupon_total})
                    seen_months.add(key)
                current = current + relativedelta(months=months_step)

            # Погашення в maturity (без дублювання купону)
            rows.append({"date": mat, "name": name, "type": "maturity", "amount": nominal_total})

    if not rows:
        return pd.DataFrame(columns=["date","name","type","amount","month"])

    cf = pd.DataFrame(rows)
    cf["date"]  = pd.to_datetime(cf["date"])
    cf["month"] = cf["date"].dt.to_period("M")

    # Дедуплікація: (name, type, month) — лишаємо першу
    cf = cf.drop_duplicates(subset=["name","type","month"], keep="first")
    cf = cf.sort_values("date").reset_index(drop=True)
    return cf

# ─────────────────────────────────────────
# SIDEBAR — ФІЛЬТРИ + ДОДАВАННЯ
# ─────────────────────────────────────────
portfolio = st.session_state.portfolio

st.sidebar.header("Оберіть ОВДП")

bond_options = ["Всі"] + (portfolio["name"].tolist() if not portfolio.empty else [])
selected_bond = st.sidebar.selectbox("", bond_options)

st.sidebar.markdown("Рік")
year_options = ["Всі"]
if not portfolio.empty:
    cf_all = generate_cashflows(portfolio)
    if not cf_all.empty:
        years = sorted(cf_all["date"].dt.year.unique().tolist())
        year_options += [str(y) for y in years]
selected_year = st.sidebar.selectbox(" ", year_options)

# ── Додати ОВДП ──
with st.sidebar.expander("➕ Додати ОВДП"):
    with st.form("add_form", clear_on_submit=True):
        name    = st.text_input("Назва")
        qty     = st.number_input("Кількість", min_value=0, step=1, value=1)
        coupon  = st.number_input("Купон (на 1 обл.)", min_value=0.0, step=0.01)
        d1      = st.date_input("date1 (перша дата купону)")
        d2_raw  = st.text_input("date2 (необов'язково, формат РРРР-ММ-ДД)")
        mat     = st.date_input("maturity (погашення)")
        nominal = st.number_input("Номінал", min_value=1, value=1000)
        ok = st.form_submit_button("Додати")

    if ok and name:
        d2_val = pd.to_datetime(d2_raw, errors="coerce") if d2_raw.strip() else pd.NaT
        new = pd.DataFrame([{
            "name": name, "quantity": qty, "coupon": coupon,
            "date1": pd.to_datetime(d1), "date2": d2_val,
            "maturity": pd.to_datetime(mat), "nominal": nominal,
        }])
        st.session_state.portfolio = pd.concat([portfolio, new], ignore_index=True)
        save_data(st.session_state.portfolio)
        st.rerun()

# ── Імпорт Excel ──
with st.sidebar.expander("📥 Імпорт Excel"):
    file = st.file_uploader("Файл Excel", type=["xlsx","xls"])
    if file:
        try:
            df_imp = pd.read_excel(file)
            for col in ["date1","date2","maturity"]:
                if col in df_imp.columns:
                    df_imp[col] = pd.to_datetime(df_imp[col], errors="coerce")
            st.session_state.portfolio = df_imp
            save_data(df_imp)
            st.rerun()
        except Exception as e:
            st.error(f"Помилка: {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
portfolio = st.session_state.portfolio

if portfolio.empty:
    st.warning("Портфель порожній. Додай ОВДП через ліву панель.")
    st.stop()

# Фільтрація для відображення
cf = generate_cashflows(portfolio)

if selected_bond != "Всі":
    cf = cf[cf["name"] == selected_bond]
if selected_year != "Всі":
    cf = cf[cf["date"].dt.year == int(selected_year)]

cf_future  = cf[cf["date"] >= TODAY]
cf_coupons = cf[cf["type"] == "coupon"]
cf_maturities = cf[cf["type"] == "maturity"]

# ─────────────────────────────────────────
# МЕТРИКИ
# ─────────────────────────────────────────
st.title("💼 ОВДП Dashboard")

total_nominal   = (portfolio["nominal"] * portfolio["quantity"]).sum()
annual_income   = cf_coupons[cf_coupons["date"] >= TODAY]["amount"].sum()  # купони вперед
avg_monthly     = cf_coupons[cf_coupons["date"] >= TODAY].groupby("month")["amount"].sum().mean()

col1, col2, col3 = st.columns(3)
col1.metric("Портфель",     f"{total_nominal:,.0f} ₴")
col2.metric("Річний дохід", f"{annual_income:,.0f} ₴")
col3.metric("Сер. місяць",  f"{avg_monthly:,.0f} ₴" if pd.notna(avg_monthly) else "—")

# Наступна виплата
next_events = cf_future.sort_values("date")
if not next_events.empty:
    nxt = next_events.iloc[0]
    st.info(f"📅 Наступна виплата: **{nxt['date'].strftime('%Y-%m-%d')}** — {nxt['name']} ({nxt['type']}) · {nxt['amount']:,.0f} ₴")

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📈 Графік", "📋 Виплати", "📁 Портфель"])

# ══════════════════════════════
# TAB 1 — ГРАФІК
# ══════════════════════════════
with tab1:
    # Агрегація по місяцях
    monthly_coupon = (
        cf_coupons[cf_coupons["date"] >= TODAY]
        .groupby("month")["amount"].sum()
        .reset_index()
    )
    monthly_mat = (
        cf_maturities[cf_maturities["date"] >= TODAY]
        .groupby("month")["amount"].sum()
        .reset_index()
    )

    if monthly_coupon.empty:
        st.info("Немає майбутніх купонних виплат.")
    else:
        monthly_coupon["date_str"] = monthly_coupon["month"].dt.to_timestamp().dt.strftime("%Y-%m")
        monthly_mat["date_str"]   = monthly_mat["month"].dt.to_timestamp().dt.strftime("%Y-%m")

        fig = go.Figure()

        # Лінія — купонний дохід
        fig.add_trace(go.Scatter(
            x=monthly_coupon["date_str"],
            y=monthly_coupon["amount"],
            mode="lines+markers",
            name="Дохід (купони)",
            line=dict(color="#2563eb", width=2),
            marker=dict(size=5),
        ))

        # Точки — погашення
        if not monthly_mat.empty:
            fig.add_trace(go.Scatter(
                x=monthly_mat["date_str"],
                y=monthly_mat["amount"],
                mode="markers",
                name="Погашення",
                marker=dict(color="#ef4444", size=12, symbol="circle"),
            ))

        # Портфель (накопичений залишок номіналу)
        # Рахуємо зменшення портфеля після кожного погашення
        port_val = total_nominal
        port_points = []
        all_months = pd.period_range(
            start=monthly_coupon["month"].min(),
            end=monthly_coupon["month"].max(),
            freq="M"
        )
        for m in all_months:
            mat_in_month = monthly_mat[monthly_mat["month"] == m]["amount"].sum()
            port_val -= mat_in_month
            port_points.append({"month_str": m.to_timestamp().strftime("%Y-%m"), "value": max(port_val, 0)})

        port_df = pd.DataFrame(port_points)
        fig.add_trace(go.Scatter(
            x=port_df["month_str"],
            y=port_df["value"],
            mode="lines",
            name="Портфель",
            line=dict(color="#10b981", width=1.5, dash="dot"),
            yaxis="y2",
        ))

        fig.update_layout(
            yaxis=dict(title="Дохід / Погашення (₴)"),
            yaxis2=dict(title="Портфель (₴)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=1.12),
            hovermode="x unified",
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Бар-чарт "провалів"
    st.subheader("📊 Помісячний дохід (пошук провалів)")
    if not monthly_coupon.empty:
        fig2 = go.Figure(go.Bar(
            x=monthly_coupon["date_str"],
            y=monthly_coupon["amount"],
            marker_color="#2563eb",
            name="Купонний дохід",
        ))
        fig2.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis_title="₴", xaxis_title="Місяць",
            margin=dict(t=20, b=40),
        )
        st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════
# TAB 2 — ВИПЛАТИ (КАЛЕНДАР)
# ══════════════════════════════
with tab2:
    st.subheader("📅 Календар виплат")

    display_cf = cf.copy()
    display_cf["Дата"]  = display_cf["date"].dt.strftime("%Y-%m-%d")
    display_cf["ОВДП"]  = display_cf["name"]
    display_cf["Тип"]   = display_cf["type"].map({"coupon": "Купон", "maturity": "Погашення"})
    display_cf["Сума (₴)"] = display_cf["amount"].map("{:,.2f}".format)
    display_cf["Статус"] = display_cf["date"].apply(lambda d: "✅ Виплачено" if d < TODAY else "⏳ Очікується")

    st.dataframe(
        display_cf[["Дата","ОВДП","Тип","Сума (₴)","Статус"]].reset_index(drop=True),
        use_container_width=True, height=450
    )

    # Ризик погашення
    st.subheader("⚠️ Ризик погашення")
    mat_future = cf_maturities[cf_maturities["date"] >= TODAY]
    in_6m  = mat_future[mat_future["date"] <= TODAY + relativedelta(months=6)]["amount"].sum()
    in_12m = mat_future[mat_future["date"] <= TODAY + relativedelta(months=12)]["amount"].sum()
    pct_6  = in_6m  / total_nominal * 100 if total_nominal else 0
    pct_12 = in_12m / total_nominal * 100 if total_nominal else 0

    r1, r2 = st.columns(2)
    r1.metric("Погашається за 6 міс",  f"{in_6m:,.0f} ₴ ({pct_6:.1f}%)")
    r2.metric("Погашається за 12 міс", f"{in_12m:,.0f} ₴ ({pct_12:.1f}%)")

# ══════════════════════════════
# TAB 3 — РЕДАГУВАННЯ ПОРТФЕЛЯ
# ══════════════════════════════
with tab3:
    st.subheader("✏️ Редагування портфеля")

    edit_df = portfolio.copy()
    for col in ["date1","date2","maturity"]:
        edit_df[col] = edit_df[col].dt.strftime("%Y-%m-%d").where(edit_df[col].notna(), "")

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="dynamic",
        key="portfolio_editor",
    )

    col_s, col_d = st.columns([1, 5])
    with col_s:
        if st.button("💾 Зберегти зміни"):
            for col in ["date1","date2","maturity"]:
                edited[col] = pd.to_datetime(edited[col], errors="coerce")
            st.session_state.portfolio = edited.reset_index(drop=True)
            save_data(st.session_state.portfolio)
            st.success("Збережено!")
            st.rerun()

    # What-if симуляція
    st.markdown("---")
    st.subheader("🔄 What-if: вплив нової ОВДП")

    with st.expander("Симулювати нову інвестицію"):
        w_name    = st.text_input("Назва (тест)", value="Нова ОВДП")
        w_qty     = st.number_input("Кількість", min_value=1, value=10, key="w_qty")
        w_coupon  = st.number_input("Купон (на 1 обл.)", min_value=0.0, value=50.0, key="w_coupon")
        w_d1      = st.date_input("date1", key="w_d1")
        w_d2_raw  = st.text_input("date2 (необов'язково)", key="w_d2")
        w_mat     = st.date_input("maturity", key="w_mat")
        w_nominal = st.number_input("Номінал", min_value=1, value=1000, key="w_nom")

        if st.button("📊 Показати вплив"):
            w_d2 = pd.to_datetime(w_d2_raw, errors="coerce") if w_d2_raw.strip() else pd.NaT
            sim_row = pd.DataFrame([{
                "name": w_name, "quantity": w_qty, "coupon": w_coupon,
                "date1": pd.to_datetime(w_d1), "date2": w_d2,
                "maturity": pd.to_datetime(w_mat), "nominal": w_nominal,
            }])
            sim_portfolio = pd.concat([portfolio, sim_row], ignore_index=True)
            sim_cf = generate_cashflows(sim_portfolio)

            orig_monthly = (
                cf_coupons[cf_coupons["date"] >= TODAY]
                .groupby("month")["amount"].sum()
            )
            sim_monthly = (
                sim_cf[(sim_cf["type"]=="coupon") & (sim_cf["date"] >= TODAY)]
                .groupby("month")["amount"].sum()
            )
            all_m = sim_monthly.index.union(orig_monthly.index)
            diff  = sim_monthly.reindex(all_m, fill_value=0) - orig_monthly.reindex(all_m, fill_value=0)

            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=[m.to_timestamp().strftime("%Y-%m") for m in orig_monthly.index],
                y=orig_monthly.values,
                name="Поточний", line=dict(color="#2563eb"),
            ))
            fig3.add_trace(go.Scatter(
                x=[m.to_timestamp().strftime("%Y-%m") for m in sim_monthly.index],
                y=sim_monthly.values,
                name="Після + ОВДП", line=dict(color="#10b981", dash="dash"),
            ))
            fig3.update_layout(
                title="Порівняння cashflow", hovermode="x unified",
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig3, use_container_width=True)

            new_annual = sim_cf[(sim_cf["type"]=="coupon") & (sim_cf["date"] >= TODAY)]["amount"].sum()
            st.metric("Новий річний дохід", f"{new_annual:,.0f} ₴",
                      delta=f"+{new_annual - annual_income:,.0f} ₴")
