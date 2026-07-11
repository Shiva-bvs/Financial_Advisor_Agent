# 💰 Financial Advisor & Expense Manager AI Agent

An AI-powered personal finance assistant that delivers personalized financial advice grounded in the philosophies of leading financial gurus, while automating expense tracking from payment screenshots, bank statements, and Splitwise data.

> Built as part of an 8-week AI agent development project focused on FinTech & personal wealth management.

---

## 👥 Team
| Name | Role |
|Shiva Teja|Leader|
|Rohan Kumar Reddy|Designer|
| — | — |
| — | — |

---

## 📖 Overview

This agent combines **OCR-based expense extraction**, **financial data analysis**, and **AI-driven advisory** to give users a single assistant for both understanding their spending and improving their financial decisions.

Users can:
- Upload payment screenshots, receipts, and bank statements for automatic expense extraction
- Sync expense-sharing data via Splitwise
- Upload financial books/articles to ground advice in specific methodologies
- Receive categorized spending analysis, budgeting recommendations, and personalized financial guidance

---

## 🧭 Project Tracks

This repo supports two development tracks — choose based on team scope and timeline.

### Track A: Essential *(Recommended)*
- **Focus:** Core financial advice + expense tracking with strong fundamentals
- **Domain:** Personal Finance Assistant **or** Expense Tracking Agent
- **APIs:** 2–3 integrations (OCR + Financial Advice + Basic Expense Analysis)
- **Framework:** Standard LangChain with financial tools
- **UI:** Streamlit financial dashboard
- **Deployment:** Streamlit Cloud (single platform)
- **Features:** Screenshot expense extraction, basic financial advice, spending categorization, simple budgeting

*(Add Track B / Advanced details here if applicable to your team's scope.)*

---

## 🎯 Learning Outcomes

By completing this project, contributors will gain experience in:

- **Financial Data Processing** — extracting and categorizing expenses from screenshots, messages, and files
- **OCR & Text Extraction** — automated processing of payment screenshots and financial documents
- **Financial Advisory Systems** — generating personalized advice based on established financial methodologies
- **Expense Analytics** — building spending analysis and budgeting recommendation engines
- **Multi-Source Content Integration** — synthesizing financial books, articles, and user data
- **Financial UX Design** — building intuitive interfaces for personal finance management

---

## 🛠️ Tech Stack & APIs

### OCR & Text Processing *(choose 1–2)*
| Option | Use Case |
|---|---|
| Google Vision API | Text extraction from screenshots/receipts |
| Amazon Textract | Advanced document/statement processing |
| Tesseract OCR | Open-source text recognition |
| Azure Computer Vision | Multi-language document processing |

### Financial Data Sources
- **Splitwise API** — expense sharing & group payment data
- **Bank APIs** — sandbox integrations where available
- **UPI Transaction Data** — PhonePe, Google Pay, Paytm
- **Credit Card APIs** — statement processing & categorization
- **Manual Upload** — bank statements, receipts, financial documents

### Indian Financial Context
- Indian banking statement formats (SBI, HDFC, ICICI)
- UPI payment app integrations
- India-specific expense categories (groceries, transport, dining, etc.)
- Indian tax slabs, deductions, and investment options
- Investment platform references (Zerodha, Groww, ET Money)

### Financial Content & Advisory Sources
- Financial book PDF processing
- Guru-based principles (e.g., Warren Buffett, Robert Kiyosaki, Ramit Sethi)
- India-adapted finance expert content
- Scraped content from reputable financial advice sites
- Investment strategy content (SIP, mutual funds, stock market guidance)

### Document Processing
- `PyPDF2` — financial book/document parsing
- `python-docx` — planning templates & reports
- CSV processing — bank statement/transaction handling
- Image processing — receipt & screenshot analysis
- Regex — transaction message parsing & categorization

### Core Framework
- **LangChain** (standard, with financial tool integrations)
- **Streamlit** (UI & dashboard)

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- pip / virtualenv
- API keys for chosen OCR provider and any financial data integrations

### Installation
```bash
git clone https://github.com/<your-org>/financial-advisor-agent.git
cd financial-advisor-agent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration
Create a `.env` file in the project root:
```env
OCR_API_KEY=your_ocr_provider_key
SPLITWISE_API_KEY=your_splitwise_key
LLM_API_KEY=your_llm_provider_key
```

### Run Locally
```bash
streamlit run app.py
```

---

## 📁 Project Structure
```
financial-advisor-agent/
├── app.py                  # Streamlit entry point
├── src/
│   ├── ocr/                # Screenshot/receipt text extraction
│   ├── expense_analysis/   # Categorization & spending analytics
│   ├── advisory/           # Guru-based advice generation
│   ├── integrations/       # Splitwise, bank, UPI connectors
│   └── document_processing/# PDF/CSV/DOCX handling
├── data/                   # Sample statements, screenshots (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## ✨ Core Features (Track A)
- 📸 **Screenshot Expense Extraction** — upload a payment screenshot, get a structured transaction
- 💡 **Basic Financial Advice** — guidance grounded in established financial philosophies
- 🏷️ **Spending Categorization** — automatic tagging (groceries, transport, dining, etc.)
- 📊 **Simple Budgeting** — spending summaries and budget recommendations

---

## 🗺️ Roadmap
- [ ] OCR pipeline for screenshots/receipts
- [ ] Splitwise integration
- [ ] Expense categorization engine
- [ ] Financial advisory module (guru-grounded)
- [ ] Streamlit dashboard
- [ ] Deployment to Streamlit Cloud



---

## ⚠️ Disclaimer
This tool provides general, educational financial information generated by AI based on public financial philosophies and user-provided data. It is **not** a substitute for professional financial, tax, or investment advice.

---

## 📄 License
Specify your license here (e.g., MIT).
