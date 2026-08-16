from fastapi import FastAPI, UploadFile, File, HTTPException
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

class ChatRequest(BaseModel):
    message: str
    
class ChatResponse(BaseModel):
    response: str
    chart_path: str = None

class UPIInitiateRequest(BaseModel):
    merchant_id: str = "MERCHANT_001"
    amount: float
    customer_id: str = "cust_001"
    upi_id: str
    payment_app: str = "google_pay"
    psp_provider: str = "razorpay"

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not agent:
        raise HTTPException(status_code=500, detail="Agent is not initialized (Check API keys).")
        
    try:
        inputs = {"messages": [("user", request.message)]}
        final_response = ""
        for s in agent.stream(inputs, stream_mode="values"):
            message = s["messages"][-1]
            if message.type == "ai" and message.content:
                final_response = message.content
        
        chart_path = None
        if "spending_chart.png" in final_response:
            chart_path = "http://localhost:8000/assets/spending_chart.png"
        elif "settlement_trend.png" in final_response:
            chart_path = "http://localhost:8000/assets/settlement_trend.png"
            
        return ChatResponse(response=final_response, chart_path=chart_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

# Mount Frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

