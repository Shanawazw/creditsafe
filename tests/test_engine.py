"""
CreditSafe — Test Suite
Tests the eligibility engine with real-world profile scenarios.
Run: python tests/test_engine.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser.eligibility_engine import run_eligibility_check, UserIncomeInput

# ─── TEST PROFILES ────────────────────────────────────────────────────────────

profiles = [
    {
        "name": "Priya — IT Professional, Excellent Profile",
        "report": {
            "credit_score": 780, "enquiries_6m": 1, "written_off": 0,
            "suit_filed": 0, "worst_dpd_12m": 0, "credit_utilisation": 22.0,
            "clean_payment_history": True, "total_accounts": 4,
            "active_accounts": 2, "overdue_accounts": 0, "warnings": []
        },
        "income": UserIncomeInput(
            gross_monthly_income=85000, existing_emi_total=15000,
            proposed_loan_amount=2500000, proposed_loan_tenure=240,
            employment_type="Salaried", employment_months=48, city_tier=1
        )
    },
    {
        "name": "Ravi — Mid-level, Borderline FOIR",
        "report": {
            "credit_score": 710, "enquiries_6m": 3, "written_off": 0,
            "suit_filed": 0, "worst_dpd_12m": 0, "credit_utilisation": 45.0,
            "clean_payment_history": True, "total_accounts": 5,
            "active_accounts": 4, "overdue_accounts": 0, "warnings": []
        },
        "income": UserIncomeInput(
            gross_monthly_income=45000, existing_emi_total=18000,
            proposed_loan_amount=500000, proposed_loan_tenure=60,
            employment_type="Salaried", employment_months=24, city_tier=2
        )
    },
    {
        "name": "Suresh — Self-Employed, Moderate Profile",
        "report": {
            "credit_score": 680, "enquiries_6m": 2, "written_off": 0,
            "suit_filed": 0, "worst_dpd_12m": 30, "credit_utilisation": 35.0,
            "clean_payment_history": False, "total_accounts": 3,
            "active_accounts": 2, "overdue_accounts": 1, "warnings": []
        },
        "income": UserIncomeInput(
            gross_monthly_income=60000, existing_emi_total=12000,
            proposed_loan_amount=300000, proposed_loan_tenure=36,
            employment_type="Self-Employed", employment_months=60, city_tier=2
        )
    },
    {
        "name": "Meena — Poor Score, Multiple Issues",
        "report": {
            "credit_score": 580, "enquiries_6m": 6, "written_off": 1,
            "suit_filed": 0, "worst_dpd_12m": 90, "credit_utilisation": 78.0,
            "clean_payment_history": False, "total_accounts": 6,
            "active_accounts": 5, "overdue_accounts": 2, "warnings": []
        },
        "income": UserIncomeInput(
            gross_monthly_income=22000, existing_emi_total=9000,
            proposed_loan_amount=200000, proposed_loan_tenure=24,
            employment_type="Salaried", employment_months=12, city_tier=3
        )
    },
    {
        "name": "Arjun — New to Credit (NTC)",
        "report": {
            "credit_score": 0, "enquiries_6m": 0, "written_off": 0,
            "suit_filed": 0, "worst_dpd_12m": 0, "credit_utilisation": 0,
            "clean_payment_history": True, "total_accounts": 0,
            "active_accounts": 0, "overdue_accounts": 0, "warnings": ["No credit history"]
        },
        "income": UserIncomeInput(
            gross_monthly_income=35000, existing_emi_total=0,
            proposed_loan_amount=200000, proposed_loan_tenure=24,
            employment_type="Salaried", employment_months=18, city_tier=2
        )
    },
]


# ─── TEST RUNNER ──────────────────────────────────────────────────────────────

def run_tests():
    print("\n" + "="*70)
    print("  CreditSafe — Eligibility Engine Test Suite")
    print("="*70)

    for profile in profiles:
        print(f"\n{'─'*70}")
        print(f"  👤  {profile['name']}")
        print(f"{'─'*70}")

        result = run_eligibility_check(profile["report"], profile["income"])

        print(f"  Credit Score   : {profile['report']['credit_score']} ({profile['report'].get('score_band','N/A')})")
        print(f"  Monthly Income : ₹{profile['income'].gross_monthly_income:,.0f}")
        print(f"  Existing EMI   : ₹{profile['income'].existing_emi_total:,.0f}")
        print(f"  FOIR (current) : {result['foir_current']:.1f}%")
        print(f"  FOIR (w/ loan) : {result['foir_with_proposed']:.1f}%")
        print(f"\n  Overall Verdict: {result['overall_verdict']} ({int(result['overall_probability']*100)}%)")
        print(f"\n  Product Breakdown:")

        products_sorted = sorted(result["products"], key=lambda x: x["probability"], reverse=True)
        for p in products_sorted:
            bar_len = int(p["probability_pct"] / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"    {p['icon']} {p['label']:<28} {bar} {p['probability_pct']:>3}%  {p['verdict']}")
            if p["hard_blocks"]:
                for block in p["hard_blocks"]:
                    print(f"       ⛔ {block}")

        print(f"\n  Advisory:")
        print(f"    📊 {result['credit_score_action']}")
        print(f"    💰 {result['foir_action']}")
        print(f"    🔍 {result['enquiry_action']}")
        print(f"\n  ✅ Top Recommendation: {result['top_recommendation']}")

        # Top tips from best product
        best = products_sorted[0]
        if best["improvement_tips"]:
            print(f"\n  💡 Tips for {best['label']}:")
            for tip in best["improvement_tips"][:2]:
                print(f"     → {tip}")

    print(f"\n{'='*70}")
    print("  All tests completed.")
    print("="*70 + "\n")


if __name__ == "__main__":
    run_tests()
