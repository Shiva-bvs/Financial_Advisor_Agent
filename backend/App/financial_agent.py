import os
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

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_DRIVE_API_KEY = os.getenv("GOOGLE_DRIVE_API_KEY")
GMAIL_API_KEY = os.getenv("GMAIL_API_KEY")

embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
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
        analyze_all_client_assets
    ]
    
    if GROQ_API_KEY:
        llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY)
    elif GEMINI_API_KEY:
        llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0, google_api_key=GEMINI_API_KEY)
    else:
        raise ValueError("No LLM API key provided. Set GROQ_API_KEY or GEMINI_API_KEY.")

    sys_msg = (
        "You are an intelligent AI Financial Advisor. Help the user analyze market data, summarize financial reports, "
        "explain basic investment concepts, analyze spending patterns, and provide personalized budgeting advice. "
        "Always remind them that you are an AI and this is not professional financial advice."
    )
    try:
        # Latest versions
        agent = create_react_agent(llm, tools=tools)
    except Exception:
        # Fallback for older versions if needed
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
                
            sys_msg_text = (
                "You are an intelligent AI Financial Advisor. Help the user analyze market data, summarize financial reports, "
                "explain basic investment concepts, analyze spending patterns, and provide personalized budgeting advice. "
                "Always remind them that you are an AI and this is not professional financial advice. "
                "When asked for a comprehensive financial report or to analyze a client's financial situation, ALWAYS use the `analyze_all_client_assets` tool to read all files in the Assets folder, and base your report on that data."
            )
            inputs = {"messages": [("system", sys_msg_text), ("user", user_input)]}
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
