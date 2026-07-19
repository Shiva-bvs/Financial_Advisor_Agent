import os
import requests
from dotenv import load_dotenv
import finnhub
from alpha_vantage.timeseries import TimeSeries
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@tool
def get_stock_price(symbol: str) -> str:
    """Get the current stock price for a given ticker symbol."""
    finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    res = finnhub_client.quote(symbol.upper())
    current_price = res.get('c')
    return f"The current price of {symbol.upper()} is ${current_price}"

@tool
def get_financial_news(query: str) -> str:
    """Get the latest financial news related to a specific query."""
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
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/pair/{base_currency.upper()}/{target_currency.upper()}"
    response = requests.get(url)
    data = response.json()
    rate = data.get("conversion_rate")
    return f"The exchange rate from {base_currency.upper()} to {target_currency.upper()} is {rate}."

vector_store = None
pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets', 'financial_report.pdf')
if os.path.exists(pdf_path) and GEMINI_API_KEY:
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GEMINI_API_KEY)
    vector_store = Chroma.from_documents(documents=splits, embedding=embeddings)

@tool
def search_financial_report(query: str) -> str:
    """Search the internal financial report PDF for information."""
    if vector_store is None:
        return "Financial report PDF not loaded."
    docs = vector_store.similarity_search(query, k=3)
    return "\n".join([doc.page_content for doc in docs])

@tool
def calculate_compound_interest(principal: float, rate: float, time: int) -> str:
    """Calculate the future value of an investment using compound interest."""
    amount = principal * (1 + rate/100) ** time
    return f"The future value of a ${principal} investment at {rate}% over {time} years is ${amount:.2f}."

def initialize_agent():
    tools = [get_stock_price, get_financial_news, get_exchange_rate, search_financial_report, calculate_compound_interest]
    
    if GROQ_API_KEY:
        llm = ChatGroq(temperature=0, model_name="llama3-70b-8192", groq_api_key=GROQ_API_KEY)
    else:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=GEMINI_API_KEY)

    sys_msg = "You are a basic Financial Advisor AI. Help the user analyze market data, summarize financial reports, and explain basic investment concepts. Always remind them that you are an AI and this is not professional financial advice."
    agent = create_react_agent(llm, tools=tools, state_modifier=sys_msg)
    return agent

if __name__ == "__main__":
    agent = initialize_agent()
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        inputs = {"messages": [("user", user_input)]}
        for s in agent.stream(inputs, stream_mode="values"):
            message = s["messages"][-1]
            message.pretty_print()
