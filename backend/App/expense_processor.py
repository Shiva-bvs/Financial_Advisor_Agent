import os
import io
import json
import re
import base64
import datetime
import pandas as pd
from PIL import Image

# Import reportlab for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# --- 1. COLUMN NORMALIZATION & VALIDATION ---

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dataframe column names to standard keys: date, category, amount, description."""
    col_map = {}
    for col in df.columns:
        col_lower = str(col).strip().lower().replace(" ", "_").replace("-", "_")
        if any(k in col_lower for k in ["txn_date", "transaction_date", "date", "dt", "time"]):
            col_map[col] = "date"
        elif any(k in col_lower for k in ["cat", "category", "type", "expense_type", "tag"]):
            col_map[col] = "category"
        elif any(k in col_lower for k in ["amt", "amount", "cost", "price", "val", "value", "spent", "debit"]):
            col_map[col] = "amount"
        elif any(k in col_lower for k in ["desc", "description", "details", "merchant", "item", "narration", "payee"]):
            col_map[col] = "description"
    
    df = df.rename(columns=col_map)
    return df

def validate_and_clean_expenses_df(df: pd.DataFrame) -> dict:
    """
    Validate and clean an expense DataFrame.
    Returns a dict with 'success', 'data' (clean DF), 'errors', 'warnings', 'total_count'.
    """
    errors = []
    warnings = []
    
    if df.empty:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": ["Uploaded file is empty."],
            "warnings": [],
            "total_count": 0
        }
        
    df = _normalize_columns(df)
    
    # Check required columns
    required = ["amount"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"Missing mandatory column: {', '.join(missing)}. File must contain an 'amount' column."],
            "warnings": [],
            "total_count": 0
        }

    # Add missing optional columns if not present
    if "date" not in df.columns:
        df["date"] = datetime.date.today().isoformat()
        warnings.append("Date column not found. Defaulted to today's date.")
    if "category" not in df.columns:
        df["category"] = "Uncategorized"
        warnings.append("Category column not found. Defaulted to 'Uncategorized'.")
    if "description" not in df.columns:
        df["description"] = "Expense item"

    clean_rows = []
    today = datetime.date.today()
    
    for idx, row in df.iterrows():
        row_num = idx + 1
        
        # Clean amount
        raw_amt = row["amount"]
        try:
            # Handle currency symbols like $ or ₹ or commas
            if isinstance(raw_amt, str):
                cleaned_amt_str = re.sub(r"[^\d.-]", "", raw_amt)
                amt = float(cleaned_amt_str) if cleaned_amt_str else 0.0
            else:
                amt = float(raw_amt)
        except Exception:
            errors.append(f"Row {row_num}: Invalid amount format '{raw_amt}'. Row skipped.")
            continue

        if amt <= 0:
            warnings.append(f"Row {row_num}: Non-positive amount '{amt}'. Skipped or flagged.")
            continue

        # Clean date
        raw_date = row["date"]
        parsed_date_str = today.isoformat()
        try:
            if pd.notnull(raw_date):
                dt = pd.to_datetime(raw_date, errors="coerce")
                if not pd.isnull(dt):
                    parsed_date_str = dt.strftime("%Y-%m-%d")
                    if dt.date() > today:
                        warnings.append(f"Row {row_num}: Future date detected ({parsed_date_str}).")
        except Exception:
            warnings.append(f"Row {row_num}: Could not parse date '{raw_date}'. Defaulted to today.")

        # Clean category & description
        cat = str(row["category"]).strip().title() if pd.notnull(row["category"]) else "Uncategorized"
        if not cat or cat.lower() in ["nan", "none", "null", ""]:
            cat = "Uncategorized"
            
        desc = str(row["description"]).strip() if pd.notnull(row["description"]) else f"Expense in {cat}"
        if not desc or desc.lower() in ["nan", "none", "null", ""]:
            desc = f"Expense in {cat}"

        clean_rows.append({
            "date": parsed_date_str,
            "category": cat,
            "amount": round(amt, 2),
            "description": desc
        })

    if not clean_rows:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": errors or ["No valid rows could be processed from file."],
            "warnings": warnings,
            "total_count": 0
        }

    clean_df = pd.DataFrame(clean_rows)
    # Sort by date descending
    clean_df = clean_df.sort_values(by="date", ascending=False).reset_index(drop=True)

    return {
        "success": True,
        "data": clean_df,
        "errors": errors,
        "warnings": warnings,
        "total_count": len(clean_df)
    }

# --- 2. MULTI-FORMAT FILE PARSERS ---

def parse_csv_expenses(file_bytes_or_buffer) -> dict:
    """Parse CSV expense file."""
    try:
        df = pd.read_csv(file_bytes_or_buffer)
        return validate_and_clean_expenses_df(df)
    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"CSV parsing error: {str(e)}. Please ensure valid CSV formatting."],
            "warnings": [],
            "total_count": 0
        }

def parse_excel_expenses(file_bytes_or_buffer) -> dict:
    """Parse Excel (.xlsx, .xls) expense file."""
    try:
        df = pd.read_excel(file_bytes_or_buffer)
        return validate_and_clean_expenses_df(df)
    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"Excel parsing error: {str(e)}. Please install openpyxl or check file format."],
            "warnings": [],
            "total_count": 0
        }

def parse_json_expenses(file_bytes_or_buffer) -> dict:
    """Parse JSON expense file or payload."""
    try:
        if isinstance(file_bytes_or_buffer, (bytes, bytearray)):
            content = file_bytes_or_buffer.decode("utf-8")
        elif isinstance(file_bytes_or_buffer, str):
            content = file_bytes_or_buffer
        else:
            content = file_bytes_or_buffer.read().decode("utf-8")
            
        data = json.loads(content)
        if isinstance(data, dict):
            if "expenses" in data:
                data = data["expenses"]
            elif "transactions" in data:
                data = data["transactions"]
            elif "items" in data:
                data = data["items"]
            else:
                data = [data]
                
        if not isinstance(data, list):
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "errors": ["JSON must contain a list of expense objects or key 'expenses'."],
                "warnings": [],
                "total_count": 0
            }
            
        df = pd.DataFrame(data)
        return validate_and_clean_expenses_df(df)
    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"JSON parsing error: {str(e)}. Check JSON syntax."],
            "warnings": [],
            "total_count": 0
        }

def parse_pdf_expenses(file_bytes_or_buffer) -> dict:
    """
    Extract text from uploaded PDF bank statement or bill and convert to expenses.
    """
    try:
        from langchain_community.document_loaders import PyPDFLoader
        import tempfile
        
        # Save temp PDF
        if isinstance(file_bytes_or_buffer, (bytes, bytearray)):
            pdf_data = file_bytes_or_buffer
        else:
            pdf_data = file_bytes_or_buffer.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_data)
            tmp_path = tmp.name

        loader = PyPDFLoader(tmp_path)
        docs = loader.load()
        text = "\n".join([doc.page_content for doc in docs])
        os.remove(tmp_path)

        if not text.strip():
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "errors": ["PDF appears to be empty or contains scanned images without text layer."],
                "warnings": ["For scanned PDFs, please upload as PNG/JPG receipt image for OCR processing."],
                "total_count": 0
            }

        # Pattern match for typical bank statement line items: date, description, amount
        lines = text.split("\n")
        extracted_rows = []
        pattern = re.compile(r"(\d{2,4}[-/\.]\d{1,2}[-/\.]\d{1,4})\s+(.+?)\s+([₹\$]?\s*[\d,]+\.\d{2})")

        for line in lines:
            match = pattern.search(line)
            if match:
                dt_str, desc_str, amt_str = match.groups()
                amt_clean = float(re.sub(r"[^\d.]", "", amt_str))
                extracted_rows.append({
                    "date": dt_str,
                    "category": "Bank Statement",
                    "amount": amt_clean,
                    "description": desc_str.strip()
                })

        if not extracted_rows:
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "errors": ["Could not automatically parse tabular transactions from this PDF structure."],
                "warnings": ["Tip: Use standard CSV/Excel statement downloads or upload receipt image for OCR."],
                "total_count": 0
            }

        df = pd.DataFrame(extracted_rows)
        return validate_and_clean_expenses_df(df)

    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"PDF extraction error: {str(e)}"],
            "warnings": [],
            "total_count": 0
        }

# --- 3. RECEIPT OCR PROCESSING WITH DIAGNOSTICS ---

def process_receipt_ocr(image_bytes: bytes, filename: str = "receipt.png", api_key: str = None) -> dict:
    """
    Process a receipt/invoice image using Gemini Vision model.
    Provides comprehensive diagnostic status and friendly error messaging.
    """
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
        
    if not api_key:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "extracted_items": [],
            "merchant": "Unknown",
            "total_amount": 0.0,
            "errors": ["GEMINI_API_KEY is not configured in .env file."],
            "troubleshooting": [
                "1. Add GEMINI_API_KEY=your_key to backend/.env file.",
                "2. Ensure you have an active Google AI Studio API key.",
                "3. Alternatively, enter expenses manually or upload CSV/Excel."
            ]
        }

    try:
        encoded_img = base64.b64encode(image_bytes).decode("utf-8")
        ext = filename.lower().split(".")[-1]
        if ext not in ["png", "jpg", "jpeg", "webp"]:
            ext = "png"

        llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key)
        
        prompt = (
            "Analyze this receipt or bill image. Extract all purchase items and return ONLY a valid JSON object matching this structure:\n"
            "{\n"
            '  "merchant": "Merchant or Store Name",\n'
            '  "date": "YYYY-MM-DD",\n'
            '  "total_amount": 150.00,\n'
            '  "category": "Food & Dining / Groceries / Shopping / Utilities / General",\n'
            '  "items": [\n'
            '     {"description": "Item 1 Name", "amount": 50.00, "category": "Food"},\n'
            '     {"description": "Item 2 Name", "amount": 100.00, "category": "Food"}\n'
            '  ]\n'
            "}\n"
            "If total_amount cannot be determined, sum the items. Do NOT wrap in markdown codeblocks if possible, or return raw JSON."
        )

        msg = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{encoded_img}"}}
            ]
        )

        response = llm.invoke([msg])
        content = response.content.strip()

        # Clean JSON from response
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)
        merchant = parsed.get("merchant", "Receipt Store")
        receipt_date = parsed.get("date", datetime.date.today().isoformat())
        total_amt = float(parsed.get("total_amount", 0.0))
        main_cat = parsed.get("category", "Shopping")
        items = parsed.get("items", [])

        extracted_rows = []
        if items:
            for item in items:
                extracted_rows.append({
                    "date": receipt_date,
                    "category": item.get("category", main_cat).title(),
                    "amount": float(item.get("amount", 0.0)),
                    "description": f"{merchant}: {item.get('description', 'Purchase')}"
                })
        elif total_amt > 0:
            extracted_rows.append({
                "date": receipt_date,
                "category": main_cat.title(),
                "amount": total_amt,
                "description": f"Receipt from {merchant}"
            })

        if not extracted_rows:
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "merchant": merchant,
                "total_amount": total_amt,
                "errors": ["OCR completed but could not extract clear price/amount numbers from image."],
                "troubleshooting": [
                    "Ensure receipt image is clear, well-lit, and unblurred.",
                    "Crop the receipt to focus on store name, date, and line totals.",
                    "You can manually add this receipt using the 'Add Expense' form."
                ]
            }

        df = pd.DataFrame(extracted_rows)
        validated = validate_and_clean_expenses_df(df)
        validated["merchant"] = merchant
        validated["total_amount"] = total_amt
        return validated

    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "merchant": "Unknown",
            "total_amount": 0.0,
            "errors": [f"OCR processing failed: {str(e)}"],
            "troubleshooting": [
                "Verify image is a valid PNG, JPG, or WEBP file.",
                "Check internet connectivity and Gemini API key quota.",
                "Try uploading a higher contrast screenshot."
            ]
        }

# --- 4. SAMPLE TEMPLATE GENERATION ---

def generate_sample_csv() -> bytes:
    """Generate sample expense CSV bytes."""
    sample_data = """Date,Category,Amount,Description
2026-08-20,Groceries,4500.00,Supermarket Monthly Provision
2026-08-21,Dining Out,1250.00,Weekend Dinner with Family
2026-08-21,Utilities,3400.00,Electricity & Water Bill
2026-08-22,Transportation,850.00,Cab & Fuel Expense
2026-08-22,Shopping,5200.00,Clothing & Household
2026-08-23,Entertainment,2499.00,Movie Tickets & Streaming Subscriptions
2026-08-23,Savings & Investment,15000.00,Monthly SIP Investment
"""
    return sample_data.encode("utf-8")

def generate_sample_excel() -> bytes:
    """Generate sample expense Excel bytes."""
    output = io.BytesIO()
    df = pd.read_csv(io.BytesIO(generate_sample_csv()))
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Expenses", index=False)
    return output.getvalue()

def generate_sample_json() -> str:
    """Generate sample expense JSON string."""
    sample_dict = {
        "expenses": [
            {"date": "2026-08-20", "category": "Groceries", "amount": 4500.00, "description": "Supermarket Provision"},
            {"date": "2026-08-21", "category": "Dining Out", "amount": 1250.00, "description": "Weekend Dinner"},
            {"date": "2026-08-21", "category": "Utilities", "amount": 3400.00, "description": "Electricity & Water"},
            {"date": "2026-08-22", "category": "Transportation", "amount": 850.00, "description": "Cab & Fuel"},
            {"date": "2026-08-22", "category": "Shopping", "amount": 5200.00, "description": "Clothing"},
            {"date": "2026-08-23", "category": "Entertainment", "amount": 2499.00, "description": "Streaming Subscriptions"},
            {"date": "2026-08-23", "category": "Savings & Investment", "amount": 15000.00, "description": "Monthly SIP"}
        ]
    }
    return json.dumps(sample_dict, indent=2)

# --- 5. GURU FINANCIAL ADVICE ENGINE ---

def get_guru_recommendations(df: pd.DataFrame, monthly_income: float = 100000.0) -> dict:
    """
    Generate tailored financial guru advice based on user spending & income.
    """
    if df.empty:
        total_spend = 0.0
        cat_summary = {}
    else:
        total_spend = df["amount"].sum()
        cat_summary = df.groupby("category")["amount"].sum().to_dict()

    savings_rate = max(0.0, (monthly_income - total_spend) / monthly_income * 100.0) if monthly_income > 0 else 0.0
    
    # 1. Warren Buffett Insights
    buffett = [
        "**Rule No. 1: Never lose money. Rule No. 2: Never forget rule No. 1.**",
        f"Your current estimated savings rate is **{savings_rate:.1f}%**. Buffett recommends aiming for at least **20-30%** saved before spending.",
        "**Do not save what is left after spending, but spend what is left after saving.** Set up automated SIP transfer on payday.",
        "Invest in low-cost index funds (Nifty 50 / S&P 500) rather than trying to beat the market with speculative trades."
    ]

    # 2. Dave Ramsey Insights
    emergency_target = total_spend * 6.0 if total_spend > 0 else monthly_income * 3.0
    ramsey = [
        "**Baby Step 1**: Build a $1,000 / ₹50,000 starter emergency fund immediately.",
        "**Baby Step 2**: Pay off all non-mortgage debt using the **Debt Snowball** method (smallest balance first).",
        f"**Baby Step 3**: Build a full **3 to 6 months emergency fund** (Target: **₹{emergency_target:,.2f}** based on your monthly expenses).",
        "Avoid credit card debt and buy essentials with cash or debit to eliminate interest drag."
    ]

    # 3. Ramit Sethi Insights (Conscious Spending Plan)
    fixed_costs = sum(v for k, v in cat_summary.items() if any(c in k.lower() for c in ["rent", "housing", "utility", "bill", "grocery", "transport"]))
    guilt_free = sum(v for k, v in cat_summary.items() if any(c in k.lower() for c in ["dining", "entertainment", "shopping", "out"]))
    
    sethi = [
        "**Ramit Sethi's Conscious Spending Framework**:",
        f"- **Fixed Costs (Target: 50-60%)**: Currently ₹{fixed_costs:,.2f} ({ (fixed_costs/monthly_income*100) if monthly_income else 0:.1f}%)",
        f"- **Investments (Target: 10%)**: Automated monthly equity investments.",
        f"- **Savings Goals (Target: 5-10%)**: Emergency, vacations, large purchases.",
        f"- **Guilt-Free Spending (Target: 20-35%)**: Currently ₹{guilt_free:,.2f} ({ (guilt_free/monthly_income*100) if monthly_income else 0:.1f}%). Spend guilt-free on what you love, cut costs mercilessly on what you don't!"
    ]

    # 4. Morgan Housel Insights (Psychology of Money)
    housel = [
        "**Freedom is the highest dividend money pays.** Money's greatest intrinsic value is giving you control over your time.",
        "**Wealth is what you don't see.** Wealth is the cars not purchased, the watches not worn, and the impulse buys declined.",
        "Room for error (Margin of Safety) is the single most important part of any financial plan."
    ]

    # 5. Benjamin Graham Insights (The Intelligent Investor)
    graham = [
        "**Margin of Safety**: Never pay more for an asset than its intrinsic value.",
        "Distinguish between **Investment** (thorough analysis, safety of principal, adequate return) and **Speculation**.",
        "Maintain a defensive allocation between equity index funds and fixed income (e.g. 50/50 or 60/40) rebalanced annually."
    ]

    return {
        "summary": {
            "total_spend": total_spend,
            "monthly_income": monthly_income,
            "savings_rate": savings_rate,
            "emergency_target": emergency_target
        },
        "gurus": {
            "Warren Buffett": buffett,
            "Dave Ramsey": ramsey,
            "Ramit Sethi": sethi,
            "Morgan Housel": housel,
            "Benjamin Graham": graham
        }
    }

# --- 6. REPORT & EXPORT GENERATORS ---

def generate_pdf_report(df: pd.DataFrame, budgets: dict, goals: list, monthly_income: float = 100000.0) -> bytes:
    """
    Generate a styled PDF report using ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#1e293b'),
        alignment=0
    )
    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#0f766e'),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155')
    )

    # Title Banner
    story.append(Paragraph("💰 Executive Financial Advisory & Expense Report", title_style))
    story.append(Paragraph(f"Generated on {datetime.date.today().strftime('%B %d, %Y')} | Confidential", body_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f766e"), spaceAfter=15))

    # Executive Summary Table
    total_spend = df["amount"].sum() if not df.empty else 0.0
    savings = max(0.0, monthly_income - total_spend)
    savings_pct = (savings / monthly_income * 100.0) if monthly_income > 0 else 0.0

    summary_data = [
        ["Metric", "Value"],
        ["Monthly Income", f"INR {monthly_income:,.2f}"],
        ["Total Monthly Expenses", f"INR {total_spend:,.2f}"],
        ["Net Savings / Surplus", f"INR {savings:,.2f}"],
        ["Savings Rate", f"{savings_pct:.1f}%"],
        ["Total Recorded Transactions", str(len(df))]
    ]
    t_summary = Table(summary_data, colWidths=[200, 300])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#0f766e')),
        ('TEXTCOLOR', (0,0), (1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    story.append(Paragraph("1. Executive Summary", h2_style))
    story.append(t_summary)
    story.append(Spacer(1, 15))

    # Category Breakdown Table
    story.append(Paragraph("2. Expense Breakdown by Category", h2_style))
    if not df.empty:
        cat_df = df.groupby("category")["amount"].agg(["sum", "count"]).reset_index()
        cat_df["pct"] = (cat_df["sum"] / total_spend * 100.0)
        cat_df = cat_df.sort_values(by="sum", ascending=False)

        cat_data = [["Category", "Total Spent (INR)", "Txn Count", "Share (%)"]]
        for _, r in cat_df.iterrows():
            cat_data.append([
                r["category"],
                f"INR {r['sum']:,.2f}",
                str(r["count"]),
                f"{r['pct']:.1f}%"
            ])

        t_cat = Table(cat_data, colWidths=[180, 120, 100, 100])
        t_cat.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(t_cat)
    else:
        story.append(Paragraph("No expenses recorded.", body_style))

    story.append(Spacer(1, 15))

    # Guru Recommendations
    story.append(Paragraph("3. Financial Guru Principles & Strategic Advice", h2_style))
    gurus = get_guru_recommendations(df, monthly_income)["gurus"]
    for guru_name, insights in list(gurus.items())[:3]:
        story.append(Paragraph(f"<b>{guru_name} Guidance:</b>", body_style))
        for line in insights:
            clean_line = line.replace("**", "")
            story.append(Paragraph(f"• {clean_line}", body_style))
        story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()

def generate_excel_export(df: pd.DataFrame, budgets: dict, goals: list) -> bytes:
    """Generate Excel workbook with multiple tabs."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Expenses Tab
        if not df.empty:
            df.to_excel(writer, sheet_name="Transactions", index=False)
        else:
            pd.DataFrame(columns=["date", "category", "amount", "description"]).to_excel(writer, sheet_name="Transactions", index=False)

        # Summary Tab
        if not df.empty:
            summary = df.groupby("category")["amount"].agg(["sum", "mean", "count"]).reset_index()
            summary.columns = ["Category", "Total Spent", "Avg Transaction", "Transaction Count"]
            summary.to_excel(writer, sheet_name="Category Breakdown", index=False)

        # Budgets Tab
        if budgets:
            b_rows = []
            for cat, target in budgets.items():
                spent = df[df["category"] == cat]["amount"].sum() if not df.empty and "category" in df.columns else 0.0
                b_rows.append({
                    "Category": cat,
                    "Target Budget (INR)": target,
                    "Actual Spent (INR)": spent,
                    "Variance (INR)": target - spent,
                    "Status": "Over Budget" if spent > target else "Within Budget"
                })
            pd.DataFrame(b_rows).to_excel(writer, sheet_name="Budget Tracking", index=False)

        # Goals Tab
        if goals:
            pd.DataFrame(goals).to_excel(writer, sheet_name="Financial Goals", index=False)

    return output.getvalue()
