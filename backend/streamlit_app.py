import streamlit as st
import os
import json
import io
import datetime
import pandas as pd
from PIL import Image
import sys

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from App.financial_agent import initialize_agent, add_pdf_to_knowledgebase
from App.upi_settlement_engine import (
    get_merchant_kpi_summary,
    get_transaction_analytics,
    get_settlement_summary,
    get_reconciliation_report,
    initiate_upi_payment,
    process_razorpay_webhook,
    generate_settlement_analytics_chart
)
from App.expense_processor import (
    parse_csv_expenses,
    parse_excel_expenses,
    parse_json_expenses,
    parse_pdf_expenses,
    parse_sms_transaction_text,
    parse_splitwise_expenses,
    calculate_indian_income_tax,
    process_receipt_ocr,
    generate_sample_csv,
    generate_sample_excel,
    generate_sample_json,
    get_guru_recommendations,
    generate_pdf_report,
    generate_excel_export,
    validate_and_clean_expenses_df
)

# Page Config
st.set_page_config(
    page_title="FinVista AI - Advisory & Business Analytics",
    layout="wide",
    page_icon="",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    /* Metric Card Styling */
    .metric-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px 20px;
        color: #f8fafc;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: #38bdf8;
    }
    .metric-label {
        font-size: 13px;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Custom Callouts */
    .guru-box {
        background-color: #0f2942;
        border-left: 4px solid #38bdf8;
        padding: 14px 18px;
        border-radius: 6px;
        margin-bottom: 12px;
    }
    
    .status-safe { color: #10b981; font-weight: bold; }
    .status-caution { color: #f59e0b; font-weight: bold; }
    .status-danger { color: #ef4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "expenses_df" not in st.session_state:
    # Seed with initial sample expenses if empty
    sample_bytes = generate_sample_csv()
    parsed = parse_csv_expenses(io.BytesIO(sample_bytes))
    st.session_state["expenses_df"] = parsed["data"]

if "budgets" not in st.session_state:
    st.session_state["budgets"] = {
        "Groceries": 5000.0,
        "Dining Out": 2000.0,
        "Utilities": 4000.0,
        "Transportation": 1500.0,
        "Shopping": 6000.0,
        "Entertainment": 3000.0,
        "Savings & Investment": 20000.0
    }

if "goals" not in st.session_state:
    st.session_state["goals"] = [
        {
            "name": "Emergency Reserve (6 Months)",
            "target": 150000.0,
            "current": 45000.0,
            "monthly_contrib": 15000.0,
            "target_date": "2027-03-31"
        },
        {
            "name": "Vacation & Travel Fund",
            "target": 50000.0,
            "current": 20000.0,
            "monthly_contrib": 5000.0,
            "target_date": "2026-12-31"
        }
    ]

if "monthly_income" not in st.session_state:
    st.session_state["monthly_income"] = 100000.0

if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "Hello! I am your AI Financial Advisor & Wealth Strategist. How can I help you optimize your personal budget, tax planning, or merchant UPI transactions today?"}
    ]

# Initialize LangChain Agent
@st.cache_resource
def get_agent():
    return initialize_agent()

try:
    agent = get_agent()
except Exception as e:
    agent = None

# Sidebar Controls & Live Financial Diagnostics
with st.sidebar:
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "images", "logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=54)
    st.title("FinVista AI")
    st.caption("Autonomous Financial Advisory & Wealth Intelligence")
    st.divider()

    st.subheader("Investor Profile & Parameters")
    monthly_income = st.number_input(
        "Monthly Income (INR ₹)",
        min_value=10000.0,
        max_value=10000000.0,
        value=float(st.session_state.get("monthly_income", 100000.0)),
        step=5000.0,
        help="Gross monthly post-tax earnings"
    )
    st.session_state["monthly_income"] = monthly_income

    risk_prof = st.selectbox(
        "Risk Profile",
        ["Moderate (Balanced Index & Debt)", "Aggressive (High Alpha Growth)", "Conservative (Capital Preservation)"],
        index=0,
        help="Calibrates asset allocation between Equities, PPF, and Gold"
    )
    st.session_state["risk_profile"] = risk_prof

    horizon = st.selectbox(
        "Investment Horizon",
        ["7+ Years (Long Term Compounding)", "3-7 Years (Medium Term)", "1-3 Years (Short Term Liquidity)"],
        index=0
    )
    st.session_state["investment_horizon"] = horizon

    st.divider()

    # --- Live Wealth & Cashflow Diagnostic Card ---
    st.subheader("Live Cashflow Diagnostics")
    total_spent = float(st.session_state["expenses_df"]["amount"].sum()) if not st.session_state["expenses_df"].empty else 0.0
    surplus = max(0.0, monthly_income - total_spent)
    savings_rate = (surplus / monthly_income * 100.0) if monthly_income > 0 else 0.0
    emergency_target = (total_spent * 6.0) if total_spent > 0 else (monthly_income * 0.5 * 6.0)

    # Health evaluation
    if savings_rate >= 30.0:
        health_color = "#10b981"
        health_label = "Optimal"
    elif savings_rate >= 15.0:
        health_color = "#f59e0b"
        health_label = "Moderate"
    else:
        health_color = "#ef4444"
        health_label = "Attention Needed"

    st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 12px; padding: 14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span class="metric-label">Net Monthly Surplus</span>
                <span style="font-size:11px; font-weight:700; color:{health_color}; background:rgba(255,255,255,0.06); padding:2px 8px; border-radius:10px;">{health_label}</span>
            </div>
            <div style="font-size: 22px; font-weight: 700; color: #38bdf8;">₹{surplus:,.2f}</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top:4px;">Savings Rate: <strong style="color:{health_color};">{savings_rate:.1f}%</strong> (Target: &ge; 20%)</div>
        </div>
        <div class="metric-card" style="margin-bottom: 12px; padding: 14px;">
            <div class="metric-label">6-Month Emergency Target</div>
            <div style="font-size: 18px; font-weight: 700; color: #fbbf24; margin-top:4px;">₹{emergency_target:,.2f}</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top:2px;">Based on 6x monthly expenses</div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()

    # --- Quick Actions & Workspace Presets ---
    st.subheader("Workspace Presets & Quick Actions")
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("Load Demo Plan", use_container_width=True, help="Load ₹1,50,000 monthly income and realistic expense data"):
            st.session_state["monthly_income"] = 150000.0
            st.session_state["expenses_df"] = parse_csv_expenses(io.BytesIO(generate_sample_csv()))["data"]
            st.rerun()
    with c_btn2:
        if st.button("Clear Expenses", use_container_width=True, help="Reset expenses table to empty"):
            st.session_state["expenses_df"] = pd.DataFrame(columns=["date", "category", "amount", "description"])
            st.rerun()

    # Collapsible Regulatory Note
    with st.expander("Compliance & Safety Notice", expanded=False):
        st.caption(
            "FinVista AI calculates quantitative portfolio projections, Indian income tax comparisons (80C, 80D, NPS), and merchant UPI settlement reconciliations for educational analytics. Adheres to SEBI guidelines."
        )



# Header Banner
st.title("FinVista AI - Personal Financial Advisor & Expense Intelligence Hub")
st.markdown("Comprehensive Personal Wealth Planning, Guru Advice, Budget Tracking & Indian Tax Optimization")

# Navigation Tabs
tab_upload, tab_dashboard, tab_advice, tab_tax, tab_budget, tab_export, tab_upi = st.tabs([
    "Expense Upload Center",
    "Financial Dashboard",
    "Guru Advice & AI Chat",
    "Indian Tax & SIP Planner",
    "Budget & Goal Tracker",
    "Export & Reports",
    "UPI Settlement Analytics"
])

# --- TAB 1: EXPENSE UPLOAD & MULTI-FORMAT PARSER ---
with tab_upload:
    st.header("Expense Upload & Multi-Format Ingestion")
    st.caption("Upload statements, receipts, Splitwise files, or paste SMS transaction alerts.")

    # Format Guidance & Sample Downloads
    with st.expander("Format Guidelines & Sample Templates", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("##### CSV Template")
            st.download_button(
                "Download Sample CSV",
                data=generate_sample_csv(),
                file_name="sample_expenses.csv",
                mime="text/csv",
                use_container_width=True
            )
        with c2:
            st.markdown("##### Excel Template")
            st.download_button(
                "Download Sample Excel",
                data=generate_sample_excel(),
                file_name="sample_expenses.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with c3:
            st.markdown("##### JSON Template")
            st.download_button(
                "Download Sample JSON",
                data=generate_sample_json(),
                file_name="sample_expenses.json",
                mime="application/json",
                use_container_width=True
            )

    st.divider()

    # Upload Container
    col_up1, col_up2 = st.columns([2, 1])

    with col_up1:
        st.markdown("### Upload File (Receipts, Statements, Splitwise)")
        uploaded_file = st.file_uploader(
            "Upload Document / Image",
            type=["csv", "xlsx", "xls", "json", "pdf", "png", "jpg", "jpeg", "webp"],
            help="Upload your bank statement, expense spreadsheet, receipt photo, or Splitwise export."
        )

        if uploaded_file:
            file_name = uploaded_file.name
            file_ext = file_name.lower().split(".")[-1]
            file_bytes = uploaded_file.getvalue()

            st.info(f"Processing uploaded file: **{file_name}** ({len(file_bytes)/1024:.1f} KB)")

            parsed_res = None
            if "splitwise" in file_name.lower() and file_ext == "csv":
                parsed_res = parse_splitwise_expenses(file_bytes)
            elif file_ext == "csv":
                parsed_res = parse_csv_expenses(file_bytes)
            elif file_ext in ["xlsx", "xls"]:
                parsed_res = parse_excel_expenses(file_bytes)
            elif file_ext == "json":
                parsed_res = parse_json_expenses(file_bytes)
            elif file_ext == "pdf":
                with st.spinner("Extracting bank statement data from PDF..."):
                    parsed_res = parse_pdf_expenses(file_bytes)
            elif file_ext in ["png", "jpg", "jpeg", "webp"]:
                with st.spinner("Running Gemini Vision OCR receipt recognition..."):
                    parsed_res = process_receipt_ocr(file_bytes, filename=file_name)

            if parsed_res:
                if parsed_res["success"]:
                    new_df = parsed_res["data"]
                    st.success(f"Successfully processed **{parsed_res['total_count']}** expense items!")
                    
                    if parsed_res.get("warnings"):
                        for w in parsed_res["warnings"]:
                            st.warning(f"Warning: {w}")
                            
                    st.dataframe(new_df, use_container_width=True, hide_index=True)
                    
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("Append to Current Expenses", use_container_width=True, type="primary"):
                            combined = pd.concat([st.session_state["expenses_df"], new_df], ignore_index=True)
                            val = validate_and_clean_expenses_df(combined)
                            st.session_state["expenses_df"] = val["data"]
                            st.success(f"Appended! Total transactions now: {len(st.session_state['expenses_df'])}")
                            st.rerun()
                    with col_b2:
                        if st.button("Replace Current Expenses", use_container_width=True):
                            st.session_state["expenses_df"] = new_df
                            st.success("Replaced existing expense dataset.")
                            st.rerun()

                else:
                    st.error("Data Processing / Ingestion Failed")
                    for err in parsed_res["errors"]:
                        st.error(f"Error details: {err}")
                    
                    if parsed_res.get("troubleshooting"):
                        st.markdown("#### Troubleshooting Steps:")
                        for tip in parsed_res["troubleshooting"]:
                            st.write(tip)

        # Indian SMS / UPI Alert Parser Expander
        with st.expander("Paste Banking & UPI SMS Alerts", expanded=False):
            st.caption("Paste raw transaction SMS messages from SBI, HDFC, ICICI, Google Pay, PhonePe, or Paytm.")
            sms_input = st.text_area(
                "SMS Alert Messages (one or multiple lines)",
                value="Rs. 450 debited from A/c 1234 on 28-Aug-2026 at Swiggy via UPI Ref 928374.\nINR 1,250.00 spent on ICICI Bank Card at Uber on 27-Aug-2026.",
                height=100
            )
            if st.button("Parse & Ingest SMS Text"):
                sms_res = parse_sms_transaction_text(sms_input)
                if sms_res["success"]:
                    st.success(f"Extracted {sms_res['total_count']} transactions from SMS text!")
                    st.dataframe(sms_res["data"], use_container_width=True, hide_index=True)
                    if st.button("Add SMS Expenses to Active Dataset"):
                        combined = pd.concat([st.session_state["expenses_df"], sms_res["data"]], ignore_index=True)
                        st.session_state["expenses_df"] = validate_and_clean_expenses_df(combined)["data"]
                        st.success("Added SMS expenses!")
                        st.rerun()
                else:
                    st.error(sms_res["errors"][0])

    with col_up2:
        st.markdown("### Add Manual Expense")
        with st.form("manual_expense_form"):
            m_date = st.date_input("Transaction Date", value=datetime.date.today())
            m_cat = st.selectbox("Category", [
                "Groceries", "Dining Out", "Utilities", "Transportation", 
                "Shopping", "Entertainment", "Health & Medical", "Housing & Rent",
                "Savings & Investment", "Other"
            ])
            m_amt = st.number_input("Amount (INR ₹)", min_value=1.0, value=500.0, step=50.0)
            m_desc = st.text_input("Description / Merchant", value="Coffee & Snacks")
            m_sub = st.form_submit_button("Save Expense")

            if m_sub:
                new_row = pd.DataFrame([{
                    "date": m_date.strftime("%Y-%m-%d"),
                    "category": m_cat,
                    "amount": round(m_amt, 2),
                    "description": m_desc
                }])
                combined = pd.concat([st.session_state["expenses_df"], new_row], ignore_index=True)
                val = validate_and_clean_expenses_df(combined)
                st.session_state["expenses_df"] = val["data"]
                st.success("Added expense item!")
                st.rerun()

    st.divider()

    # View Current Loaded Expenses
    st.subheader("Loaded Expense Records")
    if not st.session_state["expenses_df"].empty:
        st.dataframe(st.session_state["expenses_df"], use_container_width=True, hide_index=True)
        if st.button("Clear All Loaded Expenses"):
            st.session_state["expenses_df"] = pd.DataFrame(columns=["date", "category", "amount", "description"])
            st.rerun()
    else:
        st.info("No expense records loaded yet. Upload a file above or add a manual expense.")


try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except Exception:
    HAS_PLOTLY = False

# --- TAB 2: FINANCIAL DASHBOARD & VISUALIZATIONS ---
with tab_dashboard:
    st.header("Financial Dashboard & Spending Analytics")
    df = st.session_state["expenses_df"]

    if df.empty:
        st.warning("No expense data loaded. Please upload your expense file in the Expense Upload tab.")
    else:
        # High Level Metric Cards
        total_spend = df["amount"].sum()
        avg_spend = df["amount"].mean()
        txn_count = len(df)
        income = st.session_state["monthly_income"]
        net_savings = max(0.0, income - total_spend)
        savings_rate = (net_savings / income * 100.0) if income > 0 else 0.0

        top_cat_row = df.groupby("category")["amount"].sum().reset_index().sort_values(by="amount", ascending=False).iloc[0]
        top_cat_name = top_cat_row["category"]
        top_cat_amt = top_cat_row["amount"]

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Spending", f"₹{total_spend:,.2f}")
        m2.metric("Monthly Savings", f"₹{net_savings:,.2f}", delta=f"{savings_rate:.1f}% Savings Rate")
        m3.metric("Avg Transaction", f"₹{avg_spend:,.2f}")
        m4.metric("Top Category", f"{top_cat_name}", delta=f"₹{top_cat_amt:,.2f}")
        m5.metric("Transactions", f"{txn_count}")

        st.divider()

        # Charts Section
        c_left, c_right = st.columns(2)
        cat_totals = df.groupby("category")["amount"].sum().reset_index().sort_values(by="amount", ascending=False)
        daily_totals = df.groupby("date")["amount"].sum().reset_index().sort_values("date")

        with c_left:
            st.subheader("Category Spending Breakdown")
            if HAS_PLOTLY:
                fig_donut = px.pie(
                    cat_totals,
                    values="amount",
                    names="category",
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    title="Spending Distribution by Category"
                )
                fig_donut.update_traces(textposition="inside", textinfo="percent+label")
                fig_donut.update_layout(
                    margin=dict(t=30, b=0, l=0, r=0),
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f8fafc")
                )
                st.plotly_chart(fig_donut, use_container_width=True)
            else:
                st.bar_chart(cat_totals, x="category", y="amount", use_container_width=True)

        with c_right:
            st.subheader("Daily Spending Trend")
            if HAS_PLOTLY:
                fig_trend = px.area(
                    daily_totals,
                    x="date",
                    y="amount",
                    title="Daily Expense Outflow Timeline (INR ₹)",
                    markers=True,
                    color_discrete_sequence=["#38bdf8"]
                )
                fig_trend.update_layout(
                    margin=dict(t=30, b=0, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f8fafc"),
                    xaxis=dict(showgrid=True, gridcolor="#334155"),
                    yaxis=dict(showgrid=True, gridcolor="#334155", title="Amount (₹)")
                )
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.line_chart(daily_totals, x="date", y="amount", use_container_width=True)

        st.divider()

        # National Benchmark Comparison
        st.subheader("Your Category Allocation vs. Indian National Benchmarks (HCES 2023-24)")
        national_benchmarks = {
            "Groceries": 35.0,
            "Housing & Rent": 20.0,
            "Utilities": 10.0,
            "Transportation": 12.0,
            "Dining Out": 8.0,
            "Healthcare": 7.0,
            "Entertainment": 8.0
        }

        user_cat_pct = {}
        for cat, amt in cat_totals.values:
            user_cat_pct[cat] = round((amt / total_spend * 100.0), 1)

        bench_rows = []
        all_cats = set(national_benchmarks.keys()).union(user_cat_pct.keys())
        for cat in all_cats:
            u_pct = user_cat_pct.get(cat, 0.0)
            n_pct = national_benchmarks.get(cat, 5.0)
            diff = u_pct - n_pct
            status = "Above Avg" if diff > 2.0 else ("Below Avg" if diff < -2.0 else "In Line")
            bench_rows.append({
                "Category": cat,
                "Your Share (%)": f"{u_pct:.1f}%",
                "National Benchmark (%)": f"{n_pct:.1f}%",
                "Variance": f"{diff:+.1f}%",
                "Status": status
            })

        st.dataframe(pd.DataFrame(bench_rows), use_container_width=True, hide_index=True)

        st.divider()

        # Interactive Expense Explorer Table
        st.subheader("Expense Explorer & Filter Tool")
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            search_query = st.text_input("Search description or merchant", value="")
        with f_col2:
            sel_cat = st.multiselect("Filter by Category", options=df["category"].unique(), default=list(df["category"].unique()))

        filtered_df = df[df["category"].isin(sel_cat)]
        if search_query:
            filtered_df = filtered_df[filtered_df["description"].str.contains(search_query, case=False, na=False)]

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)


# --- TAB 3: GURU ADVICE & AI WEALTH STRATEGIST ---
with tab_advice:
    st.header("AI Guru Wealth Strategist & Investment Engine")
    st.caption("Custom AI model pipeline that synthesizes legendary financial principles into a personalized investment portfolio & wealth roadmap.")

    df = st.session_state["expenses_df"]
    income = float(st.session_state["monthly_income"])
    total_spent = df["amount"].sum() if not df.empty else 0.0

    from App.guru_wealth_engine import generate_ai_guru_wealth_plan

    # Interactive AI Guru Wealth Configuration
    st.subheader("Customize Your Investment & Risk Profile")
    with st.expander("Configure Financial Parameters & Goals", expanded=True):
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            g_risk = st.selectbox(
                "Risk Tolerance Profile",
                [
                    "Moderate (Balanced Index & Debt)",
                    "Aggressive (High-Growth Equities & Cashflow Assets)",
                    "Conservative (Capital Preservation & PPF)"
                ],
                index=0
            )
            g_philosophy = st.selectbox(
                "Primary Guru Philosophy Focus",
                [
                    "Comprehensive Multi-Guru Synthesis",
                    "Warren Buffett (Value & Low-Cost Indexing)",
                    "Robert Kiyosaki (Cashflow & Asset Building)",
                    "Ramit Sethi (Conscious Spending Plan)",
                    "Dave Ramsey (Debt-Free Freedom)"
                ],
                index=0
            )
        with col_g2:
            g_horizon = st.selectbox(
                "Investment Time Horizon",
                ["7+ Years (Long Term Compounding)", "3-7 Years (Medium Term)", "1-3 Years (Short Term)"],
                index=0
            )
            g_goal = st.selectbox(
                "Primary Financial Milestone",
                [
                    "Wealth Creation & Compounding",
                    "Financial Independence / Early Retirement (FIRE)",
                    "House Purchase & Downpayment",
                    "Children's Higher Education Fund",
                    "Debt Clearance & Emergency Stability"
                ],
                index=0
            )
        with col_g3:
            g_curr_savings = st.number_input("Current Liquid Savings (INR ₹)", min_value=0.0, value=150000.0, step=25000.0)
            g_debts = st.number_input("Existing Consumer / Non-Mortgage Debt (INR ₹)", min_value=0.0, value=0.0, step=10000.0)

        btn_run_guru = st.button("Generate Personalized AI Investment & Wealth Strategy", type="primary", use_container_width=True)

    if "latest_wealth_plan" not in st.session_state or btn_run_guru:
        with st.spinner("AI Guru Wealth Engine is computing optimal portfolio allocation and formulating strategic advice..."):
            st.session_state["latest_wealth_plan"] = generate_ai_guru_wealth_plan(
                monthly_income=income,
                monthly_expenses=total_spent,
                current_savings=g_curr_savings,
                existing_debts=g_debts,
                risk_profile=g_risk,
                investment_horizon=g_horizon,
                primary_goal=g_goal,
                preferred_philosophy=g_philosophy
            )

    w_plan = st.session_state["latest_wealth_plan"]

    if w_plan:
        alloc_summary = w_plan["allocation"]["summary"]
        
        # Metric Strip
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Monthly Investible Surplus", f"₹{alloc_summary['monthly_surplus_allocated']:,.2f}")
        m2.metric("Target Equity Allocation", f"{alloc_summary['equity_pct']}%")
        m3.metric("Fixed Income & Debt", f"{alloc_summary['debt_pct']}%")
        m4.metric("Target Portfolio CAGR", f"{alloc_summary['expected_cagr']}%")

        st.divider()

        # Visual Asset Allocation & SIP Breakdown Table
        col_w_chart, col_w_table = st.columns([1, 1])

        with col_w_chart:
            st.subheader("Target Asset Allocation")
            if HAS_PLOTLY:
                alloc_df = pd.DataFrame([
                    {"Asset Class": "Equity Index & Growth", "Allocation (%)": alloc_summary["equity_pct"]},
                    {"Asset Class": "Fixed Income & PPF", "Allocation (%)": alloc_summary["debt_pct"]},
                    {"Asset Class": "Gold / Inflation Hedge", "Allocation (%)": alloc_summary["gold_pct"]},
                    {"Asset Class": "Emergency Cash Buffer", "Allocation (%)": alloc_summary["cash_pct"]}
                ])
                fig_alloc = px.pie(
                    alloc_df,
                    values="Allocation (%)",
                    names="Asset Class",
                    hole=0.45,
                    color_discrete_sequence=["#38bdf8", "#10b981", "#fbbf24", "#94a3b8"],
                    title="Portfolio Asset Distribution"
                )
                fig_alloc.update_traces(textposition="inside", textinfo="percent+label")
                fig_alloc.update_layout(
                    margin=dict(t=30, b=0, l=0, r=0),
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f8fafc")
                )
                st.plotly_chart(fig_alloc, use_container_width=True)

        with col_w_table:
            st.subheader("Recommended Monthly SIP Allocation")
            inst_rows = []
            for inst in w_plan["allocation"]["instruments"]:
                inst_rows.append({
                    "Asset Class": inst["asset_class"],
                    "Monthly (₹)": f"₹{inst['monthly_amount']:,.2f}",
                    "Share": f"{inst['allocation_pct']}%",
                    "Suggested Instruments": ", ".join(inst["suggested_instruments"][:2]),
                    "Exp. Return": inst["expected_return"]
                })
            st.dataframe(pd.DataFrame(inst_rows), use_container_width=True, hide_index=True)

        st.divider()

        # Compounding Wealth Projection Table
        st.subheader("Projected Wealth Accumulation Over Time (At Target CAGR)")
        proj_rows = []
        for key, p in w_plan["allocation"]["projections"].items():
            proj_rows.append({
                "Horizon": f"{p['years']} Years",
                "Total Invested (₹)": f"₹{p['total_invested']:,.2f}",
                "Estimated Future Value (₹)": f"₹{p['estimated_future_value']:,.2f}",
                "Wealth Gain (₹)": f"₹{p['wealth_gain']:,.2f}"
            })
        st.dataframe(pd.DataFrame(proj_rows), use_container_width=True, hide_index=True)

        st.divider()

        # Dynamic AI Strategic Blueprint
        st.subheader("Personalized AI Wealth & Investment Blueprint")
        st.markdown(w_plan["ai_synthesis"])

    st.divider()

    # RAG Knowledgebase Uploader (Financial Books / PDF Articles)
    st.subheader("Ground Advice in Financial Books (RAG Knowledgebase)")
    st.caption("Upload financial books, tax documents, or PDF articles to ground the AI Advisor.")
    
    book_pdf = st.file_uploader("Upload Finance PDF Book or Article", type=["pdf"], key="rag_book_uploader")
    if book_pdf:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(book_pdf.getvalue())
            tmp_path = tmp.name
        
        with st.spinner(f"Ingesting '{book_pdf.name}' into LangChain vector store..."):
            rag_res = add_pdf_to_knowledgebase(tmp_path)
            st.success(f"{rag_res}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    st.divider()

    # Interactive AI Advisor Chat
    st.subheader("Chat with AI Advisor")
    
    col_persona, col_space = st.columns([1, 2])
    with col_persona:
        persona = st.selectbox(
            "Choose Advisor Persona",
            ["Wealth & Tax Strategist", "Warren Buffett (Value)", "Robert Kiyosaki (Cashflow)", "Dave Ramsey (Debt Free)", "Ramit Sethi (Conscious Spend)"]
        )

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about tax rules (Old vs New), SIPs, debt clearance, or budget allocation..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

    if st.session_state["messages"] and st.session_state["messages"][-1]["role"] == "user":
        if not agent:
            st.error("Agent is not initialized. Check API keys in .env.")
        else:
            with st.chat_message("assistant"):
                with st.spinner(f"{persona} is formulating financial advice..."):
                    context_prompt = f"[{persona} Persona]: " + st.session_state["messages"][-1]["content"]
                    inputs = {"messages": [("user", context_prompt)]}
                    
                    final_response = ""
                    for s in agent.stream(inputs, stream_mode="values"):
                        message = s["messages"][-1]
                        if message.type == "ai" and message.content:
                            final_response = message.content
                    
                    st.markdown(final_response)
                    st.session_state["messages"].append({"role": "assistant", "content": final_response})


# --- TAB 4: INDIAN TAX & SIP PLANNER ---
with tab_tax:
    st.header("Indian Personal Finance & Tax Optimization Engine")
    st.caption("Calculate Old vs. New Tax Regime liability, Section 80C/80D deductions, and simulate SIP compound wealth growth.")

    col_t1, col_t2 = st.columns([1, 1])

    with col_t1:
        st.subheader("Tax Slabs & Regime Optimizer (FY 2024-25 / 2025-26)")
        annual_inc = st.number_input("Annual Gross Income (INR ₹)", min_value=100000.0, value=float(st.session_state["monthly_income"] * 12.0), step=50000.0)
        
        c_80c = st.number_input("Section 80C Deductions (ELSS, PPF, EPF) (Max ₹1.5L)", min_value=0.0, max_value=150000.0, value=150000.0, step=10000.0)
        c_80d = st.number_input("Section 80D Health Insurance (Self + Parents)", min_value=0.0, max_value=100000.0, value=25000.0, step=5000.0)
        c_nps = st.number_input("Section 80CCD(1B) NPS Additional Deduction (Max ₹50k)", min_value=0.0, max_value=50000.0, value=50000.0, step=5000.0)
        c_hra = st.number_input("HRA Exemption / Home Loan Interest (Section 24b)", min_value=0.0, max_value=500000.0, value=0.0, step=25000.0)

        tax_res = calculate_indian_income_tax(annual_inc, c_80c, c_80d, c_nps, c_hra)

        st.markdown("#### Regime Comparison")
        col_reg1, col_reg2 = st.columns(2)
        with col_reg1:
            st.info(f"**New Tax Regime**\n\nTaxable: ₹{tax_res['new_regime']['taxable_income']:,.2f}\n\n**Tax Payable: ₹{tax_res['new_regime']['tax_payable']:,.2f}**\n\nEffective Rate: {tax_res['new_regime']['effective_tax_rate']}%")
        with col_reg2:
            st.info(f"**Old Tax Regime**\n\nTaxable: ₹{tax_res['old_regime']['taxable_income']:,.2f}\n\n**Tax Payable: ₹{tax_res['old_regime']['tax_payable']:,.2f}**\n\nEffective Rate: {tax_res['old_regime']['effective_tax_rate']}%")

        if tax_res["tax_difference"] > 0:
            st.success(f"Recommendation: Choose **{tax_res['recommended_regime']}**! Saves ₹{tax_res['tax_difference']:,.2f} annually.")
        else:
            st.info("Both regimes result in zero or equal tax for your income level.")

        st.markdown("##### Actionable Tax Saving Steps:")
        for tip in tax_res["tax_saving_tips"]:
            st.markdown(f"- {tip}")

    with col_t2:
        st.subheader("SIP Compound Wealth Accumulator")
        st.caption("Calculate long-term returns from disciplined mutual fund SIPs.")

        sip_monthly = st.number_input("Monthly SIP Investment (INR ₹)", min_value=500.0, value=15000.0, step=1000.0)
        sip_rate = st.slider("Expected Annual Return Rate (%)", min_value=6.0, max_value=20.0, value=12.5, step=0.5)
        sip_years = st.slider("Investment Horizon (Years)", min_value=1, max_value=35, value=10, step=1)

        # SIP Future Value formula
        # FV = P * [ ( (1 + i)^n - 1 ) / i ] * (1 + i)
        i = (sip_rate / 100.0) / 12.0
        n = sip_years * 12
        fv = sip_monthly * (((1 + i)**n - 1) / i) * (1 + i)
        total_invested = sip_monthly * n
        wealth_gain = fv - total_invested

        st.metric("Future Portfolio Value", f"₹{fv:,.2f}")
        col_sip1, col_sip2 = st.columns(2)
        col_sip1.metric("Total Amount Invested", f"₹{total_invested:,.2f}")
        col_sip2.metric("Estimated Wealth Gain", f"₹{wealth_gain:,.2f}", delta=f"{(wealth_gain/total_invested*100):.1f}% Return")

        # Visual Growth Chart
        yearly_data = []
        for y in range(1, sip_years + 1):
            cur_n = y * 12
            cur_fv = sip_monthly * (((1 + i)**cur_n - 1) / i) * (1 + i)
            cur_inv = sip_monthly * cur_n
            yearly_data.append({"Year": f"Year {y}", "Invested (₹)": cur_inv, "Portfolio Value (₹)": cur_fv})

        df_sip_chart = pd.DataFrame(yearly_data)
        if HAS_PLOTLY:
            fig_sip = px.line(
                df_sip_chart,
                x="Year",
                y=["Invested (₹)", "Portfolio Value (₹)"],
                title="SIP Wealth Growth Over Time",
                markers=True,
                color_discrete_sequence=["#94a3b8", "#10b981"]
            )
            fig_sip.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f8fafc")
            )
            st.plotly_chart(fig_sip, use_container_width=True)
        else:
            st.line_chart(df_sip_chart.set_index("Year"))


# --- TAB 5: BUDGET & GOAL TRACKER ---
with tab_budget:
    st.header("Budget Tracking & Goal Monitoring")
    df = st.session_state["expenses_df"]

    col_b_main, col_g_main = st.columns(2)

    with col_b_main:
        st.subheader("Category Budget Tracker")
        st.caption("Set target budgets and monitor real-time monthly progress.")

        new_budgets = {}
        cat_spent_map = df.groupby("category")["amount"].sum().to_dict() if not df.empty else {}

        for cat, target in st.session_state["budgets"].items():
            spent = cat_spent_map.get(cat, 0.0)
            pct = (spent / target * 100.0) if target > 0 else 0.0

            st.markdown(f"**{cat}** (Target: ₹{target:,.0f} | Spent: ₹{spent:,.2f})")
            
            # Progress bar color logic
            if pct < 80:
                st.progress(min(1.0, spent/target))
                st.caption(f"Status: Safe ({pct:.1f}% used)")
            elif pct <= 100:
                st.progress(min(1.0, spent/target))
                st.caption(f"Status: Caution ({pct:.1f}% used)")
            else:
                st.progress(1.0)
                st.caption(f"Status: OVER BUDGET ({pct:.1f}% used - Exceeded by ₹{spent - target:,.2f})")

            updated_target = st.number_input(f"Edit target for {cat}", min_value=100.0, value=float(target), step=500.0, key=f"b_{cat}")
            new_budgets[cat] = updated_target
            st.write("---")

        st.session_state["budgets"] = new_budgets

    with col_g_main:
        st.subheader("Financial Goals Progress")
        st.caption("Track progress towards your wealth milestones.")

        for i, goal in enumerate(st.session_state["goals"]):
            g_name = goal["name"]
            g_target = goal["target"]
            g_curr = goal["current"]
            g_monthly = goal["monthly_contrib"]
            g_date = goal["target_date"]
            g_pct = (g_curr / g_target * 100.0) if g_target > 0 else 0.0

            st.markdown(f"#### {g_name}")
            st.markdown(f"**Target:** ₹{g_target:,.2f} | **Saved:** ₹{g_curr:,.2f} (**{g_pct:.1f}%**)")
            st.progress(min(1.0, g_curr / g_target))
            
            months_left = max(1.0, (g_target - g_curr) / g_monthly) if g_monthly > 0 else 99
            st.caption(f"Est. completion in **{months_left:.1f} months** at ₹{g_monthly:,.0f}/mo contribution.")
            st.write("---")

        # Form to add new financial goal
        with st.expander("Add New Financial Goal"):
            with st.form("add_goal_form"):
                ng_name = st.text_input("Goal Name", value="New Car Fund")
                ng_target = st.number_input("Target Amount (INR ₹)", min_value=1000.0, value=300000.0, step=10000.0)
                ng_curr = st.number_input("Current Saved (INR ₹)", min_value=0.0, value=50000.0, step=5000.0)
                ng_monthly = st.number_input("Monthly Contribution (INR ₹)", min_value=500.0, value=10000.0, step=1000.0)
                ng_date = st.date_input("Target Date", value=datetime.date(2027, 12, 31))
                ng_sub = st.form_submit_button("Add Goal")

                if ng_sub:
                    st.session_state["goals"].append({
                        "name": ng_name,
                        "target": ng_target,
                        "current": ng_curr,
                        "monthly_contrib": ng_monthly,
                        "target_date": ng_date.strftime("%Y-%m-%d")
                    })
                    st.success(f"Added goal: {ng_name}!")
                    st.rerun()


# --- TAB 5: EXPORT & REPORTS ---
with tab_export:
    st.header("Export & Report Generator")
    st.caption("Generate downloadable financial reports, budget plans, and data exports.")

    df = st.session_state["expenses_df"]
    income = st.session_state["monthly_income"]
    budgets = st.session_state["budgets"]
    goals = st.session_state["goals"]

    ex_col1, ex_col2, ex_col3, ex_col4 = st.columns(4)

    with ex_col1:
        st.markdown("### PDF Financial Report")
        st.caption("Executive PDF summary with metrics, category breakdown & guru advice.")
        pdf_bytes = generate_pdf_report(df, budgets, goals, income)
        st.download_button(
            "Download PDF Report",
            data=pdf_bytes,
            file_name=f"financial_report_{datetime.date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary"
        )

    with ex_col2:
        st.markdown("### Excel Master Workbook")
        st.caption("Multi-tab Excel workbook with Transactions, Summary, Budgets & Goals.")
        excel_bytes = generate_excel_export(df, budgets, goals)
        st.download_button(
            "Download Excel (.xlsx)",
            data=excel_bytes,
            file_name=f"financial_master_{datetime.date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with ex_col3:
        st.markdown("### CSV Expense Log")
        st.caption("Clean CSV log of all recorded expenses.")
        csv_data = df.to_csv(index=False).encode("utf-8") if not df.empty else b""
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name=f"expenses_log_{datetime.date.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with ex_col4:
        st.markdown("### JSON Data Export")
        st.caption("Structured JSON dataset of expenses, budgets & goals.")
        json_obj = {
            "expenses": df.to_dict(orient="records") if not df.empty else [],
            "budgets": budgets,
            "goals": goals,
            "income": income
        }
        st.download_button(
            "Download JSON",
            data=json.dumps(json_obj, indent=2),
            file_name=f"financial_backup_{datetime.date.today().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )


# --- TAB 6: UPI SETTLEMENT ANALYTICS & SANDBOX ---
with tab_upi:
    st.header("UPI Business Analytics & Settlement Tracker")
    st.caption("Real-time UPI transaction tracking, fee reconciliation, bank UTR audits & payment sandbox.")

    merchant_id = st.selectbox("Select Merchant Account", ["MERCHANT_001"], index=0)
    kpis = get_merchant_kpi_summary(merchant_id)
    
    st.subheader("Merchant Performance KPIs")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Transactions", kpis["total_transactions"])
    m2.metric("Successfully Settled", kpis["success_count"])
    m3.metric("Pending Settlement", kpis["pending_count"])
    m4.metric("Failed / Disputes", f"{kpis['failed_count']} / {kpis['dispute_count']}")
    m5.metric("Gross Volume", f"₹{kpis['total_gross_volume']:,.2f}")
    m6.metric("Net Settled to Bank", f"₹{kpis['total_net_settled']:,.2f}", delta=f"-₹{kpis['total_fees_incurred']:,.2f} fees")

    st.divider()

    # 7-Day Settlement Trend Chart
    st.subheader("7-Day Settlement Trend (Gross vs. Fees vs. Net Payout)")
    chart_path = generate_settlement_analytics_chart(merchant_id)
    if chart_path and os.path.exists(chart_path):
        st.image(chart_path, use_container_width=True)

    # PSP Fee Breakdown & App Distribution
    col_psp, col_app = st.columns(2)
    with col_psp:
        st.subheader("Processing Fees & Volume by PSP")
        psp_rows = []
        for psp, val in kpis["psp_breakdown"].items():
            psp_rows.append({
                "PSP Provider": psp.upper(),
                "Volume (₹)": f"₹{val['volume']:,.2f}",
                "Fees (₹)": f"₹{val['fees']:,.2f}",
                "Txn Count": val['count']
            })
        if psp_rows:
            st.dataframe(pd.DataFrame(psp_rows), use_container_width=True, hide_index=True)

    with col_app:
        st.subheader("Payment App Distribution")
        app_rows = [{"Payment App": app.replace('_', ' ').title(), "Total Txns": count} for app, count in kpis["app_breakdown"].items()]
        if app_rows:
            st.dataframe(pd.DataFrame(app_rows), use_container_width=True, hide_index=True)

    st.divider()

    # Settlement Batches & Bank UTR Table
    st.subheader("Daily Settlement Batches & Bank UTRs")
    batches = get_settlement_summary(merchant_id)
    if batches:
        df_batches = pd.DataFrame(batches)
        df_batches = df_batches[['batch_date', 'psp_provider', 'total_transactions', 'total_gross', 'total_fees', 'total_net', 'utr', 'status']]
        df_batches.columns = ['Batch Date', 'PSP', 'Txns', 'Gross (₹)', 'Fees (₹)', 'Net Settled (₹)', 'Bank UTR', 'Status']
        st.dataframe(df_batches, use_container_width=True, hide_index=True)

    # Reconciliation Audit Table
    st.subheader("Transaction-Settlement Reconciliation Audit")
    recs = get_reconciliation_report(merchant_id)
    if recs:
        df_recs = pd.DataFrame(recs)
        df_recs = df_recs[['psp_reference_id', 'amount', 'net_amount', 'batch_date', 'utr', 'status', 'variance_amount', 'notes']]
        df_recs.columns = ['Payment Ref', 'Gross (₹)', 'Net (₹)', 'Batch Date', 'Bank UTR', 'Reconciliation', 'Variance (₹)', 'Audit Notes']
        st.dataframe(df_recs, use_container_width=True, hide_index=True)

    st.divider()

    # UPI Simulator Sandbox
    st.subheader("UPI Payment Initiation & Webhook Sandbox")
    col_sim1, col_sim2 = st.columns(2)

    with col_sim1:
        st.markdown("### 1. Initiate New UPI Transaction")
        with st.form("sim_payment_form"):
            sim_merchant = st.text_input("Merchant ID", value="MERCHANT_001")
            sim_amount = st.number_input("Amount (INR ₹)", min_value=1.0, max_value=200000.0, value=1500.0, step=50.0)
            sim_upi = st.text_input("Customer UPI ID", value="customer@okhdfcbank")
            sim_app = st.selectbox("Payment App", ["google_pay", "phonepe", "paytm", "whatsapp_pay", "cred"])
            sim_psp = st.selectbox("PSP Aggregator", ["razorpay", "billdesk", "payu"])
            submitted = st.form_submit_button("Initiate Payment")
            
            if submitted:
                new_txn = initiate_upi_payment(sim_merchant, sim_amount, "cust_simulator", sim_upi, sim_app, sim_psp)
                st.success(f"Transaction Created: {new_txn['psp_reference_id']}")
                st.json(new_txn)

    with col_sim2:
        st.markdown("### 2. Simulate PSP Webhook Event")
        with st.form("sim_webhook_form"):
            wh_ref = st.text_input("PSP Reference ID", value="pay_raz_sample_123")
            wh_event = st.selectbox("Webhook Event", [
                "payment.captured", 
                "payment.authorized", 
                "payment.failed", 
                "refund.processed"
            ])
            wh_amount = st.number_input("Payload Amount (Paise)", value=150000, step=1000)
            wh_error = st.text_input("Error Reason (if failed)", value="Customer entered incorrect UPI PIN")
            wh_submit = st.form_submit_button("Trigger Webhook Delivery")
            
            if wh_submit:
                payload = {
                    "event": wh_event,
                    "payment": {
                        "entity": {
                            "id": wh_ref,
                            "amount": wh_amount,
                            "fee": 1500,
                            "tax": 270,
                            "status": "captured" if wh_event == "payment.captured" else ("failed" if wh_event == "payment.failed" else "authorized"),
                            "vpa": "customer@okhdfcbank",
                            "error_description": wh_error if wh_event == "payment.failed" else None
                        }
                    }
                }
                res = process_razorpay_webhook(wh_event, payload)
                st.info(f"Webhook Response: {json.dumps(res)}")

# Statutory Educational & Compliance Disclaimer (SEBI Compliance)
st.write("---")
st.caption(
    "Educational & Analytical Disclaimer: FinVista AI provides automated financial data processing, expense intelligence, "
    "and wealth planning estimates based on established methodologies (Buffett, Kiyosaki, Ramsey, Sethi) and Indian Income Tax rules. "
    "This platform is designed for educational and analytical purposes and does not constitute certified SEBI investment advice. "
    "Please consult a SEBI-registered financial advisor before executing significant investment or tax decisions."
)
