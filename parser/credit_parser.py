"""
CreditSafe — Credit Report PDF Parser
Supports: TransUnion CIBIL, Experian India, Equifax India, CRIF High Mark
Author: CreditSafe India
"""

import re
import pdfplumber
import pikepdf
from dataclasses import dataclass, field, asdict
from io import BytesIO


# ─── DATA MODELS ──────────────────────────────────────────────────────────────

@dataclass
class AccountDetail:
    lender:         str
    account_type:   str
    status:         str
    outstanding:    float
    credit_limit:   float
    dpd:            str
    opened_date:    str
    last_payment:   str


@dataclass
class ParsedCreditReport:
    bureau:                str   = "Unknown"
    report_date:           str   = ""
    customer_name:         str   = ""
    pan:                   str   = ""
    dob:                   str   = ""
    mobile:                str   = ""
    credit_score:          int   = 0
    score_band:            str   = ""
    total_enquiries:       int   = 0
    enquiries_6m:          int   = 0
    enquiries_12m:         int   = 0
    last_enquiry_date:     str   = ""
    total_accounts:        int   = 0
    active_accounts:       int   = 0
    closed_accounts:       int   = 0
    overdue_accounts:      int   = 0
    written_off:           int   = 0
    suit_filed:            int   = 0
    oldest_account_age:    str   = ""
    total_outstanding:     float = 0.0
    total_credit_limit:    float = 0.0
    credit_utilisation:    float = 0.0
    clean_payment_history: bool  = True
    worst_dpd_12m:         int   = 0
    dpd_flag:              str   = "Clean"
    accounts:              list  = field(default_factory=list)
    parse_confidence:      float = 0.0
    warnings:              list  = field(default_factory=list)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

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
        cleaned = re.sub(r'[^\d.]', '', val.replace(',', ''))
        return float(cleaned) if cleaned else default
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
        "HOME LOAN": "Home Loan", "HOUSING": "Home Loan",
        "PERSONAL LOAN": "Personal Loan", "PERSONAL": "Personal Loan",
        "CONSUMER LOAN": "Consumer Loan", "CONSUMER": "Consumer Loan",
        "CREDIT CARD": "Credit Card", "CREDIT CARDS": "Credit Card",
        "AUTO LOAN": "Car Loan", "AUTO": "Car Loan",
        "TWO WHEELER": "Two-Wheeler Loan", "TWO-WHEELER": "Two-Wheeler Loan",
        "EDUCATION": "Education Loan", "BUSINESS": "Business Loan",
        "GOLD": "Gold Loan", "LAP": "Loan Against Property",
        "OVERDRAFT": "Overdraft", "USED CAR": "Used Car Loan",
        "OTHER": "Other Loan",
    }
    for key, label in mapping.items():
        if key in raw:
            return label
    return raw.title()

def _parse_dpd_history(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    """Extract worst DPD across all accounts from payment history tables."""
    # Find all numeric DPD values (exclude 000 patterns and * placeholders)
    dpd_values = []

    # Pattern: standalone numbers in DPD rows (not dates like "02-26")
    dpd_nums = re.findall(r'\b([1-9]\d{1,2})\b', text)
    for d in dpd_nums:
        val = int(d)
        if 1 <= val <= 900:
            dpd_values.append(val)

    if dpd_values:
        max_dpd = max(dpd_values)
        report.worst_dpd_12m = max_dpd
        if max_dpd <= 30:
            report.dpd_flag = "DPD 30 (Minor)"
            report.clean_payment_history = False
        elif max_dpd <= 60:
            report.dpd_flag = "DPD 60 (Moderate)"
            report.clean_payment_history = False
        elif max_dpd <= 90:
            report.dpd_flag = "DPD 90 (Serious)"
            report.clean_payment_history = False
        else:
            report.dpd_flag = f"DPD {max_dpd}+ (Critical)"
            report.clean_payment_history = False

    return report


# ─── BUREAU DETECTION ─────────────────────────────────────────────────────────

def _detect_bureau(text: str) -> str:
    """Detect which bureau the report is from based on distinctive markers."""
    t = text[:2000].upper()  # Only check first 2000 chars for speed

    if "EXPERIAN CREDIT REPORT" in t or "EXPERIAN REPORT NUMBER" in t or "ERN)" in t:
        return "Experian"
    if "EQUIFAX CREDIT REPORT" in t or "EQUIFAX RISK SCORE" in t or "EQUIFAX SCORE" in t:
        return "Equifax"
    if "CRIF CREDIT SCORE" in t or "CONSUMER CREDIT™ REPORT" in t or \
       "CRIF HIGH MARK" in t or "PERFORM CONSUMER" in t or "CHM REF" in t:
        return "CRIF"
    if "TRANSUNION CIBIL" in t or "CIBIL SCORE" in t or \
       "CREDIT HEALTH REPORT" in t or "POWERED BY" in t or \
       "ENQUIRY CONTROL NUMBER" in t or "ECN)" in t:
        return "CIBIL"

    return "CIBIL"  # Default for Indian reports


# ─── CIBIL PARSER ─────────────────────────────────────────────────────────────
# Format: "Powered by\n742\nReport Date"  OR  standalone score on own line
# Password: DOB in DDMMYYYY format

def _parse_cibil(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    report.bureau = "CIBIL"

    # Score — multiple patterns to handle all CIBIL formats
    score_patterns = [
        r'CIBIL\s*(?:Trans[Uu]nion\s*)?Score[:\s]+(\d{3})',
        r'Credit\s*Score[:\s]+(\d{3})',
        r'Your\s*Score[:\s]+(\d{3})',
        r'Powered\s*by\s*\n(\d{3})\n',
        r'Powered\s*by[^\n]*\n[^\n]*\n(\d{3})',
        r'Health\s*Report\s*\n+(\d{3})\n',
        r'\n(\d{3})\nReport\s*Date',
        r'(?:score|CIBIL)[^\d]{0,30}(\d{3})',
    ]
    for pat in score_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 900:
                report.credit_score = score
                break

    # Fallback — standalone 3-digit number on its own line
    if report.credit_score == 0:
        for s in re.findall(r'(?:^|\n)(\d{3})(?:\n|$)', text):
            val = int(s)
            if 300 <= val <= 900:
                report.credit_score = val
                break

    # Personal info
    for pat in [r'Hey\s+([A-Za-z][A-Za-z\s]{2,40}?),',
                r'Dear\s+([A-Za-z][A-Za-z\s]{2,40}?),',
                r'Name[:\s]+([A-Z][A-Za-z\s]+?)(?:\n|Date|DOB|PAN)']:
        name = _find(pat, text)
        if name and len(name) > 2:
            report.customer_name = name
            break

    report.pan         = _find(r'PAN[:\s#]*([A-Z]{5}\d{4}[A-Z])', text)
    report.dob         = _find(r'(?:Date of Birth|DOB)[:\s]+(\d{1,2}[-/\s]\w+[-/\s]\d{2,4})', text)
    report.mobile      = _find(r'(?:Mobile|Phone)[:\s]+(\d{10})', text)
    report.report_date = (
        _find(r'Report\s*Date\s*[:\s]+(\d{1,2}\s+\w{3,}\s+\d{4})', text) or
        _find(r'Report\s*Date\s*[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text)
    )

    # Enquiries
    report.total_enquiries = _find_int(r'Total\s*(?:Number of)?\s*Enquir(?:y|ies)[:\s]+(\d+)', text)
    report.enquiries_6m    = _find_int(r'(?:Last\s*6\s*Months?|6\s*Months?\s*Enquir|Enquir\w*\s*in\s*last\s*6)[:\s]+(\d+)', text)
    report.enquiries_12m   = _find_int(r'(?:Last\s*12\s*Months?|12\s*Months?\s*Enquir)[:\s]+(\d+)', text)

    # Account summary
    report.total_accounts   = _find_int(r'Total\s*(?:Number of)?\s*Accounts?[:\s]+(\d+)', text)
    report.active_accounts  = _find_int(r'Active\s*(?:Accounts?)?[:\s]+(\d+)', text)
    report.closed_accounts  = _find_int(r'Closed\s*(?:Accounts?)?[:\s]+(\d+)', text)
    report.overdue_accounts = _find_int(r'Overdue\s*(?:Accounts?)?[:\s]+(\d+)', text)
    report.written_off      = _find_int(r'Written[\s-]*[Oo]ff[:\s]+(\d+)', text)
    report.suit_filed       = _find_int(r'Suit[\s-]*[Ff]iled[:\s]+(\d+)', text)

    # Financials
    report.total_outstanding  = _find_float(
        r'Total\s*(?:Current\s*)?(?:Balance|Outstanding)[:\s]+(?:Rs\.?|₹|INR)?\s*([\d,]+)', text)
    report.total_credit_limit = _find_float(
        r'Total\s*(?:Credit\s*)?(?:Limit|Sanctioned)[:\s]+(?:Rs\.?|₹|INR)?\s*([\d,]+)', text)

    report = _parse_dpd_history(text, report)
    return report


# ─── EXPERIAN PARSER ──────────────────────────────────────────────────────────
# Format: Score is standalone number after "Score Factors" list
# e.g. "1. Recency...\n704\n2. Leverage..."
# Password: DOB in DDMMYYYY

def _parse_experian(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    report.bureau = "Experian"

    # Score — Experian puts it as a standalone number between numbered score factors
    # Pattern: between "Score Factors" section and numbered items
    score_patterns = [
        r'EXPERIAN\s*CREDIT\s*SCORE.*?Score\s*Factors.*?\n(\d{3})\n',  # Between factors
        r'Score\s*Factors\s*\n.*?\n(\d{3})\n',                          # After factor lines
        r'ranges\s*from\s*300\s*-\s*900\.\s*\n.*?\n(\d{3})\n',         # After "ranges from" text
        r'Delinquency\s*Status[^\n]*\n(\d{3})\n',                       # After last factor
        r'\n(\d{3})\nREPORT\s*SUMMARY',                                  # Just before summary
        r'Experian\s*Credit\s*Score[:\s]+(\d{3})',
        r'Credit\s*Score[:\s]+(\d{3})',
    ]
    for pat in score_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 900:
                report.credit_score = score
                break

    # Fallback — find standalone 3-digit number near "Score Factors" text
    if report.credit_score == 0:
        score_section = re.search(
            r'Score\s*Factors(.*?)REPORT\s*SUMMARY', text, re.IGNORECASE | re.DOTALL)
        if score_section:
            section_text = score_section.group(1)
            for s in re.findall(r'(?:^|\n)(\d{3})(?:\n|$)', section_text):
                val = int(s)
                if 300 <= val <= 900:
                    report.credit_score = val
                    break

    # Personal info
    # Name: "Name Syedabdulshanawaz W" (no colon, just space after "Name")
    report.customer_name = _find(r'^Name\s+([A-Za-z][A-Za-z\s]+?)$', text, flags=re.IGNORECASE | re.MULTILINE)
    if not report.customer_name:
        report.customer_name = _find(r'Name\s+([A-Za-z][A-Za-z\s]+?)(?:\n|Address|Date)', text)

    # PAN: "PAN BRMPS8203F" (no colon)
    report.pan    = _find(r'PAN\s+([A-Z]{5}\d{4}[A-Z])\b', text)
    if not report.pan:
        report.pan = _find(r'PAN[:\s]+([A-Z]{5}\d{4}[A-Z])', text)

    report.dob    = _find(r'Date\s*Of\s*Birth\s+(\d{2}-\d{2}-\d{4})', text)
    report.mobile = _find(r'Mobile\s*Phone\s+(\d{10})', text)

    # Report date: "Report Created:08-03-2026"
    report.report_date = _find(r'Report\s*Created[:\s]+(\d{2}-\d{2}-\d{4})', text)

    # Account summary from REPORT SUMMARY section
    report.total_accounts   = _find_int(r'Total\s*number\s*of\s*Accounts\s+(\d+)', text)
    report.active_accounts  = _find_int(r'Active\s*Accounts\s+(\d+)', text)
    report.closed_accounts  = _find_int(r'Closed\s*Accounts\s+(\d+)', text)

    # Financials: "Total Current Bal. amt 62,76,374"
    report.total_outstanding = _find_float(r'Total\s*Current\s*Bal\.\s*amt\s+([\d,]+)', text)
    if report.total_outstanding == 0:
        report.total_outstanding = _find_float(r'Total\s*Current\s*Bal[^\d]+([\d,]+)', text)

    # Written off / suit filed — Experian uses "SF/WD/WO/Settled amt"
    # Count write-offs from account details
    report.written_off = len(re.findall(r'Total\s*Write-off\s*Amt\s+[\d,]+', text, re.IGNORECASE))

    # Enquiries — "Last 180 days credit enquiries 0"
    report.enquiries_6m  = _find_int(r'Last\s*180\s*days\s*credit\s*enquiries\s+(\d+)', text)
    report.enquiries_12m = _find_int(r'Last\s*(?:365|12\s*months?)\s*(?:days\s*)?(?:credit\s*)?enquiries\s+(\d+)', text)
    report.total_enquiries = max(report.enquiries_6m, report.enquiries_12m)

    report = _parse_dpd_history(text, report)
    return report


# ─── EQUIFAX PARSER ───────────────────────────────────────────────────────────
# Format: "Equifax Risk Score 4.0 798"
# No password needed

def _parse_equifax(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    report.bureau = "Equifax"

    # Score — "Equifax Risk Score 4.0 798"
    score_patterns = [
        r'Equifax\s*Risk\s*Score\s*[\d.]+\s+(\d{3})',   # "Equifax Risk Score 4.0 798"
        r'Equifax\s*Score[^:]*:\s*(\d{3})',
        r'Score\s*Name\s*Score.*?(\d{3})',
        r'Risk\s*Score[^\d]+(\d{3})',
    ]
    for pat in score_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 900:
                report.credit_score = score
                break

    # Personal info
    # Name: "Consumer Name: SYED ABDUL ABDUL SHANAWAZ"
    report.customer_name = _find(r'Consumer\s*Name[:\s]+([A-Z][A-Z\s]+?)(?:\n|Personal)', text)

    # PAN: "PAN: BRMPS8203F"
    report.pan    = _find(r'PAN[:\s]+([A-Z]{5}\d{4}[A-Z])', text)
    report.dob    = _find(r'DOB[:\s]+(\d{2}-\d{2}-\d{4})', text)
    report.mobile = _find(r'Mobile\s*[:\s]+(\d{10})', text)

    # Report date — has "(cid:9)" artifact from PDF: "Date (cid:9) : 08-03-2026"
    report.report_date = _find(r'Date\s*(?:\(cid:\d+\)\s*)?[:\s]+(\d{2}-\d{2}-\d{4})', text)

    # Account summary
    report.total_accounts   = _find_int(r'Number\s*of\s*Accounts\s*[:\s]+(\d+)', text)
    report.active_accounts  = _find_int(r'Number\s*of\s*Open\s*Accounts\s*[:\s]+(\d+)', text)
    report.overdue_accounts = _find_int(r'Number\s*of\s*Past\s*Due\s*Accounts\s*[:\s]+(\d+)', text)
    report.written_off      = _find_int(r'Number\s*of\s*Write-off\s*Accounts\s*[:\s]+(\d+)', text)

    # Financials
    # "Total Balance Amount : Rs. 55,88,037"
    report.total_outstanding  = _find_float(r'Total\s*Balance\s*Amount\s*[:\s]+Rs\.\s*([\d,]+)', text)
    # "Total Credit Limit : Rs. 4,32,000"
    report.total_credit_limit = _find_float(r'Total\s*Credit\s*Limit\s*[:\s]+Rs\.\s*([\d,]+)', text)

    # Enquiries — "Total Inquiries : 1" from Recent Activity
    report.total_enquiries = _find_int(r'Total\s*Inquiries\s*[:\s]+(\d+)', text)

    report = _parse_dpd_history(text, report)
    return report


# ─── CRIF HIGH MARK PARSER ────────────────────────────────────────────────────
# Format: "PERFORM CONSUMER 2.2 300-900 736" in score table
# Password: first 4 letters of first name + last 4 digits of mobile
# e.g. Shanawaz + 6987 = SHAN6987

def _parse_crif(text: str, report: ParsedCreditReport) -> ParsedCreditReport:
    report.bureau = "CRIF"

    # Score — "PERFORM CONSUMER 2.2 300-900 736"
    # The score is the last number after the range "300-900"
    score_patterns = [
        r'300-900\s+(\d{3})',                                  # "300-900 736"
        r'PERFORM\s*CONSUMER\s*[\d.]+\s*300-900\s+(\d{3})',   # Full pattern
        r'CRIF\s*(?:Credit\s*)?Score[^\d]+(\d{3})',
        r'SCORE\s*DESCRIPTION\s*\n[^\n]+\n[^\n]+\n(\d{3})',   # After table headers
    ]
    for pat in score_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 900:
                report.credit_score = score
                break

    # Personal info
    # Name: "Name: Shanawaz Syedabdul" or "For SHANAWAZ SYEDABDUL"
    report.customer_name = _find(r'Name[:\s]+([A-Za-z][A-Za-z\s]+?)(?:\s*Phone|\s*ID|\n)', text)
    if not report.customer_name:
        report.customer_name = _find(r'For\s+([A-Z][A-Z\s]+?)(?:\s*CHM|\s*Ref|\n)', text)

    # PAN: "ID(s): BRMPS8203F [PAN]"
    report.pan    = _find(r'ID\(s\)[:\s]+([A-Z]{5}\d{4}[A-Z])\s*\[PAN\]', text)
    if not report.pan:
        report.pan = _find(r'PAN[:\s]+([A-Z]{5}\d{4}[A-Z])', text)

    report.mobile = _find(r'Phone\s*Numbers?[:\s]+(\d{10})', text)
    report.dob    = _find(r'(?:Date of Birth|DOB)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', text)

    # Report date: "Date of Issue: 08-03-2026"
    report.report_date = (
        _find(r'Date\s*of\s*Issue[:\s]+(\d{2}-\d{2}-\d{4})', text) or
        _find(r'Date\s*of\s*Request[:\s]+(\d{2}-\d{2}-\d{4})', text)
    )

    # Account summary from Primary Account Summary table
    # Row format: "57 10 3 7 50 0 ₹ 55,88,037.00..."
    # Columns:    Total Active Overdue Secured Unsecured Untagged Balance...
    account_row = re.search(
        r'(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+\d+\s+\d+\s+₹\s*([\d,]+)',
        text
    )
    if account_row:
        report.total_accounts   = int(account_row.group(1))
        report.active_accounts  = int(account_row.group(2))
        report.overdue_accounts = int(account_row.group(3))
        report.total_outstanding = float(account_row.group(4).replace(',', ''))

    # Also try explicit labels if table parsing fails
    if report.total_accounts == 0:
        report.total_accounts   = _find_int(r'Total\s*(?:Number of)?\s*Accounts?[:\s]+(\d+)', text)
        report.active_accounts  = _find_int(r'Active\s*(?:Accounts?)?[:\s]+(\d+)', text)
        report.overdue_accounts = _find_int(r'Overdue\s*(?:Accounts?)?[:\s]+(\d+)', text)

    # Written off / suit filed
    report.written_off = _find_int(r'Written[\s-]*[Oo]ff[:\s]+(\d+)', text)
    report.suit_filed  = _find_int(r'Suit[\s-]*[Ff]iled[:\s]+(\d+)', text)

    # Sanctioned / credit limit
    report.total_credit_limit = _find_float(
        r'Total\s*Sanctioned\s*(?:Amount)?[:\s]+(?:₹|Rs\.?)?\s*([\d,]+)', text)

    # Enquiries
    report.total_enquiries = _find_int(r'NUM-GRANTORS[^A-Z]*(\d+)', text)

    report = _parse_dpd_history(text, report)
    return report


# ─── MASTER PARSER ────────────────────────────────────────────────────────────

def parse_credit_report(pdf_bytes: bytes, password: str = "") -> dict:
    """
    Main entry point. Accepts PDF bytes + optional password.
    Password formats by bureau:
    - CIBIL:    DOB in DDMMYYYY (e.g. 15031990)
    - Experian: DOB in DDMMYYYY
    - Equifax:  No password needed
    - CRIF:     First 4 letters of first name + last 4 digits of mobile (e.g. SHAN6987)
    """
    report = ParsedCreditReport()
    full_text = ""

    try:
        # Step 1 — Decrypt if password protected
        try:
            pdf_io = BytesIO(pdf_bytes)
            with pikepdf.open(pdf_io, password=password) as unlocked:
                out = BytesIO()
                unlocked.save(out)
                pdf_bytes = out.getvalue()
        except pikepdf.PasswordError:
            report.warnings.append(
                "Incorrect PDF password. "
                "CIBIL/Experian: use DOB as DDMMYYYY (e.g. 15031990). "
                "CRIF: use first 4 letters of name + last 4 digits of mobile (e.g. SHAN6987). "
                "Equifax: no password needed."
            )
            report.parse_confidence = 0.0
            return _report_to_dict(report)
        except Exception:
            pass  # Not encrypted — continue normally

        # Step 2 — Extract text (cap at 20 pages for speed)
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                if i >= 20:
                    break
                page_text = page.extract_text() or ""
                pages.append(page_text)
            full_text = "\n".join(pages)

        if not full_text.strip():
            report.warnings.append("PDF text extraction yielded no content — may be scanned/image-based")
            report.parse_confidence = 0.0
            return _report_to_dict(report)

        # Step 3 — Detect bureau and route to correct parser
        report.bureau = _detect_bureau(full_text)

        if report.bureau == "Experian":
            report = _parse_experian(full_text, report)
        elif report.bureau == "Equifax":
            report = _parse_equifax(full_text, report)
        elif report.bureau == "CRIF":
            report = _parse_crif(full_text, report)
        else:
            report = _parse_cibil(full_text, report)

        # Step 4 — Post process and calculate confidence
        report = _post_process(report)

    except Exception as e:
        report.warnings.append(f"Parser error: {str(e)}")
        report.parse_confidence = 0.1

    return _report_to_dict(report)


# ─── POST PROCESSING ──────────────────────────────────────────────────────────

def _post_process(report: ParsedCreditReport) -> ParsedCreditReport:
    if report.credit_score > 0:
        report.score_band = _score_band(report.credit_score)

    if report.total_credit_limit > 0 and report.total_outstanding > 0:
        report.credit_utilisation = round(
            (report.total_outstanding / report.total_credit_limit) * 100, 1
        )

    if report.active_accounts == 0 and report.total_accounts > 0 and report.closed_accounts > 0:
        report.active_accounts = report.total_accounts - report.closed_accounts

    # Confidence scoring
    scored_fields = [
        report.credit_score > 0,
        bool(report.customer_name),
        bool(report.pan),
        report.total_accounts > 0,
        bool(report.report_date),
    ]
    report.parse_confidence = round(sum(scored_fields) / len(scored_fields), 2)

    # Warnings
    if report.credit_score == 0:
        report.warnings.append(
            f"Credit score not found in {report.bureau} report — "
            "check that you uploaded the correct PDF"
        )
    if report.written_off > 0:
        report.warnings.append(
            f"⚠️ {report.written_off} written-off account(s) detected — serious lender concern"
        )
    if report.suit_filed > 0:
        report.warnings.append(
            f"⚠️ {report.suit_filed} suit-filed account(s) — near-certain lender rejection"
        )
    if report.enquiries_6m > 3:
        report.warnings.append(
            f"⚠️ {report.enquiries_6m} enquiries in last 6 months — lenders may flag as credit-hungry"
        )
    if report.credit_utilisation > 30:
        report.warnings.append(
            f"⚠️ Credit utilisation at {report.credit_utilisation}% — optimal is below 30%"
        )

    return report


def _report_to_dict(report: ParsedCreditReport) -> dict:
    d = asdict(report)
    d["accounts"] = [
        asdict(a) if hasattr(a, '__dataclass_fields__') else a
        for a in report.accounts
    ]
    return d