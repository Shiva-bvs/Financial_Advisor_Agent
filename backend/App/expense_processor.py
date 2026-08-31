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
    """Parse CSV expense file from bytes, string, or file-like buffer."""
    try:
        if isinstance(file_bytes_or_buffer, (bytes, bytearray)):
            file_bytes_or_buffer = io.BytesIO(file_bytes_or_buffer)
        elif isinstance(file_bytes_or_buffer, str):
            file_bytes_or_buffer = io.StringIO(file_bytes_or_buffer)
            
        df = pd.read_csv(file_bytes_or_buffer)
        return validate_and_clean_expenses_df(df)
    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"CSV parsing error: {str(e)}. Please ensure valid CSV formatting."],
            "warnings": [],
            "total_count": 0,
            "troubleshooting": [
                "1. Ensure the CSV contains an 'Amount' column with numeric values.",
                "2. Check that delimiter is comma (,) and text is UTF-8 encoded.",
                "3. Try downloading and using our Sample CSV template."
            ]
        }

def parse_excel_expenses(file_bytes_or_buffer) -> dict:
    """Parse Excel (.xlsx, .xls) expense file from bytes or file-like buffer."""
    try:
        if isinstance(file_bytes_or_buffer, (bytes, bytearray)):
            file_bytes_or_buffer = io.BytesIO(file_bytes_or_buffer)
            
        df = pd.read_excel(file_bytes_or_buffer)
        return validate_and_clean_expenses_df(df)
    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"Excel parsing error: {str(e)}. Please check file integrity."],
            "warnings": [],
            "total_count": 0,
            "troubleshooting": [
                "1. Ensure openpyxl is installed and file extension is .xlsx or .xls.",
                "2. Check that the first worksheet contains standard headers (Date, Category, Amount, Description).",
                "3. Ensure the spreadsheet is not password-protected."
            ]
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
                "errors": ["JSON must contain a list of expense objects or an 'expenses' key."],
                "warnings": [],
                "total_count": 0,
                "troubleshooting": [
                    "Format should be: {'expenses': [{'date': 'YYYY-MM-DD', 'category': 'Food', 'amount': 150.0, 'description': 'Lunch'}]}",
                    "Download our Sample JSON template for the exact schema."
                ]
            }
            
        df = pd.DataFrame(data)
        return validate_and_clean_expenses_df(df)
    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"JSON parsing error: {str(e)}. Check JSON syntax."],
            "warnings": [],
            "total_count": 0,
            "troubleshooting": [
                "1. Ensure valid JSON syntax (double quotes for keys/strings, no trailing commas).",
                "2. Verify UTF-8 file encoding."
            ]
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
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        if not text.strip():
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "errors": ["PDF appears to be empty or contains scanned images without a selectable text layer."],
                "warnings": ["For scanned or photographed receipts/bills, please upload directly as PNG/JPG for Vision OCR processing."],
                "total_count": 0,
                "troubleshooting": [
                    "1. If this is a digital bank statement, ensure it is not password-protected.",
                    "2. If this is a scanned photo inside a PDF, export the page as an image (JPG/PNG) and upload to OCR.",
                    "3. Export your bank statement in CSV/Excel format for 100% precision."
                ]
            }

        # Pattern match for typical bank statement line items: date, description, amount
        lines = text.split("\n")
        extracted_rows = []
        pattern = re.compile(r"(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})\s+(.+?)\s+([₹\$]?\s*[\d,]+\.\d{2})")

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
                "errors": ["Could not automatically parse tabular transactions from this specific PDF layout."],
                "warnings": ["Tip: Use standard CSV/Excel statement downloads from your banking portal or upload receipt image for OCR."],
                "total_count": 0,
                "troubleshooting": [
                    "1. Indian bank statements (SBI, HDFC, ICICI) vary significantly across branches.",
                    "2. Download the statement in CSV/XLS format directly from your NetBanking portal for instant ingestion.",
                    "3. Or enter expenses via the Manual Expense form on the right."
                ]
            }

        df = pd.DataFrame(extracted_rows)
        return validate_and_clean_expenses_df(df)

    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"PDF extraction error: {str(e)}"],
            "warnings": [],
            "total_count": 0,
            "troubleshooting": [
                "Ensure pypdf/langchain-community is installed and the PDF is not encrypted."
            ]
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
            "errors": ["GEMINI_API_KEY is not configured in backend/.env file."],
            "troubleshooting": [
                "1. Open or create the `backend/.env` file.",
                "2. Add your Google Gemini API key: `GEMINI_API_KEY=your_actual_key_here`.",
                "3. Get a free API key at https://aistudio.google.com.",
                "4. Alternatively, use the Manual Expense form or upload CSV/Excel files."
            ]
        }

    try:
        encoded_img = base64.b64encode(image_bytes).decode("utf-8")
        ext = filename.lower().split(".")[-1]
        if ext not in ["png", "jpg", "jpeg", "webp"]:
            ext = "png"

        # Try latest model names
        model_candidates = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-flash-latest"]
        llm = None
        for mod in model_candidates:
            try:
                llm = ChatGoogleGenerativeAI(model=mod, google_api_key=api_key)
                break
            except Exception:
                continue
                
        if not llm:
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
                    "1. Ensure receipt image is well-lit, sharp, and unblurred.",
                    "2. Crop the image to highlight the merchant header and itemized total section.",
                    "3. If the receipt is handwritten, manual entry via the form on the right is recommended."
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
                "1. Verify image is a valid PNG, JPG, JPEG, or WEBP file.",
                "2. Check internet connectivity and Google AI Studio API quota/rate limits.",
                "3. Try uploading a higher resolution or higher contrast image."
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

def parse_sms_transaction_text(sms_text: str) -> dict:
    """
    Parse Indian banking and UPI SMS transaction alerts (SBI, HDFC, ICICI, GPay, PhonePe, Paytm).
    Extracts date, amount, merchant/payee, and category.
    """
    if not sms_text or not sms_text.strip():
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": ["SMS text input is empty."],
            "warnings": [],
            "total_count": 0
        }

    lines = [line.strip() for line in sms_text.strip().split("\n") if line.strip()]
    extracted = []
    today_str = datetime.date.today().isoformat()

    amt_pattern = re.compile(r"(?:(?:INR|RS\.?|INR\.|₹)\s*|debited\s+by\s+|spent\s+)([\d,]+\.?\d*)", re.IGNORECASE)
    date_pattern = re.compile(r"(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})")
    merchant_pattern = re.compile(r"(?:at|to|for|vpa|merchant)\s+([A-Za-z0-9\s&_\.\-]+?)(?:\s+on|\s+via|\s+ref|\s+upi|\.|$)", re.IGNORECASE)

    for line in lines:
        amt_match = amt_pattern.search(line)
        if amt_match:
            try:
                amt_str = amt_match.group(1).replace(",", "")
                amt = float(amt_str)
                if amt <= 0: continue
            except Exception:
                continue

            # Extract date
            dt_match = date_pattern.search(line)
            dt_val = today_str
            if dt_match:
                try:
                    parsed_dt = pd.to_datetime(dt_match.group(1), errors="coerce")
                    if not pd.isnull(parsed_dt):
                        dt_val = parsed_dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            # Extract merchant
            merch_match = merchant_pattern.search(line)
            desc_val = merch_match.group(1).strip() if merch_match else "UPI / Card Payment"
            if len(desc_val) > 40:
                desc_val = desc_val[:40].strip()

            # Categorize based on keywords
            desc_lower = desc_val.lower()
            cat = "Shopping"
            if any(k in desc_lower for k in ["swiggy", "zomato", "restaurant", "cafe", "food", "dine", "kfc", "mcdonald"]):
                cat = "Dining Out"
            elif any(k in desc_lower for k in ["blinkit", "zepto", "instamart", "supermarket", "grocery", "dmart", "spencer"]):
                cat = "Groceries"
            elif any(k in desc_lower for k in ["uber", "ola", "metro", "fuel", "petrol", "hpcl", "bpcl", "rapido"]):
                cat = "Transportation"
            elif any(k in desc_lower for k in ["bescom", "electricity", "water", "airtel", "jio", "broadband", "bill", "gas"]):
                cat = "Utilities"
            elif any(k in desc_lower for k in ["netflix", "prime", "hotstar", "bookmyshow", "pvr", "movie"]):
                cat = "Entertainment"
            elif any(k in desc_lower for k in ["zerodha", "groww", "sip", "mutual", "ppf", "nps"]):
                cat = "Savings & Investment"
            elif any(k in desc_lower for k in ["pharmacy", "apollo", "medplus", "hospital", "clinic"]):
                cat = "Healthcare"

            extracted.append({
                "date": dt_val,
                "category": cat,
                "amount": round(amt, 2),
                "description": desc_val
            })

    if not extracted:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": ["Could not find valid transaction amount patterns in the pasted SMS text."],
            "warnings": [],
            "total_count": 0,
            "troubleshooting": [
                "Paste transaction SMS alerts containing keywords like 'debited INR', 'spent Rs.', or 'paid via UPI'.",
                "Example: 'Rs. 450 debited from A/c 1234 on 28-Aug-2026 at Swiggy via UPI'."
            ]
        }

    df = pd.DataFrame(extracted)
    return validate_and_clean_expenses_df(df)

def parse_splitwise_expenses(file_bytes_or_buffer, user_name: str = None) -> dict:
    """
    Parse Splitwise export CSV file and extract user's net expense share.
    """
    try:
        if isinstance(file_bytes_or_buffer, (bytes, bytearray)):
            file_bytes_or_buffer = io.BytesIO(file_bytes_or_buffer)
        elif isinstance(file_bytes_or_buffer, str):
            file_bytes_or_buffer = io.StringIO(file_bytes_or_buffer)

        df = pd.read_csv(file_bytes_or_buffer)
        
        # Look for standard Splitwise CSV columns
        col_lower = {str(c).lower().strip(): c for c in df.columns}
        
        # Check date and cost
        date_col = next((col_lower[c] for c in ["date", "datetime", "created_at"] if c in col_lower), None)
        desc_col = next((col_lower[c] for c in ["description", "details", "expense"] if c in col_lower), None)
        cat_col = next((col_lower[c] for c in ["category", "type"] if c in col_lower), None)
        cost_col = next((col_lower[c] for c in ["cost", "amount", "total"] if c in col_lower), None)

        if not cost_col:
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "errors": ["Splitwise CSV missing 'Cost' or 'Amount' column."],
                "warnings": [],
                "total_count": 0
            }

        extracted = []
        for _, row in df.iterrows():
            # Skip settlement payment lines in Splitwise if desired or treat as transfers
            desc = str(row[desc_col]).strip() if desc_col and pd.notnull(row[desc_col]) else "Splitwise Expense"
            if "settlement" in desc.lower() or "paid back" in desc.lower():
                continue

            raw_cost = row[cost_col]
            try:
                cost = float(re.sub(r"[^\d.]", "", str(raw_cost)))
                if cost <= 0: continue
            except Exception:
                continue

            dt = str(row[date_col]) if date_col and pd.notnull(row[date_col]) else datetime.date.today().isoformat()
            cat = str(row[cat_col]).title() if cat_col and pd.notnull(row[cat_col]) else "Shared Group Expense"

            extracted.append({
                "date": dt,
                "category": cat,
                "amount": round(cost, 2),
                "description": f"Splitwise: {desc}"
            })

        if not extracted:
            return {
                "success": False,
                "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
                "errors": ["No valid expense rows extracted from Splitwise file."],
                "warnings": [],
                "total_count": 0
            }

        return validate_and_clean_expenses_df(pd.DataFrame(extracted))

    except Exception as e:
        return {
            "success": False,
            "data": pd.DataFrame(columns=["date", "category", "amount", "description"]),
            "errors": [f"Splitwise parsing error: {str(e)}"],
            "warnings": [],
            "total_count": 0
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

# --- 5. GURU FINANCIAL ADVICE ENGINE & INDIAN TAX OPTIMIZER ---

def calculate_indian_income_tax(
    annual_income: float,
    deductions_80c: float = 150000.0,
    deductions_80d: float = 25000.0,
    nps_80ccd: float = 50000.0,
    hra_or_home_loan: float = 0.0
) -> dict:
    """
    Calculate Indian Income Tax under New Tax Regime (FY 2024-25 / 2025-26) vs Old Tax Regime.
    Provides tax-saving strategies (Section 80C, 80D, 80CCD, ELSS, PPF).
    """
    # 1. New Tax Regime (Budget 2024-25 / 2025-26 slabs)
    # Standard deduction: ₹75,000 for salaried
    new_std_deduction = 75000.0
    taxable_new = max(0.0, annual_income - new_std_deduction)
    
    # Slabs for New Tax Regime:
    # 0 - 3L: Nil
    # 3L - 7L: 5%
    # 7L - 10L: 10%
    # 10L - 12L: 15%
    # 12L - 15L: 20%
    # > 15L: 30%
    tax_new = 0.0
    if taxable_new <= 700000.0:
        tax_new = 0.0  # Section 87A full tax rebate up to 7 Lakh taxable income
    else:
        if taxable_new > 300000:
            tax_new += min(400000.0, taxable_new - 300000) * 0.05
        if taxable_new > 700000:
            tax_new += min(300000.0, taxable_new - 700000) * 0.10
        if taxable_new > 1000000:
            tax_new += min(200000.0, taxable_new - 1000000) * 0.15
        if taxable_new > 1200000:
            tax_new += min(300000.0, taxable_new - 1200000) * 0.20
        if taxable_new > 1500000:
            tax_new += (taxable_new - 1500000) * 0.30

    cess_new = tax_new * 0.04
    total_tax_new = tax_new + cess_new

    # 2. Old Tax Regime
    # Standard deduction: ₹50,000
    # Slabs: 0-2.5L: Nil, 2.5L-5L: 5%, 5L-10L: 20%, >10L: 30%
    old_std_deduction = 50000.0
    total_old_deductions = old_std_deduction + min(150000.0, deductions_80c) + min(100000.0, deductions_80d) + min(50000.0, nps_80ccd) + hra_or_home_loan
    taxable_old = max(0.0, annual_income - total_old_deductions)

    tax_old = 0.0
    if taxable_old <= 500000.0:
        tax_old = 0.0  # Section 87A rebate for Old Regime
    else:
        if taxable_old > 250000:
            tax_old += min(250000.0, taxable_old - 250000) * 0.05
        if taxable_old > 500000:
            tax_old += min(500000.0, taxable_old - 500000) * 0.20
        if taxable_old > 1000000:
            tax_old += (taxable_old - 1000000) * 0.30

    cess_old = tax_old * 0.04
    total_tax_old = tax_old + cess_old

    # Recommendation
    diff = abs(total_tax_new - total_tax_old)
    if total_tax_new < total_tax_old:
        recommended_regime = "New Tax Regime"
        savings_regime = total_tax_old - total_tax_new
        regime_rationale = f"The New Tax Regime saves you ₹{savings_regime:,.2f} in tax with simplified lower slabs and a ₹75,000 standard deduction."
    else:
        recommended_regime = "Old Tax Regime"
        savings_regime = total_tax_new - total_tax_old
        regime_rationale = f"The Old Tax Regime saves you ₹{savings_regime:,.2f} due to high itemized deductions (80C, 80D, NPS, HRA)."

    # Actionable tax saving tips
    tips = [
        f"**Section 80C (Max ₹1.5L)**: Utilize ELSS Mutual Funds (3-year lock-in with equity growth), PPF (7.1% tax-free), or EPF.",
        f"**Section 80D (Health Insurance)**: Claim up to ₹25,000 for self/family and ₹50,000 for senior citizen parents.",
        f"**Section 80CCD(1B) (NPS)**: Exclusive additional deduction up to ₹50,000 above the 80C limit for retirement compounding.",
        f"**Tax Rebate U/S 87A**: Zero tax liability under New Regime if taxable income is up to ₹7,00,000 (Gross income ₹7.75 Lakhs with standard deduction)."
    ]

    return {
        "annual_income": annual_income,
        "new_regime": {
            "standard_deduction": new_std_deduction,
            "taxable_income": taxable_new,
            "tax_payable": round(total_tax_new, 2),
            "effective_tax_rate": round(total_tax_new / annual_income * 100, 2) if annual_income > 0 else 0.0
        },
        "old_regime": {
            "total_deductions": total_old_deductions,
            "taxable_income": taxable_old,
            "tax_payable": round(total_tax_old, 2),
            "effective_tax_rate": round(total_tax_old / annual_income * 100, 2) if annual_income > 0 else 0.0
        },
        "recommended_regime": recommended_regime,
        "tax_difference": round(diff, 2),
        "regime_rationale": regime_rationale,
        "tax_saving_tips": tips
    }

def get_guru_recommendations(df: pd.DataFrame, monthly_income: float = 100000.0) -> dict:
    """
    Generate tailored financial guru advice based on user spending & income.
    Includes Buffett, Kiyosaki, Ramsey, Sethi, Housel, Graham & Indian Expert strategies.
    """
    if df.empty:
        total_spend = 0.0
        cat_summary = {}
    else:
        total_spend = df["amount"].sum()
        cat_summary = df.groupby("category")["amount"].sum().to_dict()

    savings_rate = max(0.0, (monthly_income - total_spend) / monthly_income * 100.0) if monthly_income > 0 else 0.0
    annual_income = monthly_income * 12.0
    emergency_target = total_spend * 6.0 if total_spend > 0 else monthly_income * 3.0
    
    # 1. Warren Buffett Insights (Value & Compounding)
    buffett = [
        "**Rule No. 1: Never lose money. Rule No. 2: Never forget rule No. 1.**",
        f"Your current savings rate is **{savings_rate:.1f}%**. Buffett recommends saving at least **20-30%** before any discretionary spending.",
        "**Do not save what is left after spending, but spend what is left after saving.** Automate index SIPs on salary day.",
        "Invest consistently in low-cost index funds (Nifty 50 / S&P 500) rather than speculative short-term trading."
    ]

    # 2. Robert Kiyosaki Insights (Rich Dad Poor Dad & Cashflow)
    kiyosaki = [
        "**Assets vs. Liabilities**: An asset puts money in your pocket; a liability takes money out of your pocket.",
        "**Pay Yourself First**: Allocate 15-20% of your paycheck directly into income-generating assets (Dividend equities, Mutual Funds, Real Estate) before paying bills.",
        f"Your monthly outflow is **₹{total_spend:,.2f}**. Focus on building passive cash flow to exceed this number for true financial freedom.",
        "Don't work for money — make your money work relentlessly for you through compounding assets."
    ]

    # 3. Dave Ramsey Insights (Baby Steps & Debt Free)
    ramsey = [
        "**Baby Step 1**: Build a $1,000 / ₹50,000 starter emergency fund immediately.",
        "**Baby Step 2**: Pay off all consumer debts (credit cards, personal loans) using the **Debt Snowball** method (smallest balance first).",
        f"**Baby Step 3**: Build a full **3 to 6 months emergency reserve** (Target: **₹{emergency_target:,.2f}** based on your current expense run-rate).",
        "**Baby Step 4**: Invest 15% of household income into tax-advantaged retirement & mutual funds."
    ]

    # 4. Ramit Sethi Insights (Conscious Spending Plan)
    fixed_costs = sum(v for k, v in cat_summary.items() if any(c in k.lower() for c in ["rent", "housing", "utility", "bill", "grocery", "transport"]))
    guilt_free = sum(v for k, v in cat_summary.items() if any(c in k.lower() for c in ["dining", "entertainment", "shopping", "out"]))
    
    sethi = [
        "**Ramit Sethi's Conscious Spending Plan**:",
        f"- **Fixed Costs (Target: 50-60%)**: Currently ₹{fixed_costs:,.2f} ({ (fixed_costs/monthly_income*100) if monthly_income else 0:.1f}%)",
        f"- **Investments (Target: 10%)**: Automated monthly equity investments (SIPs).",
        f"- **Savings Goals (Target: 5-10%)**: Emergency fund, travel, life milestones.",
        f"- **Guilt-Free Spending (Target: 20-35%)**: Currently ₹{guilt_free:,.2f} ({ (guilt_free/monthly_income*100) if monthly_income else 0:.1f}%). Spend extravagantly on the things you love, and cut costs mercilessly on the things you don't!"
    ]

    # 5. Morgan Housel Insights (Psychology of Money)
    housel = [
        "**Freedom is the highest dividend money pays.** Money's greatest intrinsic value is giving you complete autonomy over your time.",
        "**Wealth is what you don't see.** Wealth is the fancy cars not purchased, the luxury watches not worn, and impulse buys declined.",
        "Room for error (Margin of Safety) is the single most important part of any financial plan."
    ]

    # 6. Indian Wealth & Tax Strategist (Mashelkar / Indian Context)
    tax_analysis = calculate_indian_income_tax(annual_income)
    indian_expert = [
        f"**Indian Tax Optimization**: For your annual income of ₹{annual_income:,.2f}, the **{tax_analysis['recommended_regime']}** is optimal ({tax_analysis['regime_rationale']}).",
        "**Section 80C & ELSS**: Invest ₹1.5 Lakhs in ELSS mutual funds for dual benefits: Section 80C tax deduction + highest long-term wealth compounding (12-14% CAGR).",
        "**Sovereign Gold & PPF**: Allocate 5-10% in digital gold/SGBs and PPF (7.1% tax-free sovereign guarantee) for low-risk capital protection.",
        "**Automated Monthly SIP**: Set up auto-debit SIP in Nifty 50 / Nifty Next 50 index funds within 2 days of salary credit."
    ]

    return {
        "summary": {
            "total_spend": total_spend,
            "monthly_income": monthly_income,
            "annual_income": annual_income,
            "savings_rate": savings_rate,
            "emergency_target": emergency_target
        },
        "gurus": {
            "Warren Buffett": buffett,
            "Robert Kiyosaki": kiyosaki,
            "Ramit Sethi": sethi,
            "Dave Ramsey": ramsey,
            "Morgan Housel": housel,
            "Indian Wealth Strategist": indian_expert
        },
        "tax_analysis": tax_analysis
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
    story.append(Paragraph(" Executive Financial Advisory & Expense Report", title_style))
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
