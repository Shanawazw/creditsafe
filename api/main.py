"""
CreditSafe — FastAPI Backend
Endpoints for credit report parsing and eligibility checking.
Run: uvicorn api.main:app --reload --port 8000
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from parser.credit_parser import parse_credit_report
from parser.eligibility_engine import run_eligibility_check, UserIncomeInput

app = FastAPI(
    title="CreditSafe API",
    description="India's zero-inquiry credit eligibility checker",
    version="1.0.0"
)

# CORS — allows React frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict to your domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── REQUEST / RESPONSE SCHEMAS ───────────────────────────────────────────────

class IncomeRequest(BaseModel):
    gross_monthly_income:  float = Field(..., example=50000,  description="Monthly gross income in ₹")
    existing_emi_total:    float = Field(0,   example=12000,  description="Total of all existing EMIs per month")
    proposed_loan_amount:  float = Field(..., example=500000, description="Loan amount being considered (₹)")
    proposed_loan_tenure:  int   = Field(60,  example=60,     description="Preferred tenure in months")
    employment_type:       str   = Field("Salaried", example="Salaried",
                                         description="Salaried / Self-Employed / Govt / Gig")
    employment_months:     int   = Field(24,  example=36,     description="Months in current job / business")
    city_tier:             int   = Field(1,   example=1,      description="City tier: 1, 2, or 3")

class ManualCheckRequest(BaseModel):
    """For users who don't have a PDF handy — manual score entry."""
    credit_score:          int   = Field(..., example=720)
    enquiries_6m:          int   = Field(0,   example=1)
    written_off:           int   = Field(0,   example=0)
    suit_filed:            int   = Field(0,   example=0)
    worst_dpd_12m:         int   = Field(0,   example=0)
    credit_utilisation:    float = Field(0,   example=25.0)
    income:                IncomeRequest = None


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "CreditSafe API is live", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.post("/api/v1/parse-report", tags=["Credit Report"])
async def parse_report(file: UploadFile = File(...)):
    """
    Upload a CIBIL or Experian PDF credit report.
    Returns structured extracted data including score, accounts, enquiries.
    
    Supported: CIBIL (TransUnion), Experian India, Equifax India, CRIF High Mark.
    Zero data retention — report is processed in memory and discarded.
    """
    if file.content_type not in ["application/pdf", "application/octet-stream"]:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    if file.size and file.size > 10 * 1024 * 1024:   # 10MB limit
        raise HTTPException(status_code=400, detail="File size must be under 10MB")

    pdf_bytes = await file.read()

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file received")

    result = parse_credit_report(pdf_bytes)

    return {
        "success": True,
        "message": "Report parsed successfully" if result["parse_confidence"] > 0.5 else "Partial parse — some fields may be missing",
        "data": result
    }


@app.post("/api/v1/eligibility/from-report", tags=["Eligibility"])
async def eligibility_from_report(
    income: IncomeRequest,
    file: UploadFile = File(...)
):
    """
    Full pipeline: Upload credit report PDF + income details.
    Returns product-wise approval probability for all loan types.
    """
    pdf_bytes = await file.read()
    report_data = parse_credit_report(pdf_bytes)

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

    return {
        "success":     True,
        "report":      report_data,
        "eligibility": eligibility
    }


@app.post("/api/v1/eligibility/manual", tags=["Eligibility"])
async def eligibility_manual(request: ManualCheckRequest):
    """
    Quick eligibility check without PDF upload.
    User manually enters their credit score + income details.
    Useful for first-time check or users who don't have their report handy.
    """
    # Construct a minimal report_data from manual inputs
    report_data = {
        "credit_score":       request.credit_score,
        "enquiries_6m":       request.enquiries_6m,
        "written_off":        request.written_off,
        "suit_filed":         request.suit_filed,
        "worst_dpd_12m":      request.worst_dpd_12m,
        "credit_utilisation": request.credit_utilisation,
        "clean_payment_history": request.worst_dpd_12m == 0,
        "total_accounts":     0,
        "active_accounts":    0,
        "overdue_accounts":   0,
        "parse_confidence":   1.0,
        "warnings":           []
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
    """
    Standalone FOIR calculator — no credit report needed.
    """
    from parser.eligibility_engine import calculate_emi
    net_income = income.gross_monthly_income * 0.80
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
