import streamlit as st
import os
import json
import pandas as pd
from PIL import Image
import sys
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

st.set_page_config(page_title="AI Financial Advisor & UPI Analytics", layout="wide", page_icon="💰")

@st.cache_resource
def get_agent():
    return initialize_agent()

try:
    agent = get_agent()
except Exception as e:
    st.error(f"Failed to initialize agent: {e}")
    agent = None

# Header
st.title("💰 AI Financial Advisor & UPI Business Analytics")
st.caption("Personalized wealth advisory grounded in financial gurus + Real-time UPI transaction & settlement tracking")

# Tabs
tab_chat, tab_upi, tab_simulator = st.tabs([
    "💬 AI Financial Advisor Chat", 
    "💳 UPI Settlement & Transaction Analytics", 
    "⚡ UPI Simulator & Webhooks"
])

# --- Tab 1: AI Chat Interface ---
with tab_chat:
    col_chat, col_side = st.columns([3, 1])
    
    with col_side:
        st.subheader("📁 Data Integrations")
        
        with st.expander("1. Guru Advice (PDF)", expanded=False):
            pdf_file = st.file_uploader("Upload book/article", type=["pdf"], key="chat_pdf")
            if pdf_file:
                temp_pdf_path = os.path.join(os.path.dirname(__file__), "Assets", "temp_uploaded.pdf")
                os.makedirs(os.path.dirname(temp_pdf_path), exist_ok=True)
                with open(temp_pdf_path, "wb") as f:
                    f.write(pdf_file.getbuffer())
                with st.spinner("Indexing PDF..."):
                    res = add_pdf_to_knowledgebase(temp_pdf_path)
                    st.success(res)

        with st.expander("2. Spending Data (CSV)", expanded=False):
            csv_file = st.file_uploader("Upload expenses CSV", type=["csv"], key="chat_csv")
            if csv_file:
                try:
                    df = pd.read_csv(csv_file)
                    st.write("Preview:", df.head(2))
                    if st.button("Analyze CSV Expenses", key="btn_csv_exp"):
                        expenses_json = df.to_json(orient="records")
                        prompt = f"Analyze these expenses and compare with national patterns: {expenses_json}"
                        if "messages" not in st.session_state:
                            st.session_state.messages = []
                        st.session_state.messages.append({"role": "user", "content": prompt})
                        st.rerun()
                except Exception as e:
                    st.error(f"CSV Error: {e}")

        with st.expander("3. OCR Screenshot / Receipt", expanded=False):
            img_file = st.file_uploader("Upload receipt image", type=["png", "jpg", "jpeg"], key="chat_img")
            if img_file:
                image = Image.open(img_file)
                st.image(image, caption="Uploaded Image", use_container_width=True)
                temp_img_path = os.path.join(os.path.dirname(__file__), "Assets", "uploaded_screenshot.png")
                os.makedirs(os.path.dirname(temp_img_path), exist_ok=True)
                image.save(temp_img_path)
                if st.button("Extract & Generate Report", key="btn_img_exp"):
                    prompt = "Generate a comprehensive financial report from my uploaded document and uploaded_screenshot.png."
                    if "messages" not in st.session_state:
                        st.session_state.messages = []
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    st.rerun()

        with st.expander("4. Quick Prompts", expanded=True):
            if st.button("📊 Analyze UPI Settlements", use_container_width=True):
                prompt = "Please analyze my UPI transaction volume, fee breakdown, and settlement health for MERCHANT_001."
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.rerun()

            if st.button("🏦 Check Bank UTRs & Batches", use_container_width=True):
                prompt = "Check all bank settlement batches, UTR references, and reconciliation status for MERCHANT_001."
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.rerun()

            if st.button("📑 Old vs New Tax Regime", use_container_width=True):
                prompt = "Explain whether Old or New Tax Regime is better for an annual salary of ₹15 Lakh with ₹1.5 Lakh 80C and ₹50k NPS."
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.rerun()

            if st.button("👥 Fetch Splitwise Mock", use_container_width=True):
                prompt = "Fetch my recent Splitwise expenses and analyze my spending patterns."
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.rerun()

    with col_chat:
        # Chat history container
        if "messages" not in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "Hello! I am your AI Financial Advisor and UPI Business Analytics Assistant. How can I assist you with your personal wealth, tax planning, or merchant UPI settlements today?"}
            ]

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask about personal finance, tax rules, or UPI settlement analytics..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

        if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
            if not agent:
                st.error("Agent is not initialized. Please verify API keys in .env.")
            else:
                with st.chat_message("assistant"):
                    with st.spinner("Analyzing financial data and formulating advisory..."):
                        langchain_messages = []
                        for msg in st.session_state.messages:
                            langchain_messages.append((msg["role"], msg["content"]))
                        
                        inputs = {"messages": langchain_messages}
                        response_placeholder = st.empty()
                        
                        final_response = ""
                        for s in agent.stream(inputs, stream_mode="values"):
                            message = s["messages"][-1]
                            if message.type == "ai" and message.content:
                                final_response = message.content
                        
                        response_placeholder.markdown(final_response)
                        st.session_state.messages.append({"role": "assistant", "content": final_response})
                        
                        # Show spending chart if generated
                        spending_chart = os.path.join(os.path.dirname(__file__), "Assets", "spending_chart.png")
                        if os.path.exists(spending_chart) and "spending_chart.png" in final_response:
                            st.image(spending_chart, caption="Spending Analysis by Category", use_container_width=True)

                        # Show settlement trend chart if generated
                        settlement_chart = os.path.join(os.path.dirname(__file__), "Assets", "settlement_trend.png")
                        if os.path.exists(settlement_chart) and "settlement_trend.png" in final_response:
                            st.image(settlement_chart, caption="7-Day UPI Settlement & Payout Trend", use_container_width=True)

# --- Tab 2: UPI Analytics & Settlement Tracker Dashboard ---
with tab_upi:
    merchant_id = st.selectbox("Select Merchant Account", ["MERCHANT_001"], index=0)
    kpis = get_merchant_kpi_summary(merchant_id)
    
    st.subheader("📈 High-Level Merchant Metrics")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Transactions", kpis["total_transactions"])
    m2.metric("Successfully Settled", kpis["success_count"])
    m3.metric("Pending Settlement", kpis["pending_count"])
    m4.metric("Failed / Disputes", f"{kpis['failed_count']} / {kpis['dispute_count']}")
    m5.metric("Gross Volume", f"₹{kpis['total_gross_volume']:,.2f}")
    m6.metric("Net Settled to Bank", f"₹{kpis['total_net_settled']:,.2f}", delta=f"-₹{kpis['total_fees_incurred']:,.2f} fees")

    st.divider()

    # 7-Day Settlement Trend Chart
    st.subheader("📊 7-Day Settlement Trend (Gross vs. Fees vs. Net)")
    chart_path = generate_settlement_analytics_chart(merchant_id)
    if chart_path and os.path.exists(chart_path):
        st.image(chart_path, use_container_width=True)

    # Fee Breakdown & App Distribution
    col_psp, col_app = st.columns(2)
    with col_psp:
        st.subheader("💳 Processing Fees & Volume by PSP")
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
        st.subheader("📱 Payment App Distribution")
        app_rows = [{"Payment App": app.replace('_', ' ').title(), "Total Txns": count} for app, count in kpis["app_breakdown"].items()]
        if app_rows:
            st.dataframe(pd.DataFrame(app_rows), use_container_width=True, hide_index=True)

    st.divider()

    # Settlement Batches & Bank UTR Table
    st.subheader("🏦 Daily Settlement Batches & Bank UTRs")
    batches = get_settlement_summary(merchant_id)
    if batches:
        df_batches = pd.DataFrame(batches)
        df_batches = df_batches[['batch_date', 'psp_provider', 'total_transactions', 'total_gross', 'total_fees', 'total_net', 'utr', 'status']]
        df_batches.columns = ['Batch Date', 'PSP', 'Txns', 'Gross (₹)', 'Fees (₹)', 'Net Settled (₹)', 'Bank UTR', 'Status']
        st.dataframe(df_batches, use_container_width=True, hide_index=True)

    # Reconciliation Audit Table
    st.subheader("🔍 Transaction-Settlement Reconciliation Audit")
    recs = get_reconciliation_report(merchant_id)
    if recs:
        df_recs = pd.DataFrame(recs)
        df_recs = df_recs[['psp_reference_id', 'amount', 'net_amount', 'batch_date', 'utr', 'status', 'variance_amount', 'notes']]
        df_recs.columns = ['Payment Ref', 'Gross (₹)', 'Net (₹)', 'Batch Date', 'Bank UTR', 'Reconciliation', 'Variance (₹)', 'Audit Notes']
        st.dataframe(df_recs, use_container_width=True, hide_index=True)

    # Recent Transactions Table
    st.subheader("📋 Recent UPI Transactions")
    status_filter = st.selectbox("Filter by Status", ["all", "success", "pending", "failed"], index=0)
    txns = get_transaction_analytics(merchant_id=merchant_id, status=status_filter)
    if txns:
        df_txns = pd.DataFrame(txns[:25])
        df_txns = df_txns[['psp_reference_id', 'upi_id', 'amount', 'payment_app', 'psp_provider', 'status', 'cleared_by_npci_at', 'net_amount_to_merchant']]
        df_txns.columns = ['Reference ID', 'Customer UPI VPA', 'Amount (₹)', 'Payment App', 'PSP', 'Status', 'Cleared by NPCI', 'Net Payout (₹)']
        st.dataframe(df_txns, use_container_width=True, hide_index=True)


# --- Tab 3: UPI Simulator & Webhook Event Trigger ---
with tab_simulator:
    st.subheader("⚡ UPI Payment Initiation & Webhook Sandbox")
    st.caption("Test the end-to-end payment lifecycle: Initiation → Customer Authorization → NPCI Clearance → Aggregator Webhook → Settlement Batch Reconciliation.")
    
    col_sim1, col_sim2 = st.columns(2)
    
    with col_sim1:
        st.markdown("### 1. Initiate New UPI Transaction")
        with st.form("sim_payment_form"):
            sim_merchant = st.text_input("Merchant ID", value="MERCHANT_001")
            sim_amount = st.number_input("Amount (INR ₹)", min_value=1.0, max_value=200000.0, value=1500.0, step=50.0)
            sim_upi = st.text_input("Customer UPI ID", value="customer@okhdfcbank")
            sim_app = st.selectbox("Payment App", ["google_pay", "phonepe", "paytm", "whatsapp_pay", "cred"])
            sim_psp = st.selectbox("PSP Aggregator", ["razorpay", "billdesk", "payu"])
            submitted = st.form_submit_button("🚀 Initiate Payment")
            
            if submitted:
                new_txn = initiate_upi_payment(sim_merchant, sim_amount, "cust_simulator", sim_upi, sim_app, sim_psp)
                st.success(f"Transaction Created: {new_txn['psp_reference_id']}")
                st.json(new_txn)

    with col_sim2:
        st.markdown("### 2. Simulate PSP Webhook Event")
        with st.form("sim_webhook_form"):
            wh_ref = st.text_input("PSP Reference ID (from initiated txn)", value="pay_raz_sample_123")
            wh_event = st.selectbox("Webhook Event", [
                "payment.captured", 
                "payment.authorized", 
                "payment.failed", 
                "refund.processed"
            ])
            wh_amount = st.number_input("Payload Amount (in Paise)", value=150000, step=1000)
            wh_error = st.text_input("Error Reason (for failed event)", value="Customer entered incorrect UPI PIN")
            wh_submit = st.form_submit_button("📡 Trigger Webhook Delivery")
            
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
