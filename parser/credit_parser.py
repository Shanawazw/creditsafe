"""
CreditSafe — Credit Report PDF Parser
Supports: TransUnion CIBIL, Experian India
Author: CreditSafe India
"""

import re
import pdfplumber
from dataclasses import dataclass, field, asdict
from typing import Optional
from io import BytesIO


# ─── DATA MODELS ──────────────────────────────────────────────────────────────

@dataclass
class AccountDetail:
    lender:         str
    account_type:   str   # Home Loan / Personal Loan / Credit Card etc.
    status:         str   # Active / Closed / Written-off
    outstanding:    float
    credit_limit:   float
    dpd:            str   # Days Past Due — "000" is clean
    opened_date:    str
    last_payment:   str


@dataclass
class ParsedCreditReport:
    # ── Identity
    bureau:             str   = "Unknown"   # CIBIL / Experian / Equifax / CRIF
    report_date:        str   = ""
    customer_name:      str   = ""
    pan:                str   = ""
    dob:                str   = ""
    mobile:             str   = ""

    # ── Core Score
    credit_score:       int   = 0
    score_band:         str   = ""          # Excellent / Good / Fair / Poor / Very Poor

    # ── Enquiry Intelligence
    total_enquiries:    int   = 0
    enquiries_6m:       int   = 0
    enquiries_12m:      int   = 0
    last_enquiry_date:  str   = ""

    # ── Account Summary
    total_accounts:     int   = 0
    active_accounts:    int   = 0
    closed_accounts:    int   = 0
    overdue_accounts:   int   = 0
    written_off:        int   = 0
    suit_filed:         int   = 0
    oldest_account_age: str   = ""

    # ── Financial Exposure
    total_outstanding:  float = 0.0
    total_credit_limit: float = 0.0
    credit_utilisation: float = 0.0     # %

    # ── Payment History
    clean_payment_history: bool  = True
    worst_dpd_12m:         int   = 0    # 0=clean, 30, 60, 90+
    dpd_flag:              str   = "Clean"

    # ── Account Details
    accounts:           list  = field(default_factory=list)

    # ── Parser Metadata
    parse_confidence:   float = 0.0     # 0–1
    warnings:           list  = field(default_factory=list)


# ─── HELPER UTILITIES ─────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

def _find(pattern: str, text: str, group: int = 1, flags=re.IGNORECASE) -> str:
    m = re.search(pattern, text, flags)
    return _clean(m.group(group)) if m else ""

def _find_int(pattern: str, text: str, default: int = 0) -> int:
    val = _find(pattern, text)
    try:
        return int(re.sub(r'[^\d]', '', val))
    except:
        return default

def _find_float(pattern: str, text: str, default: float = 0.0) -> float:
    val = _find(pattern, text)
    try:
        return float(re.sub(r'[^\d.]', '', val))
    except:
        return default

def _score_band(score: int) -> str:
    if score >= 750: return "Excellent"
    if score >= 700: return "Good"
    if score >= 650: return "Fair"
    if score >= 550: return "Poor"
    return "Very Poor"

def _normalise_account_type(raw: str) -> str:
    raw = raw.upper()
    mapping = {
        "HOME": "Home Loan",
        "HOUSING": "Home Loan",
        "PERSONAL": "Personal Loan",
        "CONSUMER": "Personal Loan",
        "CREDIT CARD": "Credit Card",
        "CC": "Credit Card",
        "AUTO": "Car Loan",
        "VEHICLE": "Car Loan",
        "EDUCATION": "Education Loan",
        "BUSINESS": "Business Loan",
        "GOLD": "Gold Loan",
        "LAP": "Loan Against Property",
        "OVERDRAFT": "Overdraft",
        "KISAN": "Agricultural Loan",
    }
    for key, label in mapping.items():
        if key in raw:
            return label
    return raw.title()


# ─── BUREAU DETECTION ─────────────────────────────────────────────────────────

def _detect_bureau(text: str) -> str:
    text_up = text.upper()
    if "TRANSUNION CIBIL" in text_up or "CIBIL SCORE" in text_up:
        return "CIBIL"
    if "EXPERIAN" in text_up:
        return "Experian"
    if "EQUIFAX" in text_up:
        return "Equifax"
    if "CRIF" in text_up or "HIGHMARK" in text_up:
        return "CRIF High Mark"
    return "Unknown"


# ─── CIBIL PARSER ─────────────────────────────────────────────────────────────

def _parse_cibil(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    report.bureau = "CIBIL"

    # Score — CIBIL shows it prominently as 3-digit number 300-900
    score_patterns = [
        r'CIBIL\s*(?:Trans[Uu]nion\s*)?Score[:\s]+(\d{3})',
        r'Credit\s*Score[:\s]+(\d{3})',
        r'Your\s*Score[:\s]+(\d{3})',
        r'\b([7-9]\d{2})\b.*?(?:score|CIBIL)',
        r'(?:score|CIBIL)[^\d]+(\d{3})',
    ]
    for pat in score_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 900:
                report.credit_score = score
                break

    # Personal info
    report.customer_name = _find(r'Name[:\s]+([A-Z][A-Z\s]+?)(?:\n|Date|DOB|PAN)', text)
    report.pan            = _find(r'PAN[:\s#]*([A-Z]{5}\d{4}[A-Z])', text)
    report.dob            = _find(r'(?:Date of Birth|DOB)[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text)
    report.mobile         = _find(r'(?:Mobile|Phone)[:\s]+(\d{10})', text)
    report.report_date    = _find(r'(?:Report Date|Date of Issue|Generated on)[:\s]+(\d{1,2}[-/]\w+[-/]\d{2,4})', text)

    # Enquiries
    report.total_enquiries = _find_int(r'Total\s*(?:Number of)?\s*Enquir(?:y|ies)[:\s]+(\d+)', text)
    report.enquiries_6m    = _find_int(r'(?:Last\s*6\s*Months?|6\s*Months?\s*Enquir)[:\s]+(\d+)', text)
    report.enquiries_12m   = _find_int(r'(?:Last\s*12\s*Months?|12\s*Months?\s*Enquir)[:\s]+(\d+)', text)

    # Account counts
    report.total_accounts   = _find_int(r'Total\s*(?:Number of)?\s*Accounts?[:\s]+(\d+)', text)
    report.active_accounts  = _find_int(r'Active\s*Accounts?[:\s]+(\d+)', text)
    report.closed_accounts  = _find_int(r'Closed\s*Accounts?[:\s]+(\d+)', text)
    report.overdue_accounts = _find_int(r'Overdue\s*Accounts?[:\s]+(\d+)', text)
    report.written_off      = _find_int(r'Written[\s-]*off[:\s]+(\d+)', text)
    report.suit_filed       = _find_int(r'Suit[\s-]*[Ff]iled[:\s]+(\d+)', text)

    # Financial figures
    report.total_outstanding  = _find_float(r'Total\s*(?:Current\s*)?Balance[:\s]+(?:Rs\.?|₹|INR)?\s*([\d,]+)', text)
    report.total_credit_limit = _find_float(r'Total\s*(?:Credit\s*)?(?:Limit|Sanctioned)[:\s]+(?:Rs\.?|₹|INR)?\s*([\d,]+)', text)

    # DPD — check for any non-zero DPD in the text
    dpd_values = re.findall(r'\bDPD[:\s]*(\d+)', text, re.IGNORECASE)
    if dpd_values:
        max_dpd = max(int(d) for d in dpd_values if d.isdigit())
        report.worst_dpd_12m = max_dpd
        if max_dpd == 0:
            report.dpd_flag = "Clean"
        elif max_dpd <= 30:
            report.dpd_flag = "DPD 30 (Minor)"
            report.clean_payment_history = False
        elif max_dpd <= 60:
            report.dpd_flag = "DPD 60 (Moderate)"
            report.clean_payment_history = False
        else:
            report.dpd_flag = f"DPD {max_dpd}+ (Serious)"
            report.clean_payment_history = False

    # Parse individual accounts
    report.accounts = _parse_accounts_cibil(text)

    return report


def _parse_accounts_cibil(text: str) -> list:
    """
    Extract individual account blocks from CIBIL report.
    CIBIL formats vary — we use a block-based approach.
    """
    accounts = []

    # Look for account blocks — typically separated by lender names
    # Pattern: find sections with account type + lender + balance
    account_pattern = re.compile(
        r'((?:HDFC|ICICI|SBI|AXIS|KOTAK|YES|IDFC|BAJAJ|TATA|RELIANCE|MUTHOOT|'
        r'FULLERTON|MAHINDRA|HERO|INDUS|FEDERAL|KARNATAKA|CANARA|PNB|BOB|'
        r'UNION|CENTRAL|SYNDICATE|ALLAHABAD|OBC|DENA)[^\n]*?)\n'
        r'.*?(?:Account Type|Loan Type)[:\s]+([^\n]+)\n'
        r'.*?(?:Current Balance|Outstanding)[:\s]+(?:Rs\.?|₹)?\s*([\d,]+)',
        re.IGNORECASE | re.DOTALL
    )

    for m in account_pattern.finditer(text):
        try:
            accounts.append(AccountDetail(
                lender       = _clean(m.group(1))[:50],
                account_type = _normalise_account_type(_clean(m.group(2))),
                status       = "Active",
                outstanding  = float(re.sub(r'[^\d]', '', m.group(3)) or 0),
                credit_limit = 0.0,
                dpd          = "000",
                opened_date  = "",
                last_payment = ""
            ))
        except:
            continue

    return accounts


# ─── EXPERIAN PARSER ──────────────────────────────────────────────────────────

def _parse_experian(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    report.bureau = "Experian"

    # Experian score format slightly different
    score_patterns = [
        r'Experian\s*Credit\s*Score[:\s]+(\d{3})',
        r'Credit\s*Score[:\s]+(\d{3})',
        r'\b([3-9]\d{2})\b',
    ]
    for pat in score_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 900:
                report.credit_score = score
                break

    # Shared extraction logic
    report.customer_name    = _find(r'(?:Full Name|Name)[:\s]+([A-Z][A-Z\s]+?)(?:\n|DOB|PAN)', text)
    report.pan              = _find(r'PAN[:\s#]*([A-Z]{5}\d{4}[A-Z])', text)
    report.dob              = _find(r'(?:Date of Birth|DOB)[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text)
    report.enquiries_6m     = _find_int(r'(?:Enquiries in Last 6|6 Month Enquir)[^\d]+(\d+)', text)
    report.total_accounts   = _find_int(r'(?:No\. of|Total) Accounts[:\s]+(\d+)', text)
    report.active_accounts  = _find_int(r'Active[:\s]+(\d+)', text)
    report.written_off      = _find_int(r'Written[\s-]*[Oo]ff[:\s]+(\d+)', text)
    report.total_outstanding = _find_float(r'Total\s*Balance[:\s]+(?:Rs\.?|₹)?\s*([\d,]+)', text)

    return report


# ─── MASTER PARSER ────────────────────────────────────────────────────────────

def parse_credit_report(pdf_bytes: bytes) -> dict:
    """
    Main entry point.
    Accepts PDF as bytes, returns dict with parsed credit report fields.
    """
    report = ParsedCreditReport()
    full_text = ""

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages.append(page_text)
            full_text = "\n".join(pages)

        if not full_text.strip():
            report.warnings.append("PDF text extraction yielded no content — may be scanned/image-based PDF")
            report.parse_confidence = 0.0
            return _report_to_dict(report)

        # Detect bureau
        report.bureau = _detect_bureau(full_text)

        # Route to bureau-specific parser
        if report.bureau == "CIBIL":
            report = _parse_cibil(full_text, report)
        elif report.bureau == "Experian":
            report = _parse_experian(full_text, report)
        else:
            # Attempt generic extraction for Equifax / CRIF
            report = _parse_cibil(full_text, report)
            report.warnings.append(f"Using generic parser for bureau: {report.bureau}")

        # Post-processing
        report = _post_process(report)

    except Exception as e:
        report.warnings.append(f"Parser error: {str(e)}")
        report.parse_confidence = 0.1

    return _report_to_dict(report)


def _post_process(report: ParsedCreditReport) -> ParsedCreditReport:
    """Derived calculations and confidence scoring."""

    # Score band
    if report.credit_score > 0:
        report.score_band = _score_band(report.credit_score)

    # Credit utilisation
    if report.total_credit_limit > 0:
        report.credit_utilisation = round(
            (report.total_outstanding / report.total_credit_limit) * 100, 1
        )

    # Derive active accounts if not found
    if report.active_accounts == 0 and report.total_accounts > 0:
        report.active_accounts = report.total_accounts - report.closed_accounts

    # Confidence scoring — how many fields did we successfully extract?
    scored_fields = [
        report.credit_score > 0,
        bool(report.customer_name),
        bool(report.pan),
        report.total_accounts > 0,
        report.enquiries_6m >= 0,
    ]
    report.parse_confidence = round(sum(scored_fields) / len(scored_fields), 2)

    # Warnings
    if report.credit_score == 0:
        report.warnings.append("Credit score not found — report may be in an unsupported format")
    if report.written_off > 0:
        report.warnings.append(f"⚠️ {report.written_off} written-off account(s) detected — this is a serious lender concern")
    if report.suit_filed > 0:
        report.warnings.append(f"⚠️ {report.suit_filed} suit-filed account(s) detected — near-certain lender rejection")
    if report.enquiries_6m > 3:
        report.warnings.append(f"⚠️ {report.enquiries_6m} enquiries in last 6 months — lenders may flag as credit-hungry")
    if report.credit_utilisation > 30:
        report.warnings.append(f"⚠️ Credit utilisation at {report.credit_utilisation}% — optimal is below 30%")

    return report


def _report_to_dict(report: ParsedCreditReport) -> dict:
    d = asdict(report)
    d["accounts"] = [asdict(a) if hasattr(a, '__dataclass_fields__') else a for a in report.accounts]
    return d
