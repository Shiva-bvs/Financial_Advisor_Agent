import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import json
import pandas as pd
import matplotlib.pyplot as plt

from dotenv import load_dotenv
import base64
import finnhub
from alpha_vantage.timeseries import TimeSeries
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_DRIVE_API_KEY = os.getenv("GOOGLE_DRIVE_API_KEY")
GMAIL_API_KEY = os.getenv("GMAIL_API_KEY")


try:
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception:
    embeddings = None

vector_store = None

def init_vector_store():
    global vector_store
    try:
        pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'financial_report.pdf')

        if os.path.exists(pdf_path) and embeddings:
            loader = PyPDFLoader(pdf_path)
            docs = loader.load()
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            splits = text_splitter.split_documents(docs)
            vector_store = Chroma.from_documents(documents=splits, embedding=embeddings)
    except Exception as e:
        print(f"\033[93m[Warning]: Failed to initialize vector store for PDFs: {e}\033[0m")
        vector_store = None

init_vector_store()

def add_pdf_to_knowledgebase(pdf_path: str):
    """Add a new PDF to the Chroma vector store."""
    global vector_store
    if not embeddings:
        return "Embeddings not configured."
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    if vector_store is None:
        vector_store = Chroma.from_documents(documents=splits, embedding=embeddings)
    else:
        vector_store.add_documents(documents=splits)
    return f"Successfully added {os.path.basename(pdf_path)} to the knowledgebase."


@tool
def get_stock_price(symbol: str) -> str:
    """Get the current stock price for a given ticker symbol."""
    if not FINNHUB_API_KEY: return "Finnhub API key not configured."
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    res = finnhub_client.quote(symbol.upper())
    current_price = res.get('c')
    return f"The current price of {symbol.upper()} is ${current_price}"

@tool
def get_financial_news(query: str) -> str:
    """Get the latest financial news related to a specific query."""
    if not NEWSDATA_API_KEY: return "NewsData API key not configured."
    url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&q={query}&language=en"
    response = requests.get(url)
    data = response.json()
    articles = data.get('results', [])
    result = f"Top news for '{query}':\n"
    for i, article in enumerate(articles[:3]):
        result += f"{i+1}. {article.get('title')} - {article.get('source_id')}\n"
    return result

@tool
def get_exchange_rate(base_currency: str, target_currency: str) -> str:
    """Get the current exchange rate from a base currency to a target currency."""
    if not EXCHANGE_RATE_API_KEY: return "Exchange Rate API key not configured."
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/pair/{base_currency.upper()}/{target_currency.upper()}"
    response = requests.get(url)
    data = response.json()
    rate = data.get("conversion_rate")
    return f"The exchange rate from {base_currency.upper()} to {target_currency.upper()} is {rate}."

@tool
def search_financial_knowledgebase(query: str) -> str:
    """Search the internal financial knowledgebase (books, reports) for information."""
    if vector_store is None:
        return "Knowledgebase is empty or not loaded."
    docs = vector_store.similarity_search(query, k=3)
    return "\n".join([doc.page_content for doc in docs])

@tool
def calculate_compound_interest(principal: float, rate: float, time: int) -> str:
    """Calculate the future value of an investment using compound interest."""
    amount = principal * (1 + rate/100) ** time
    return f"The future value of a ${principal} investment at {rate}% over {time} years is ${amount:.2f}."

@tool
def analyze_spending_patterns(expenses_json: str) -> str:
    """
    Analyze spending patterns given a JSON string of expenses.
    Expected JSON format: [{"category": "Food", "amount": 50.0}, ...]
    It returns a summary and saves a plot to 'Assets/spending_chart.png'.
    """
    try:
        expenses = json.loads(expenses_json)
        if not expenses:
            return "No expenses to analyze."
        df = pd.DataFrame(expenses)
        if 'category' not in df.columns or 'amount' not in df.columns:
            return "Expenses must have 'category' and 'amount' keys."
        
        # Group by category
        summary = df.groupby('category')['amount'].sum().reset_index()
        total_spent = summary['amount'].sum()
        
        # Generate plot
        plt.figure(figsize=(8, 8))
        plt.pie(summary['amount'], labels=summary['category'], autopct='%1.1f%%', startangle=140)
        plt.title('Spending by Category')
        chart_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'spending_chart.png')
        
        # Ensure Assets folder exists
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        plt.savefig(chart_path)
        plt.close()

        # Build summary string
        result = f"Total Spent: ${total_spent:.2f}\n\nCategory Breakdown:\n"
        for _, row in summary.iterrows():
            result += f"- {row['category']}: ${row['amount']:.2f}\n"
        result += "\n(A pie chart has been saved to Assets/spending_chart.png)"
        return result
    except Exception as e:
        return f"Error analyzing expenses: {str(e)}"

@tool
def get_budget_recommendations(analysis_summary: str) -> str:
    """Get standard budgeting recommendations (e.g. 50/30/20 rule) based on the provided spending analysis summary."""
    # This tool delegates back to the LLM's system prompt or can provide hardcoded generic advice.
    # We will provide a simple generic template that the agent can expand upon.
    return (
        f"Based on the analysis: \n{analysis_summary}\n\n"
        "Recommendation:\n"
        "Consider applying the 50/30/20 rule: allocate 50% to needs, 30% to wants, and 20% to savings/debt repayment. "
        "Review your top spending categories to see where you can cut back to increase your savings rate."
    )

@tool
def fetch_splitwise_expenses() -> str:
    """Fetch recent group expenses from Splitwise. (Mock implementation)"""
    mock_expenses = [
        {"category": "Dining Out", "amount": 45.50, "description": "Dinner at Mario's", "date": "2023-10-01"},
        {"category": "Groceries", "amount": 120.00, "description": "Whole Foods split", "date": "2023-10-03"},
        {"category": "Utilities", "amount": 60.00, "description": "Internet Bill", "date": "2023-10-05"}
    ]
    return json.dumps(mock_expenses)

@tool
def search_gmail_financial_records(query: str = "receipt OR invoice OR statement") -> str:
    """Fetch recent financial records (receipts/invoices) from Gmail."""
    if not GMAIL_API_KEY:
        return "Gmail API key not configured."
    try:
        service = build('gmail', 'v1', developerKey=GMAIL_API_KEY)
        # Note: Usually developerKey (API Key) does not work for private user data like Gmail.
        # This will likely return a 401 Unauthorized or 403 Permission Denied in practice.
        results = service.users().messages().list(userId='me', q=query, maxResults=5).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return "No financial records found in Gmail."
            
        return f"Found {len(messages)} emails matching '{query}'. (Content extraction requires OAuth)"
    except HttpError as error:
        return f"Gmail API Error (Expected if using API Key instead of OAuth): {error}"
    except Exception as e:
        return f"Error connecting to Gmail: {str(e)}"

@tool
def search_drive_financial_records(query: str = "budget") -> str:
    """Search Google Drive for financial spreadsheets or documents."""
    if not GOOGLE_DRIVE_API_KEY:
        return "Google Drive API key not configured."
    try:
        service = build('drive', 'v3', developerKey=GOOGLE_DRIVE_API_KEY)
        # Like Gmail, Drive usually requires OAuth for private files.
        results = service.files().list(
            q=f"name contains '{query}'",
            pageSize=5,
            fields="nextPageToken, files(id, name, mimeType)"
        ).execute()
        items = results.get('files', [])
        
        if not items:
            return "No financial records found in Google Drive."
            
        res = "Found the following files in Drive:\n"
        for item in items:
            res += f"- {item['name']} ({item['mimeType']})\n"
        return res
    except HttpError as error:
        return f"Drive API Error (Expected if using API Key instead of OAuth): {error}"
    except Exception as e:
        return f"Error connecting to Google Drive: {str(e)}"

@tool
def analyze_financial_image(filename: str) -> str:
    """Analyze a financial screenshot or receipt image stored in the Assets folder and extract key financial data."""
    if not GEMINI_API_KEY:
        return "Gemini API key is required for image analysis."
    image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', filename)
    if not os.path.exists(image_path):
        return f"Image file {filename} not found in Assets folder."
        
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=GEMINI_API_KEY)
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "Extract all financial transactions, balances, and key information from this image. Format it clearly."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_string}"}}
            ]
        )
        response = llm.invoke([msg])
        return response.content
    except Exception as e:
        return f"Error analyzing image: {str(e)}"

@tool
def analyze_all_client_assets() -> str:
    """Analyze all financial files (PDFs and Images) stored in the Assets folder and return a combined summary of the client's financial situation."""
    if not GEMINI_API_KEY:
        return "Gemini API key is required for asset analysis."
        
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets')
    if not os.path.exists(assets_dir):
        return "Assets folder not found."
        
    extracted_data = []
    
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=GEMINI_API_KEY)
        
        for filename in os.listdir(assets_dir):
            file_path = os.path.join(assets_dir, filename)
            if not os.path.isfile(file_path):
                continue
                
            ext = filename.lower().split('.')[-1]
            
            # Handle Images
            if ext in ['png', 'jpg', 'jpeg']:
                with open(file_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                msg = HumanMessage(
                    content=[
                        {"type": "text", "text": f"Extract all financial transactions, balances, and key information from this image ({filename}). Format it clearly."},
                        {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{encoded_string}"}}
                    ]
                )
                response = llm.invoke([msg])
                extracted_data.append(f"--- Data from Image: {filename} ---\n{response.content}\n")
                
            # Handle PDFs
            elif ext == 'pdf':
                loader = PyPDFLoader(file_path)
                docs = loader.load()
                pdf_text = "\n".join([doc.page_content for doc in docs])
                # Truncate PDF to avoid massive context blowouts, but keep a healthy chunk
                extracted_data.append(f"--- Data from PDF: {filename} ---\n{pdf_text[:5000]}\n") 
                
        if not extracted_data:
            return "No valid financial documents found in the Assets folder."
            
        return "\n\n".join(extracted_data)
        
    except Exception as e:
        return f"Error analyzing assets: {str(e)}"

try:
    from App.upi_settlement_engine import (
        get_merchant_kpi_summary, get_transaction_analytics, get_settlement_summary,
        get_reconciliation_report, initiate_upi_payment, generate_settlement_analytics_chart
    )
except ImportError:
    from upi_settlement_engine import (
        get_merchant_kpi_summary, get_transaction_analytics, get_settlement_summary,
        get_reconciliation_report, initiate_upi_payment, generate_settlement_analytics_chart
    )

@tool
def analyze_upi_settlements_and_transactions(merchant_id: str = "MERCHANT_001") -> str:
    """Analyze UPI transactions, merchant volume, fee breakdown by PSP/App, and generate 7-day settlement trends."""
    try:
        kpis = get_merchant_kpi_summary(merchant_id)
        chart_path = generate_settlement_analytics_chart(merchant_id)
        
        psp_summary = "\n".join([f"  - {psp.upper()}: Volume INR {v['volume']:,.2f} | Fees INR {v['fees']:,.2f} ({v['count']} txns)" for psp, v in kpis['psp_breakdown'].items()])
        app_summary = ", ".join([f"{app}: {count}" for app, count in kpis['app_breakdown'].items()])
        
        res = (
            f"=== UPI TRANSACTION & SETTLEMENT SUMMARY ({merchant_id}) ===\n"
            f"- Total Transactions: {kpis['total_transactions']} (Success: {kpis['success_count']}, Pending: {kpis['pending_count']}, Failed: {kpis['failed_count']}, Disputes: {kpis['dispute_count']})\n"
            f"- Success Rate: {kpis['success_rate']}%\n"
            f"- Gross Transaction Volume: INR {kpis['total_gross_volume']:,.2f}\n"
            f"- Total Processing Fees Incurred (MDR + GST): INR {kpis['total_fees_incurred']:,.2f}\n"
            f"- Net Settled to Bank Account: INR {kpis['total_net_settled']:,.2f}\n"
            f"- Pending Settlement Volume: INR {kpis['pending_settlement_amount']:,.2f}\n\n"
            f"PSP Fee & Volume Breakdown:\n{psp_summary}\n\n"
            f"Payment Apps Distribution:\n  {app_summary}\n\n"
            f"(Settlement trend chart generated at Assets/settlement_trend.png)"
        )
        return res
    except Exception as e:
        return f"Error analyzing UPI settlements: {str(e)}"

@tool
def check_merchant_settlement_batches(merchant_id: str = "MERCHANT_001") -> str:
    """Query bank settlement batches, UTR numbers, bank payout timestamps, and reconciliation match status."""
    try:
        batches = get_settlement_summary(merchant_id)
        if not batches:
            return f"No settlement batches found for {merchant_id}."
            
        res = f"=== BANK SETTLEMENT BATCHES ({merchant_id}) ===\n"
        for b in batches[:6]:
            utr_str = b['utr'] if b['utr'] else "Pending Bank UTR"
            res += f"- Batch Date: {b['batch_date']} | PSP: {b['psp_provider'].upper()} | Net Payout: INR {b['total_net']:,.2f} | Status: {b['status'].upper()} | Bank UTR: {utr_str}\n"
            
        recs = get_reconciliation_report(merchant_id)
        matched_count = len([r for r in recs if r['status'] == 'matched'])
        variance_count = len([r for r in recs if r['status'] == 'mismatch'])
        res += f"\nReconciliation Audit Health:\n- Matched Transactions: {matched_count}\n- Variances/Discrepancies: {variance_count}\n"
        return res
    except Exception as e:
        return f"Error querying settlement batches: {str(e)}"

@tool
def simulate_or_record_upi_transaction(merchant_id: str = "MERCHANT_001", amount: float = 1000.0, upi_id: str = "customer@okhdfcbank", payment_app: str = "google_pay", psp_provider: str = "razorpay") -> str:
    """Simulate or record a new UPI transaction through the settlement pipeline with fee calculations."""
    try:
        txn = initiate_upi_payment(merchant_id, amount, "cust_live", upi_id, payment_app, psp_provider)
        return (
            f"Transaction Initiated Successfully:\n"
            f"- Transaction Ref: {txn['psp_reference_id']}\n"
            f"- Amount: INR {txn['amount']:.2f}\n"
            f"- App / PSP: {txn['payment_app']} via {txn['psp_provider']}\n"
            f"- Estimated Fee (incl. GST): INR {(txn['psp_fee'] + txn['payment_app_fee'] + txn['gst_fee']):.2f}\n"
            f"- Net Expected Payout: INR {txn['net_amount_to_merchant']:.2f}\n"
            f"- Status: {txn['status']}"
        )
    except Exception as e:
        return f"Error initiating UPI transaction: {str(e)}"

def initialize_agent():
    tools = [
        get_stock_price, 
        get_financial_news, 
        get_exchange_rate, 
        search_financial_knowledgebase, 
        calculate_compound_interest,
        analyze_spending_patterns,
        get_budget_recommendations,
        fetch_splitwise_expenses,
        search_gmail_financial_records,
        search_drive_financial_records,
        analyze_financial_image,
        analyze_all_client_assets,
        analyze_upi_settlements_and_transactions,
        check_merchant_settlement_batches,
        simulate_or_record_upi_transaction
    ]
    
    llm = None
    if GEMINI_API_KEY:
        try:
            llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=GEMINI_API_KEY)
        except Exception as e:
            print(f"Warning: Failed to initialize Gemini LLM: {e}")

    if not llm and GROQ_API_KEY:
        try:
            llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY)
        except Exception as e:
            print(f"Warning: Failed to initialize Groq LLM: {e}")

    if not llm:
        raise ValueError("No working LLM available. Please check GEMINI_API_KEY in .env.")


    # Load universal knowledge from Assets
    inv_knowledge_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'universal_knowledge.txt')
    universal_knowledge = ""
    if os.path.exists(inv_knowledge_path):
        with open(inv_knowledge_path, "r", encoding="utf-8") as f:
            universal_knowledge = f.read()

    # Load spending patterns knowledge
    spend_knowledge_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'spending_patterns.txt')
    spending_patterns = ""
    if os.path.exists(spend_knowledge_path):
        with open(spend_knowledge_path, "r", encoding="utf-8") as f:
            spending_patterns = f.read()
            
    # Load tax laws knowledge
    tax_knowledge_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'tax_laws.txt')
    tax_laws = ""
    if os.path.exists(tax_knowledge_path):
        with open(tax_knowledge_path, "r", encoding="utf-8") as f:
            tax_laws = f.read()

    # Load indian currency protocol knowledge
    indian_currency_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'indian_currency_protocol.txt')
    indian_currency_protocol = ""
    if os.path.exists(indian_currency_path):
        with open(indian_currency_path, "r", encoding="utf-8") as f:
            indian_currency_protocol = f.read()

    # Load UPI settlement analytics knowledge
    upi_knowledge_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'upi_settlement_analytics.txt')
    upi_settlement_knowledge = ""
    if os.path.exists(upi_knowledge_path):
        with open(upi_knowledge_path, "r", encoding="utf-8") as f:
            upi_settlement_knowledge = f.read()

    sys_msg = (
        "You are an intelligent AI Financial Advisor and Business Analytics Assistant. Help the user analyze market data, summarize financial reports, "
        "explain basic investment concepts, analyze personal & business spending patterns, and provide personalized budgeting & UPI settlement advice. "
        "Always remind them that you are an AI and this is not professional financial advice.\n"
        "When asked for a comprehensive financial report or to analyze a client's financial situation, ALWAYS use the `analyze_all_client_assets` tool to read all files in the Assets folder, and base your report on that data.\n\n"
        "UPI TRANSACTION & BUSINESS SETTLEMENT TRACKING:\n"
        "When the user asks about UPI transactions, merchant payouts, bank settlements, fee reconciliations, or UTR statuses:\n"
        "1. Use `analyze_upi_settlements_and_transactions` to provide comprehensive transaction volume, fee breakdown (MDR + GST), and generate the 7-day settlement trend chart.\n"
        "2. Use `check_merchant_settlement_batches` to inspect bank UTR records, settlement lag (T+1/T+2), and reconciliation variance.\n"
        "3. Apply the UPI Settlement Guidelines below to explain the lifecycle, fee breakdown, and NPCI clearance mechanisms:\n"
        f"{upi_settlement_knowledge}\n\n"
        "INDIAN FINANCIAL SYSTEM & CURRENCY PROTOCOL:\n"
        f"{indian_currency_protocol}\n\n"
        "SPENDING ANALYSIS INSTRUCTIONS:\n"
        "When a user provides their spending details or asks for spending analysis, you MUST:\n"
        "1. Analyze their spending pattern and compare it against the national averages provided in the NATIONAL SPENDING PATTERNS data.\n"
        "2. Generate a custom financial and budgeting plan for them based on this comparison.\n"
        "3. Suggest appropriate investment options from the INVESTMENT RECOMMENDATIONS KNOWLEDGE BASE as the final step of the plan.\n\n"
        "TAX PLANNING INSTRUCTIONS:\n"
        "When a user asks about taxes, tax savings, or when you are generating a comprehensive financial plan:\n"
        "1. Use the TAX SAVING LAWS & RULES below to determine if they should opt for the Old or New Tax Regime.\n"
        "2. Recommend specific deductions (80C, 80D, NPS) based on their profile.\n"
        "3. If you lack information (like their salary, rent, or home loan status), explicitly ask them for it before giving a final recommendation on the tax regime.\n\n"
        "TAX SAVING LAWS & RULES:\n"
        f"{tax_laws}\n\n"
        "NATIONAL SPENDING PATTERNS (HCES 2023-24):\n"
        f"{spending_patterns}\n\n"
        "INVESTMENT RECOMMENDATIONS KNOWLEDGE BASE:\n"
        "When the user is trying to improve their savings, searching for investment options, or after analyzing their spending, proactively offer the following as a suggestion:\n"
        f"{universal_knowledge}"
    )
    
    try:
        # Latest versions
        agent = create_react_agent(llm, tools=tools, state_modifier=sys_msg)
    except Exception:
        try:
            # Fallback for older versions if needed
            agent = create_react_agent(llm, tools=tools, messages_modifier=sys_msg)
        except Exception:
            agent = create_react_agent(llm, tools=tools)

            agent = create_react_agent(llm, tools=tools)
    return agent

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Welcome to the AI Financial Advisor CLI  ")
    print("Type 'exit' or 'quit' to close the application.")
    print("="*50 + "\n")
    
    try:
        agent = initialize_agent()
        print("\033[92m[System]: Agent successfully initialized. Ready to chat!\033[0m\n")
    except Exception as e:
        print(f"\033[91m[Error]: Failed to initialize agent: {e}\033[0m")
        exit(1)
        
    while True:
        try:
            user_input = input("\033[94mYou:\033[0m ")
            if not user_input.strip():
                continue
                
            if user_input.lower() in ['exit', 'quit']:
                print("\033[93mGoodbye! Have a great day.\033[0m")
                break
                
            inputs = {"messages": [("user", user_input)]}
            print("\033[90mThinking...\033[0m")
            
            for s in agent.stream(inputs, stream_mode="values"):
                message = s["messages"][-1]
                # Skip printing the user's own message back to them
                if message.type == "user":
                    continue
                message.pretty_print()
                
            print("-" * 50)
            
        except KeyboardInterrupt:
            print("\n\033[93mGoodbye!\033[0m")
            break
        except Exception as e:
            print(f"\n\033[91m[Error during execution]: {e}\033[0m\n")
