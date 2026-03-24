"""
CreditSafe — FastAPI Backend
Run: python -m uvicorn api.main:app --reload --port 8000
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from parser.credit_parser import parse_credit_report
from parser.eligibility_engine import run_eligibility_check, UserIncomeInput

app = FastAPI(
    title="CreditSafe API",
    description="India's zero-inquiry credit eligibility checker",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────

class IncomeRequest(BaseModel):
    gross_monthly_income:  float = Field(..., example=50000)
    existing_emi_total:    float = Field(0,   example=12000)
    proposed_loan_amount:  float = Field(..., example=500000)
    proposed_loan_tenure:  int   = Field(60,  example=60)
    employment_type:       str   = Field("Salaried")
    employment_months:     int   = Field(24)
    city_tier:             int   = Field(1)

class ManualCheckRequest(BaseModel):
    credit_score:          int   = Field(..., example=720)
    enquiries_6m:          int   = Field(0)
    written_off:           int   = Field(0)
    suit_filed:            int   = Field(0)
    worst_dpd_12m:         int   = Field(0)
    credit_utilisation:    float = Field(0)
    income:                IncomeRequest = None


# ─── HEALTH ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "CreditSafe API is live", "version": "1.0.0"}

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


# ─── PARSE REPORT ─────────────────────────────────────────────────────────────

@app.post("/api/v1/parse-report", tags=["Credit Report"])
async def parse_report(
    file: UploadFile = File(...),
    password: str = Form(default="")
):
    """
    Upload CIBIL or Experian PDF.
    Pass your DOB as password in DDMMYYYY format (e.g. 15031990).
    """
    if file.content_type not in ["application/pdf", "application/octet-stream"]:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file received")

    result = parse_credit_report(pdf_bytes, password=password)

    return {
        "success": True,
        "message": "Report parsed successfully" if result["parse_confidence"] > 0.5 else "Partial parse — some fields may be missing",
        "data": result
    }


# ─── DEBUG ENDPOINT — see raw extracted text ──────────────────────────────────

@app.post("/api/v1/debug/extract-text", tags=["Debug"])
async def debug_extract_text(
    file: UploadFile = File(...),
    password: str = Form(default="")
):
    """
    Debug endpoint — returns the raw text extracted from the PDF.
    Use this to see what text our parser is working with.
    """
    import pdfplumber
    import pikepdf
    from io import BytesIO

    pdf_bytes = await file.read()

    # Try to decrypt
    try:
        pdf_io = BytesIO(pdf_bytes)
        with pikepdf.open(pdf_io, password=password) as unlocked:
            out = BytesIO()
            unlocked.save(out)
            pdf_bytes = out.getvalue()
        decrypted = True
    except Exception as e:
        decrypted = False
        decrypt_error = str(e)

    # Extract text page by page
    pages_text = []
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages_text.append({
                    "page": i + 1,
                    "char_count": len(text),
                    "preview": text[:500],   # First 500 chars of each page
                    "full_text": text
                })
    except Exception as e:
        return {"success": False, "error": str(e)}

    total_text = "\n".join([p["full_text"] for p in pages_text])

    # Show what patterns matched
    import re
    score_found = re.search(r'(\d{3})', total_text[:2000])

    return {
        "success": True,
        "decrypted": decrypted,
        "total_pages": len(pages_text),
        "total_chars": len(total_text),
        "pages": pages_text,
        "first_500_chars": total_text[:500],
        "score_pattern_found": score_found.group(1) if score_found else "No 3-digit number found in first 2000 chars",
    }


# ─── ELIGIBILITY ──────────────────────────────────────────────────────────────

@app.post("/api/v1/eligibility/manual", tags=["Eligibility"])
async def eligibility_manual(request: ManualCheckRequest):
    report_data = {
        "credit_score":         request.credit_score,
        "enquiries_6m":         request.enquiries_6m,
        "written_off":          request.written_off,
        "suit_filed":           request.suit_filed,
        "worst_dpd_12m":        request.worst_dpd_12m,
        "credit_utilisation":   request.credit_utilisation,
        "clean_payment_history": request.worst_dpd_12m == 0,
        "total_accounts":       0,
        "active_accounts":      0,
        "overdue_accounts":     0,
        "parse_confidence":     1.0,
        "warnings":             []
    }

    income = request.income or IncomeRequest(
        gross_monthly_income=50000,
        proposed_loan_amount=500000,
        proposed_loan_tenure=60
    )
    income_input = UserIncomeInput(
        gross_monthly_income = income.gross_monthly_income,
        existing_emi_total   = income.existing_emi_total,
        proposed_loan_amount = income.proposed_loan_amount,
        proposed_loan_tenure = income.proposed_loan_tenure,
        employment_type      = income.employment_type,
        employment_months    = income.employment_months,
        city_tier            = income.city_tier
    )

    eligibility = run_eligibility_check(report_data, income_input)
    return {"success": True, "eligibility": eligibility}


@app.post("/api/v1/calculate-foir", tags=["Tools"])
async def calculate_foir(income: IncomeRequest):
    from parser.eligibility_engine import calculate_emi
    net_income   = income.gross_monthly_income * 0.80
    proposed_emi = calculate_emi(income.proposed_loan_amount, 12.0, income.proposed_loan_tenure)
    foir_current  = round((income.existing_emi_total / net_income) * 100, 1) if net_income > 0 else 0
    foir_proposed = round(((income.existing_emi_total + proposed_emi) / net_income) * 100, 1) if net_income > 0 else 0
    status = "Excellent" if foir_proposed < 30 else "Good" if foir_proposed < 40 else \
             "Acceptable" if foir_proposed < 50 else "High Risk" if foir_proposed < 60 else "Likely Rejected"
    return {
        "net_monthly_income":    net_income,
        "existing_emi":          income.existing_emi_total,
        "proposed_emi":          proposed_emi,
        "foir_without_proposed": foir_current,
        "foir_with_proposed":    foir_proposed,
        "foir_status":           status,
        "bank_threshold":        50,
        "nbfc_threshold":        60
    }