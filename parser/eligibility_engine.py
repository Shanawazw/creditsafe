"""
CreditSafe — Eligibility Calculator Engine
Computes approval probability per loan product
based on parsed credit report + user-declared income inputs.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# ─── LENDER THRESHOLD DATABASE ────────────────────────────────────────────────
# Sources: RBI guidelines, public bank product pages, NBFC published criteria
# These are the actual underwriting benchmarks we reverse-engineered in Phase 1 research

PRODUCT_THRESHOLDS = {
    "personal_loan_bank": {
        "label":         "Personal Loan (Bank)",
        "icon":          "💼",
        "min_score":     700,
        "ideal_score":   750,
        "min_income":    25000,
        "max_foir":      50,
        "ideal_foir":    40,
        "min_emp_months": 24,
        "score_weight":  0.40,
        "foir_weight":   0.30,
        "income_weight": 0.20,
        "history_weight":0.10,
        "max_enquiries_6m": 3,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "personal_loan_nbfc": {
        "label":         "Personal Loan (NBFC)",
        "icon":          "💼",
        "min_score":     650,
        "ideal_score":   700,
        "min_income":    15000,
        "max_foir":      60,
        "ideal_foir":    50,
        "min_emp_months": 12,
        "score_weight":  0.35,
        "foir_weight":   0.30,
        "income_weight": 0.25,
        "history_weight":0.10,
        "max_enquiries_6m": 5,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "home_loan": {
        "label":         "Home Loan",
        "icon":          "🏠",
        "min_score":     700,
        "ideal_score":   750,
        "min_income":    15000,
        "max_foir":      50,
        "ideal_foir":    40,
        "min_emp_months": 24,
        "score_weight":  0.35,
        "foir_weight":   0.30,
        "income_weight": 0.20,
        "history_weight":0.15,
        "max_enquiries_6m": 3,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "credit_card_premium": {
        "label":         "Credit Card (Premium)",
        "icon":          "💳",
        "min_score":     750,
        "ideal_score":   800,
        "min_income":    30000,
        "max_foir":      40,
        "ideal_foir":    30,
        "min_emp_months": 12,
        "score_weight":  0.50,
        "foir_weight":   0.20,
        "income_weight": 0.20,
        "history_weight":0.10,
        "max_enquiries_6m": 2,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "credit_card_standard": {
        "label":         "Credit Card (Standard)",
        "icon":          "💳",
        "min_score":     700,
        "ideal_score":   740,
        "min_income":    20000,
        "max_foir":      50,
        "ideal_foir":    40,
        "min_emp_months": 12,
        "score_weight":  0.45,
        "foir_weight":   0.25,
        "income_weight": 0.20,
        "history_weight":0.10,
        "max_enquiries_6m": 3,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "car_loan": {
        "label":         "Car Loan",
        "icon":          "🚗",
        "min_score":     700,
        "ideal_score":   740,
        "min_income":    20000,
        "max_foir":      50,
        "ideal_foir":    40,
        "min_emp_months": 6,
        "score_weight":  0.35,
        "foir_weight":   0.30,
        "income_weight": 0.25,
        "history_weight":0.10,
        "max_enquiries_6m": 4,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "education_loan": {
        "label":         "Education Loan",
        "icon":          "🎓",
        "min_score":     650,
        "ideal_score":   700,
        "min_income":    10000,
        "max_foir":      60,
        "ideal_foir":    50,
        "min_emp_months": 0,
        "score_weight":  0.30,
        "foir_weight":   0.25,
        "income_weight": 0.30,
        "history_weight":0.15,
        "max_enquiries_6m": 5,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
    "gold_loan": {
        "label":         "Gold Loan",
        "icon":          "🥇",
        "min_score":     0,
        "ideal_score":   600,
        "min_income":    0,
        "max_foir":      80,
        "ideal_foir":    60,
        "min_emp_months": 0,
        "score_weight":  0.10,
        "foir_weight":   0.20,
        "income_weight": 0.20,
        "history_weight":0.10,
        "max_enquiries_6m": 10,
        "written_off_ok": True,
        "suit_filed_ok":  False,
        "collateral_note": "Primarily secured against gold — easiest approval path",
    },
    "business_loan_bank": {
        "label":         "Business Loan (Bank)",
        "icon":          "🏢",
        "min_score":     700,
        "ideal_score":   750,
        "min_income":    50000,
        "max_foir":      50,
        "ideal_foir":    40,
        "min_emp_months": 36,
        "score_weight":  0.35,
        "foir_weight":   0.25,
        "income_weight": 0.25,
        "history_weight":0.15,
        "max_enquiries_6m": 3,
        "written_off_ok": False,
        "suit_filed_ok":  False,
    },
}


# ─── INPUT / OUTPUT MODELS ────────────────────────────────────────────────────

@dataclass
class UserIncomeInput:
    gross_monthly_income:   float   # ₹ — declared by user
    existing_emi_total:     float   # ₹ — all current EMIs per month
    proposed_loan_amount:   float   # ₹ — what they want to borrow
    proposed_loan_tenure:   int     # months
    employment_type:        str     # Salaried / Self-Employed / Govt / Gig
    employment_months:      int     # total months in current job / business
    city_tier:              int     # 1, 2, or 3


@dataclass
class ProductEligibility:
    product_key:        str
    label:              str
    icon:               str
    probability:        float       # 0.0 – 1.0
    probability_pct:    int         # 0 – 100
    verdict:            str         # Very Likely / Likely / Moderate / Low / Very Low
    verdict_color:      str         # green / yellow / orange / red
    foir:               float
    foir_status:        str
    score_status:       str
    income_status:      str
    hard_blocks:        list        # Absolute deal-breakers
    improvement_tips:   list        # Actionable SHAP-style explanations
    estimated_emi:      float       # ₹ per month for proposed loan


@dataclass
class EligibilityResult:
    # Input mirror
    credit_score:       int
    gross_monthly_income: float
    existing_emi_total: float
    proposed_loan_amount: float

    # Computed
    foir_current:       float       # FOIR without proposed loan
    foir_with_proposed: float       # FOIR including proposed EMI
    net_monthly_income: float       # After tax approximation

    # Overall
    overall_probability: float
    overall_verdict:    str
    products:           list        # List of ProductEligibility

    # Advisory
    top_recommendation: str
    credit_score_action: str
    foir_action:        str
    enquiry_action:     str

    # Flags
    has_hard_blocks:    bool


# ─── CORE CALCULATOR ──────────────────────────────────────────────────────────

def calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard EMI formula."""
    if tenure_months == 0 or annual_rate == 0:
        return principal / max(tenure_months, 1)
    r = annual_rate / 12 / 100
    return round(principal * r * (1 + r) ** tenure_months / ((1 + r) ** tenure_months - 1), 0)


def _score_factor(score: int, thresholds: dict) -> tuple[float, str]:
    """Returns (0–1 score contribution, status string)."""
    min_s  = thresholds["min_score"]
    ideal  = thresholds["ideal_score"]

    if min_s == 0:
        return 1.0, "No minimum requirement"
    if score < min_s:
        gap = min_s - score
        return 0.0, f"Below minimum by {gap} points"
    if score >= ideal:
        return 1.0, f"Strong ({score} ≥ {ideal} ideal)"
    # Linear between min and ideal
    factor = (score - min_s) / (ideal - min_s)
    return round(factor, 2), f"Meets minimum, approaching ideal"


def _foir_factor(foir: float, thresholds: dict) -> tuple[float, str]:
    """Returns (0–1 foir contribution, status string)."""
    max_f  = thresholds["max_foir"]
    ideal  = thresholds["ideal_foir"]

    if foir > max_f:
        return 0.0, f"FOIR {foir:.1f}% exceeds maximum {max_f}%"
    if foir <= ideal:
        return 1.0, f"Excellent FOIR ({foir:.1f}% ≤ {ideal}% ideal)"
    # Linear between ideal and max
    factor = 1 - (foir - ideal) / (max_f - ideal)
    return round(max(factor, 0.1), 2), f"FOIR {foir:.1f}% — acceptable but elevated"


def _income_factor(income: float, thresholds: dict) -> tuple[float, str]:
    min_i = thresholds["min_income"]
    if income < min_i:
        return 0.0, f"Income ₹{income:,.0f} below minimum ₹{min_i:,.0f}"
    if income >= min_i * 3:
        return 1.0, f"Strong income ₹{income:,.0f}/month"
    factor = min(income / (min_i * 3), 1.0)
    return round(factor, 2), f"Meets minimum income requirement"


def _enquiry_factor(enquiries_6m: int, thresholds: dict) -> float:
    max_e = thresholds["max_enquiries_6m"]
    if enquiries_6m == 0:
        return 1.0
    if enquiries_6m > max_e:
        return max(0.0, 1 - (enquiries_6m - max_e) * 0.15)
    return 1.0 - (enquiries_6m / max_e) * 0.1


def _history_factor(report_data: dict) -> float:
    factor = 1.0
    if report_data.get("written_off", 0) > 0:
        factor = 0.0
    elif report_data.get("worst_dpd_12m", 0) >= 90:
        factor = 0.1
    elif report_data.get("worst_dpd_12m", 0) >= 60:
        factor = 0.3
    elif report_data.get("worst_dpd_12m", 0) >= 30:
        factor = 0.6
    return factor


def _verdict(prob: float) -> tuple[str, str]:
    if prob >= 0.80: return "Very Likely",  "green"
    if prob >= 0.65: return "Likely",        "teal"
    if prob >= 0.45: return "Moderate",      "amber"
    if prob >= 0.25: return "Low",           "orange"
    return "Very Low", "red"


def _improvement_tips(
    product_key: str, score: int, foir: float, income: float,
    enquiries_6m: int, thresholds: dict, report_data: dict
) -> list:
    tips = []
    min_s = thresholds["min_score"]
    ideal_s = thresholds["ideal_score"]
    max_f = thresholds["max_foir"]

    if score < min_s:
        tips.append(f"Your score {score} is {min_s - score} points below the minimum. Pay all EMIs on time for 3–4 months to see improvement.")
    elif score < ideal_s:
        tips.append(f"Raising your score from {score} to {ideal_s}+ could improve your probability by ~15%. Reduce credit card utilisation below 30%.")

    if foir > max_f:
        tips.append(f"Your FOIR of {foir:.1f}% exceeds the {max_f}% maximum. Prepaying ₹{(foir - max_f) * income / 100:,.0f} of existing EMI obligations would bring you within range.")
    elif foir > thresholds["ideal_foir"]:
        tips.append(f"Reducing FOIR from {foir:.1f}% to below {thresholds['ideal_foir']}% would move you to the best-rate tier.")

    if enquiries_6m > thresholds["max_enquiries_6m"]:
        tips.append(f"You have {enquiries_6m} enquiries in 6 months — wait 3–4 months before applying to let this settle.")

    if report_data.get("credit_utilisation", 0) > 30:
        util = report_data["credit_utilisation"]
        tips.append(f"Credit card utilisation at {util}% — paying down to below 30% can add 20–30 score points within 30 days.")

    if not tips:
        tips.append("Your profile is strong for this product. Apply with confidence.")

    return tips


def run_eligibility_check(report_data: dict, income_input: UserIncomeInput) -> dict:
    """
    Master function — takes parsed credit report dict + user income inputs.
    Returns full eligibility result across all products.
    """

    score          = report_data.get("credit_score", 0)
    written_off    = report_data.get("written_off", 0)
    suit_filed     = report_data.get("suit_filed", 0)
    enquiries_6m   = report_data.get("enquiries_6m", 0)
    gross_income   = income_input.gross_monthly_income
    existing_emi   = income_input.existing_emi_total
    emp_months     = income_input.employment_months

    # Net monthly income approximation (after 20% tax deduction for salaried)
    tax_factor = 0.80 if income_input.employment_type == "Salaried" else 0.85
    net_income = gross_income * tax_factor

    # FOIR — current (before proposed loan)
    foir_current = round((existing_emi / net_income) * 100, 1) if net_income > 0 else 0.0

    # Proposed EMI at ~12% for computation (adjusted per product)
    proposed_emi_approx = calculate_emi(
        income_input.proposed_loan_amount, 12.0, income_input.proposed_loan_tenure
    )
    foir_with_proposed = round(((existing_emi + proposed_emi_approx) / net_income) * 100, 1) if net_income > 0 else 0.0

    product_results = []
    probabilities   = []

    for key, thresholds in PRODUCT_THRESHOLDS.items():
        hard_blocks = []

        # Hard block checks — absolute rejections
        if not thresholds["written_off_ok"] and written_off > 0:
            hard_blocks.append(f"Written-off account detected — near-certain rejection")
        if not thresholds["suit_filed_ok"] and suit_filed > 0:
            hard_blocks.append(f"Suit-filed account — automatic rejection at most lenders")
        if score > 0 and score < thresholds["min_score"]:
            hard_blocks.append(f"Credit score {score} below minimum {thresholds['min_score']}")
        if gross_income < thresholds["min_income"] and thresholds["min_income"] > 0:
            hard_blocks.append(f"Income ₹{gross_income:,.0f} below minimum ₹{thresholds['min_income']:,.0f}")
        if emp_months < thresholds["min_emp_months"] and thresholds["min_emp_months"] > 0:
            hard_blocks.append(f"Employment {emp_months}M below minimum {thresholds['min_emp_months']}M")

        # If any hard block → probability is capped at 5%
        if hard_blocks:
            probability = 0.05
        else:
            # Weighted factor scoring
            s_factor, s_status = _score_factor(score, thresholds)
            f_factor, f_status = _foir_factor(foir_with_proposed, thresholds)
            i_factor, i_status = _income_factor(gross_income, thresholds)
            e_factor           = _enquiry_factor(enquiries_6m, thresholds)
            h_factor           = _history_factor(report_data)

            probability = (
                s_factor * thresholds["score_weight"]  +
                f_factor * thresholds["foir_weight"]   +
                i_factor * thresholds["income_weight"] +
                h_factor * thresholds["history_weight"]
            ) * e_factor

            probability = round(min(max(probability, 0.0), 1.0), 2)

            # Strings for display
            s_status = s_status
            f_status = f_status
            i_status = i_status

        verdict, color = _verdict(probability)
        product_emi    = calculate_emi(
            income_input.proposed_loan_amount,
            11.5 if "home" in key else 14.0 if "personal" in key else 12.0,
            income_input.proposed_loan_tenure
        )
        tips = _improvement_tips(key, score, foir_with_proposed, net_income, enquiries_6m, thresholds, report_data)

        # Regenerate status strings for display
        _, s_status = _score_factor(score, thresholds)
        _, f_status = _foir_factor(foir_with_proposed, thresholds)
        _, i_status = _income_factor(gross_income, thresholds)

        product_results.append(asdict(ProductEligibility(
            product_key      = key,
            label            = thresholds["label"],
            icon             = thresholds["icon"],
            probability      = probability,
            probability_pct  = int(probability * 100),
            verdict          = verdict,
            verdict_color    = color,
            foir             = foir_with_proposed,
            foir_status      = f_status,
            score_status     = s_status,
            income_status    = i_status,
            hard_blocks      = hard_blocks,
            improvement_tips = tips,
            estimated_emi    = product_emi
        )))
        probabilities.append(probability)

    # Overall probability = weighted average of top 3 products
    top3 = sorted(probabilities, reverse=True)[:3]
    overall = round(sum(top3) / len(top3), 2)
    overall_verdict, _ = _verdict(overall)

    # Advisory messages
    score_action = ""
    if score < 700:
        score_action = f"Your score of {score} is limiting your options. 3 months of clean payments + reducing credit card utilisation below 30% could add 30–50 points."
    elif score < 750:
        score_action = f"You're in the 'Good' band. Reaching 750+ would unlock best-rate products from HDFC, ICICI, and Axis."
    else:
        score_action = f"Excellent score of {score}. Maintain it by keeping enquiries low and utilisation below 30%."

    foir_action = ""
    if foir_with_proposed > 50:
        foir_action = f"Your FOIR including the proposed loan would be {foir_with_proposed:.1f}%. Most banks want this below 50%. Consider a longer tenure or smaller loan amount."
    elif foir_with_proposed > 40:
        foir_action = f"FOIR of {foir_with_proposed:.1f}% is acceptable but elevated. NBFCs will be more flexible than banks here."
    else:
        foir_action = f"Healthy FOIR of {foir_with_proposed:.1f}%. You're well within most lenders' comfort zone."

    enquiry_action = ""
    if enquiries_6m > 3:
        enquiry_action = f"You have {enquiries_6m} enquiries in 6 months. Wait 2–3 months before applying — lenders penalise 'credit hunger'."
    elif enquiries_6m > 0:
        enquiry_action = f"{enquiries_6m} recent enquiry(ies). Keep this low. Use CreditSafe to pre-check before approaching any lender."
    else:
        enquiry_action = "No recent hard enquiries — your score is protected."

    best_product = max(product_results, key=lambda x: x["probability"])
    top_rec = f"Based on your profile, your best immediate option is a {best_product['label']} with a {best_product['probability_pct']}% approval probability."

    result = EligibilityResult(
        credit_score          = score,
        gross_monthly_income  = gross_income,
        existing_emi_total    = existing_emi,
        proposed_loan_amount  = income_input.proposed_loan_amount,
        foir_current          = foir_current,
        foir_with_proposed    = foir_with_proposed,
        net_monthly_income    = net_income,
        overall_probability   = overall,
        overall_verdict       = overall_verdict,
        products              = product_results,
        top_recommendation    = top_rec,
        credit_score_action   = score_action,
        foir_action           = foir_action,
        enquiry_action        = enquiry_action,
        has_hard_blocks       = any(p["hard_blocks"] for p in product_results)
    )

    return asdict(result)
