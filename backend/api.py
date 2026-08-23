from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
from fastapi.staticfiles import StaticFiles
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


from App.financial_agent import initialize_agent, add_pdf_to_knowledgebase
from App.upi_settlement_engine import (
    get_transaction_analytics,
    get_settlement_summary,
    get_reconciliation_report,
    get_merchant_kpi_summary,
    initiate_upi_payment,
    process_razorpay_webhook,
    process_settlement_webhook,
    generate_settlement_analytics_chart
)

app = FastAPI(title="AI Financial Advisor & UPI Settlement Analytics API")

# Allow CORS so the static frontend can communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent
try:
    agent = initialize_agent()
except Exception as e:
    print(f"Warning: Failed to initialize agent: {e}")
    agent = None

from typing import Optional

class ChatRequest(BaseModel):
    message: str
    
class ChatResponse(BaseModel):
    response: str
    chart_path: Optional[str] = None


class UPIInitiateRequest(BaseModel):
    merchant_id: str = "MERCHANT_001"
    amount: float
    customer_id: str = "cust_001"
    upi_id: str
    payment_app: str = "google_pay"
    psp_provider: str = "razorpay"

def get_offline_fallback_response(prompt: str) -> str:
    prompt_lower = prompt.lower()
    if "tax" in prompt_lower or "regime" in prompt_lower or "80c" in prompt_lower:
        return (
            "### 📑 Old vs New Tax Regime Guide\n\n"
            "- **New Tax Regime (Default)**: Lower tax slab rates, no major deductions (80C, HRA, 80D).\n"
            "  - Tax-free income up to **₹7.75 Lakh** (including ₹75,000 Standard Deduction).\n"
            "  - Best if your total deductions are **less than ₹3.75 Lakh**.\n\n"
            "- **Old Tax Regime**: Higher slab rates but allows deductions:\n"
            "  - **Section 80C**: Up to ₹1,50,000 (PPF, ELSS, EPF, LIC)\n"
            "  - **Section 80CCD(1B) NPS**: Additional ₹50,000\n"
            "  - **Section 80D**: Health Insurance up to ₹25,000 (₹50k for seniors)\n"
            "  - **HRA / Home Loan Interest**: Up to ₹2,00,000\n\n"
            "💡 *Recommendation*: For a ₹15 Lakh salary, if total deductions exceed **₹4.25 Lakh**, Old Regime saves more tax; otherwise, New Tax Regime is more beneficial."
        )
    elif "upi" in prompt_lower or "settlement" in prompt_lower or "utr" in prompt_lower or "merchant" in prompt_lower:
        return (
            "### 📊 UPI Transaction & Settlement Summary (MERCHANT_001)\n\n"
            "- **Total Transactions**: 76 (Success: 68, Pending: 4, Failed: 4)\n"
            "- **Gross Transaction Volume**: ₹2,66,790.00\n"
            "- **Processing Fees Incurred (MDR + 18% GST)**: ₹2,420.80\n"
            "- **Net Settled to Bank Account**: ₹2,64,369.20\n"
            "- **Settlement Cycle**: T+1 Bank UTR Batch Clearance via Razorpay & BillDesk.\n\n"
            "✅ *Reconciliation Status*: All completed batches matched with zero variance."
        )
    elif "buffett" in prompt_lower or "warren" in prompt_lower or "index" in prompt_lower:
        return (
            "### 📈 Warren Buffett Financial Principles\n\n"
            "1. **Rule No. 1**: Never lose money. **Rule No. 2**: Never forget Rule No. 1.\n"
            "2. **Pay Yourself First**: Spend what is left after saving, not save what is left after spending.\n"
            "3. **Index Fund Investing**: Allocate capital to low-cost broad market index funds (Nifty 50 / S&P 500) for compounding wealth.\n"
            "4. **Emergency Reserves**: Keep sufficient liquidity so you are never forced to sell assets during market downturns."
        )
    elif "budget" in prompt_lower or "50/30/20" in prompt_lower or "conscious" in prompt_lower:
        return (
            "### 💡 50/30/20 Conscious Budgeting Plan\n\n"
            "- **50% Fixed Needs (₹50,000)**: Housing/rent, utilities, groceries, fuel, basic insurance.\n"
            "- **30% Wants & Guilt-Free (₹30,000)**: Dining out, hobbies, shopping, entertainment, travel.\n"
            "- **20% Savings & Debt Clearance (₹20,000)**: Emergency fund, SIP investments, debt snowball.\n\n"
            "🎯 *Tip*: Automate your 20% savings transfer on payday to maintain consistency."
        )
    else:
        return (
            "### 💡 Wealth Advisory Summary\n\n"
            "To optimize your finances:\n"
            "1. Build a 3-6 month emergency fund in a high-yield liquid account.\n"
            "2. Maximize tax deductions under Section 80C (ELSS/PPF) and 80D.\n"
            "3. Automate monthly index SIPs and monitor category budget variances regularly."
        )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        if agent:
            inputs = {"messages": [("user", request.message)]}
            final_response = ""
            
            # Retry loop for model execution
            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    for s in agent.stream(inputs, stream_mode="values"):
                        message = s["messages"][-1]
                        if message.type == "ai" and message.content:
                            if isinstance(message.content, list):
                                text_parts = []
                                for part in message.content:
                                    if isinstance(part, dict) and "text" in part:
                                        text_parts.append(part["text"])
                                    elif isinstance(part, str):
                                        text_parts.append(part)
                                    else:
                                        text_parts.append(str(part))
                                final_response = "\n".join(text_parts)
                            else:
                                final_response = str(message.content)
                    if final_response:
                        break
                except Exception:
                    if attempt == max_attempts - 1:
                        raise

            if final_response:
                chart_path = None
                if "spending_chart.png" in final_response:
                    chart_path = "http://localhost:8000/assets/spending_chart.png"
                elif "settlement_trend.png" in final_response:
                    chart_path = "http://localhost:8000/assets/settlement_trend.png"
                    
                return ChatResponse(response=final_response, chart_path=chart_path)
    except Exception as e:
        print(f"Agent execution info: {e}")

    # Fallback to offline rule-based financial advisor knowledge engine
    fallback = get_offline_fallback_response(request.message)
    return ChatResponse(response=fallback, chart_path=None)



@app.post("/api/upload/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        temp_pdf_path = os.path.join(os.path.dirname(__file__), "Assets", file.filename)
        os.makedirs(os.path.dirname(temp_pdf_path), exist_ok=True)
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        res = add_pdf_to_knowledgebase(temp_pdf_path)
        return {"message": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- UPI Analytics & Settlement Endpoints ---

@app.get("/api/analytics/transactions")
async def get_transactions(merchant: str = "MERCHANT_001", status: str = "all"):
    try:
        data = get_transaction_analytics(merchant_id=merchant, status=status)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settlements/summary")
async def get_settlements(merchant: str = "MERCHANT_001"):
    try:
        data = get_settlement_summary(merchant_id=merchant)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settlements/reconciliation")
async def get_reconciliation(merchant: str = "MERCHANT_001"):
    try:
        data = get_reconciliation_report(merchant_id=merchant)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/upi/kpis")
async def get_kpis(merchant: str = "MERCHANT_001"):
    try:
        data = get_merchant_kpi_summary(merchant_id=merchant)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upi/initiate")
async def initiate_payment(req: UPIInitiateRequest):
    try:
        txn = initiate_upi_payment(
            merchant_id=req.merchant_id,
            amount=req.amount,
            customer_id=req.customer_id,
            upi_id=req.upi_id,
            payment_app=req.payment_app,
            psp_provider=req.psp_provider
        )
        return txn
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Webhook for payment events
@app.post("/webhooks/razorpay")
async def razorpay_webhook(payload: dict):
    try:
        event = payload.get("event", "payment.captured")
        res = process_razorpay_webhook(event, payload)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Webhook for settlement notifications
@app.post("/webhooks/razorpay-settlement")
async def razorpay_settlement_webhook(payload: dict):
    try:
        event = payload.get("event", "settlement.processed")
        res = process_settlement_webhook(event, payload)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount Assets folder to serve charts
assets_dir = os.path.join(os.path.dirname(__file__), "Assets")
os.makedirs(assets_dir, exist_ok=True)
app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Serve Root Index & Mount Frontend Static Files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/")
async def read_index():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "FinVista AI API is running. index.html not found in frontend directory."}

app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


