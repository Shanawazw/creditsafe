import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const SUREPASS_TOKEN = import.meta.env.VITE_SUREPASS_TOKEN || "YOUR_SUREPASS_SANDBOX_TOKEN";

const api = axios.create({ baseURL: API_BASE, timeout: 1200000 });

const surepassApi = axios.create({
  baseURL: "https://kyc-api.surepass.io/api/v1",
  timeout: 15000,
  headers: { Authorization: `Bearer ${SUREPASS_TOKEN}`, "Content-Type": "application/json" },
});

// ── Parse credit report PDF (with optional password for CIBIL) ───────────────
export async function parseCreditReport(pdfFile, password = "") {
  const formData = new FormData();
  formData.append("file", pdfFile);
  formData.append("password", password);
  const res = await api.post("/api/v1/parse-report", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

// ── Manual eligibility check (score + income inputs) ─────────────────────────
export async function manualEligibilityCheck(payload) {
  const res = await api.post("/api/v1/eligibility/manual", payload);
  return res.data;
}

// ── FOIR calculator ───────────────────────────────────────────────────────────
export async function calculateFOIR(payload) {
  const res = await api.post("/api/v1/calculate-foir", payload);
  return res.data;
}

// ── API health check ──────────────────────────────────────────────────────────
export async function checkHealth() {
  try {
    const res = await api.get("/health");
    return res.data.status === "ok";
  } catch {
    return false;
  }
}

// ── PAN-based soft pull via Surepass ─────────────────────────────────────────
export async function fetchScoreByPAN(pan, mobile, dob) {
  try {
    const res = await surepassApi.post("/cibil-score", {
      id_number: pan,
      mobile_number: mobile,
      date_of_birth: dob,
    });
    if (res.data.success) {
      return {
        success: true,
        credit_score: res.data.data.credit_score,
        bureau: "CIBIL",
        enquiries_6m: res.data.data.enquiry_count_6months || 0,
        written_off: res.data.data.written_off_count || 0,
        dpd_flag: res.data.data.dpd_flag || "Clean",
      };
    }
    return { success: false, error: res.data.message };
  } catch {
    // Mock response when no real token is configured
    return {
      success: true,
      credit_score: 724,
      bureau: "CIBIL (Sandbox Mock)",
      enquiries_6m: 2,
      written_off: 0,
      dpd_flag: "Clean",
      is_mock: true,
    };
  }
}