import streamlit as st
import os
import json
import pandas as pd
from PIL import Image
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from App.financial_agent import initialize_agent, add_pdf_to_knowledgebase

st.set_page_config(page_title="AI Financial Advisor", layout="wide")

@st.cache_resource
def get_agent():
    return initialize_agent()

try:
    agent = get_agent()
except Exception as e:
    st.error(f"Failed to initialize agent: {e}")
    st.stop()

st.title("AI Financial Advisor")

# Sidebar for file uploads
with st.sidebar:
    st.header("Data Sources")
    
    st.subheader("1. Financial Guru Advice (PDF)")
    pdf_file = st.file_uploader("Upload a financial book/article", type=["pdf"])
    if pdf_file:
        # Save temp and add to knowledgebase
        temp_pdf_path = os.path.join(os.path.dirname(__file__), "Assets", "temp_uploaded.pdf")
        os.makedirs(os.path.dirname(temp_pdf_path), exist_ok=True)
        with open(temp_pdf_path, "wb") as f:
            f.write(pdf_file.getbuffer())
        with st.spinner("Processing PDF..."):
            res = add_pdf_to_knowledgebase(temp_pdf_path)
            st.success(res)
            
    st.subheader("2. Expense Data (CSV)")
    csv_file = st.file_uploader("Upload expenses (CSV)", type=["csv"])
    if csv_file:
        try:
            df = pd.read_csv(csv_file)
            st.write("Preview:", df.head(3))
            if st.button("Analyze CSV Expenses"):
                # Send to agent as JSON
                expenses_json = df.to_json(orient="records")
                with st.spinner("Analyzing..."):
                    prompt = f"Analyze these expenses and give me budget recommendations: {expenses_json}"
                    if "messages" not in st.session_state:
                        st.session_state.messages = []
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    st.rerun()
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

    st.subheader("3. Receipts & Screenshots (Image)")
    img_file = st.file_uploader("Upload receipt or bank statement screenshot", type=["png", "jpg", "jpeg"])
    if img_file:
        image = Image.open(img_file)
        st.image(image, caption="Uploaded Image", use_container_width=True)
        
        # Save image to Assets
        temp_img_path = os.path.join(os.path.dirname(__file__), "Assets", "uploaded_screenshot.png")
        os.makedirs(os.path.dirname(temp_img_path), exist_ok=True)
        image.save(temp_img_path)
        
        if st.button("Generate Financial Report from PDF & Image"):
            st.info("Sending request to agent...")
            prompt = "Generate a comprehensive financial report about my financial condition. I have uploaded a financial document to the knowledgebase (PDF), and provided a screenshot named 'uploaded_screenshot.png'. Please extract the data from both and provide a full analysis."
            if "messages" not in st.session_state:
                st.session_state.messages = []
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.rerun()
            
    st.subheader("4. Splitwise Integration")
    if st.button("Fetch Group Expenses"):
        prompt = "Fetch my recent Splitwise expenses and analyze my spending patterns."
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()
        
    st.subheader("5. Google Drive Integration")
    if st.button("Search Drive for Budget"):
        prompt = "Search my Google Drive for financial spreadsheets and budget documents."
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

    st.subheader("6. Gmail Integration")
    if st.button("Fetch Email Receipts"):
        prompt = "Fetch my recent email receipts and invoices from Gmail."
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()



# Main Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Check for new user input
if prompt := st.chat_input("Ask your financial advisor anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

# If the last message is from the user, get a response from the agent
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Construct message history for the agent
            # We will just pass the whole conversation to the agent so it remembers context
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
            
            # Display chart if it was generated
            chart_path = os.path.join(os.path.dirname(__file__), "Assets", "spending_chart.png")
            if os.path.exists(chart_path) and "spending_chart.png" in final_response:
                st.image(chart_path)
