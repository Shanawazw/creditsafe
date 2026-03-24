import { useState, useEffect, useRef } from "react";
import {
  parseCreditReport, manualEligibilityCheck,
  fetchScoreByPAN, checkHealth
} from "./services/api";

// ── Colour tokens ─────────────────────────────────────────────────────────────
const C = {
  bg:      "#07090f",
  surface: "#0d1117",
  card:    "#111827",
  border:  "#1f2937",
  teal:    "#14b8a6",
  tealD:   "#0f766e",
  amber:   "#f59e0b",
  red:     "#ef4444",
  green:   "#22c55e",
  text:    "#f1f5f9",
  muted:   "#64748b",
  sub:     "#94a3b8",
};

// ── Responsive hook ───────────────────────────────────────────────────────────
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 640);
  useEffect(() => {
    const fn = () => setIsMobile(window.innerWidth < 640);
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return isMobile;
}

// ── Tiny reusable components ──────────────────────────────────────────────────
const Pill = ({ text, color }) => (
  <span style={{
    background: `${color}18`, color, border: `1px solid ${color}40`,
    borderRadius: 20, padding: "3px 12px", fontSize: 11, fontWeight: 700,
    letterSpacing: 0.5, whiteSpace: "nowrap"
  }}>{text}</span>
);

const Bar = ({ pct, color }) => (
  <div style={{ background: "#1f2937", borderRadius: 6, height: 8, overflow: "hidden" }}>
    <div style={{
      width: `${pct}%`, height: "100%", borderRadius: 6,
      background: `linear-gradient(90deg, ${color}, ${color}cc)`,
      transition: "width 1.4s cubic-bezier(0.4,0,0.2,1)"
    }} />
  </div>
);

const Input = ({ label, value, onChange, type = "text", placeholder, prefix }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
    <label style={{ fontSize: 12, color: C.sub, fontWeight: 600, letterSpacing: 0.5 }}>{label}</label>
    <div style={{ position: "relative" }}>
      {prefix && <span style={{
        position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)",
        color: C.muted, fontSize: 14, fontWeight: 600
      }}>{prefix}</span>}
      <input
        type={type} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: "100%", background: "#111827", border: `1px solid ${C.border}`,
          borderRadius: 10, padding: prefix ? "12px 14px 12px 28px" : "12px 14px",
          color: C.text, fontSize: 14, outline: "none", boxSizing: "border-box",
          fontFamily: "inherit"
        }}
        onFocus={e => e.target.style.borderColor = C.teal}
        onBlur={e => e.target.style.borderColor = C.border}
      />
    </div>
  </div>
);

const Btn = ({ children, onClick, variant = "primary", disabled, loading, fullWidth }) => {
  const bg = variant === "primary"
    ? `linear-gradient(135deg, ${C.teal}, ${C.tealD})`
    : variant === "ghost" ? "transparent" : "#1f2937";
  return (
    <button onClick={onClick} disabled={disabled || loading} style={{
      background: disabled ? "#1f2937" : bg,
      color: disabled ? C.muted : "white",
      border: variant === "ghost" ? `1px solid ${C.border}` : "none",
      borderRadius: 12, padding: "14px 24px", fontWeight: 700, fontSize: 14,
      cursor: disabled ? "not-allowed" : "pointer", width: fullWidth ? "100%" : "auto",
      fontFamily: "inherit", letterSpacing: 0.3, transition: "all 0.2s",
      opacity: loading ? 0.7 : 1,
    }}>
      {loading ? "⏳  Processing..." : children}
    </button>
  );
};

// ── Bureau badge ──────────────────────────────────────────────────────────────
const BUREAU_META = {
  CIBIL:    { color: "#6366f1", label: "CIBIL", icon: "🏦" },
  Experian: { color: "#ec4899", label: "Experian", icon: "📊" },
  Equifax:  { color: "#f59e0b", label: "Equifax", icon: "📈" },
  CRIF:     { color: "#14b8a6", label: "CRIF High Mark", icon: "📋" },
};
const BureauBadge = ({ bureau }) => {
  const meta = BUREAU_META[bureau] || BUREAU_META["CIBIL"];
  return (
    <span style={{
      background: `${meta.color}18`, color: meta.color,
      border: `1px solid ${meta.color}40`, borderRadius: 20,
      padding: "4px 12px", fontSize: 11, fontWeight: 700, letterSpacing: 0.5
    }}>{meta.icon} {meta.label}</span>
  );
};

// ── Score Gauge ───────────────────────────────────────────────────────────────
const ScoreGauge = ({ score, onClick }) => {
  const pct   = score > 0 ? ((score - 300) / 600) * 100 : 0;
  const color = score >= 750 ? C.green : score >= 700 ? C.teal : score >= 650 ? C.amber : C.red;
  const band  = score >= 750 ? "Excellent" : score >= 700 ? "Good" : score >= 650 ? "Fair" : score > 0 ? "Poor" : "No Score";
  const angle = (pct / 100) * 180 - 90;
  return (
    <div style={{ textAlign: "center", cursor: onClick ? "pointer" : "default" }} onClick={onClick}>
      <svg width={200} height={112} viewBox="0 0 220 120">
        <defs>
          <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stopColor="#ef4444" />
            <stop offset="40%"  stopColor="#f59e0b" />
            <stop offset="100%" stopColor="#22c55e" />
          </linearGradient>
        </defs>
        <path d="M 25 105 A 85 85 0 0 1 195 105" fill="none" stroke="#1f2937" strokeWidth={18} strokeLinecap="round"/>
        <path d="M 25 105 A 85 85 0 0 1 195 105" fill="none" stroke="url(#gauge-grad)" strokeWidth={16}
          strokeLinecap="round" strokeDasharray={`${pct * 2.67} 267`}/>
        <g transform={`translate(110,105) rotate(${angle})`}>
          <line x1="0" y1="0" x2="0" y2="-65" stroke="white" strokeWidth={3} strokeLinecap="round"/>
          <circle cx="0" cy="0" r={6} fill="white"/>
        </g>
        <text x="110" y="96" textAnchor="middle" fill="white" fontSize={28} fontWeight={800}
          fontFamily="'DM Sans', sans-serif">{score > 0 ? score : "—"}</text>
      </svg>
      <div style={{ color, fontWeight: 800, fontSize: 13, letterSpacing: 2, textTransform: "uppercase" }}>{band}</div>
      <div style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>Range: 300 – 900</div>
      {onClick && <div style={{ fontSize: 11, color: C.teal, marginTop: 6, letterSpacing: 0.5 }}>
        Tap to understand your score →
      </div>}
    </div>
  );
};

// ── Score Explanation Modal ───────────────────────────────────────────────────
const SCORE_BANDS = [
  { min: 750, max: 900, label: "Excellent",  color: C.green,  desc: "You're in the top tier. Banks compete to offer you credit at the best rates. Approval is near-certain for most products." },
  { min: 700, max: 749, label: "Good",       color: C.teal,   desc: "Strong creditworthiness. You qualify for most loans. Rates are good but not the absolute best." },
  { min: 650, max: 699, label: "Fair",       color: C.amber,  desc: "Acceptable for some banks and most NBFCs. You may face higher interest rates and some rejections." },
  { min: 550, max: 649, label: "Poor",       color: "#f97316", desc: "Banks will likely reject. NBFCs may approve at significantly higher rates. Focus on improving before applying." },
  { min: 300, max: 549, label: "Very Poor",  color: C.red,    desc: "High risk in lenders' eyes. Avoid applying — each rejection adds a hard inquiry. Rebuild first." },
];

const SCORE_FACTORS = [
  { icon: "📅", label: "Payment History", weight: "35%", tip: "Never miss a payment. Set auto-debit for all EMIs." },
  { icon: "💳", label: "Credit Utilisation", weight: "30%", tip: "Keep credit card usage below 30% of your limit." },
  { icon: "⏳", label: "Credit Age", weight: "15%", tip: "Older accounts boost your score. Don't close old cards." },
  { icon: "🔀", label: "Credit Mix", weight: "10%", tip: "A mix of secured (home/car) and unsecured (personal/card) is ideal." },
  { icon: "🔍", label: "New Enquiries", weight: "10%", tip: "Avoid multiple loan applications within 90 days." },
];

const ScoreExplainModal = ({ score, bureau, onClose }) => {
  const currentBand = SCORE_BANDS.find(b => score >= b.min && score <= b.max) || SCORE_BANDS[4];
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)",
      zIndex: 1000, overflowY: "auto", padding: "24px 16px",
      display: "flex", justifyContent: "center", alignItems: "flex-start"
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: 20, maxWidth: 560, width: "100%",
        padding: "28px 24px", margin: "auto"
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 11, color: C.teal, fontWeight: 700, letterSpacing: 2, textTransform: "uppercase", marginBottom: 4 }}>
              Score Intelligence
            </div>
            <h2 style={{ fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
              Understanding Your Score
            </h2>
          </div>
          <button onClick={onClose} style={{ background: C.card, border: `1px solid ${C.border}`,
            borderRadius: 8, color: C.muted, cursor: "pointer", padding: "6px 12px", fontSize: 18 }}>✕</button>
        </div>

        {/* Your score highlight */}
        <div style={{
          background: `${currentBand.color}12`, border: `1px solid ${currentBand.color}30`,
          borderRadius: 14, padding: "18px 20px", marginBottom: 24
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 13, color: C.sub }}>Your {bureau || "Credit"} Score</span>
            <BureauBadge bureau={bureau} />
          </div>
          <div style={{ fontSize: 42, fontWeight: 900, color: currentBand.color, lineHeight: 1 }}>{score}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: currentBand.color, marginBottom: 8 }}>{currentBand.label}</div>
          <div style={{ fontSize: 13, color: C.sub, lineHeight: 1.7 }}>{currentBand.desc}</div>
        </div>

        {/* Score bands */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: 1, marginBottom: 12 }}>Score Bands</div>
          {SCORE_BANDS.map(band => (
            <div key={band.label} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "10px 12px",
              borderRadius: 10, marginBottom: 6,
              background: score >= band.min && score <= band.max ? `${band.color}12` : "transparent",
              border: `1px solid ${score >= band.min && score <= band.max ? band.color + "40" : "transparent"}`
            }}>
              <div style={{ width: 48, textAlign: "right", fontSize: 18, fontWeight: 900, color: band.color,
                flexShrink: 0 }}>{band.label === "Excellent" ? "750+" : `${band.min}`}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: band.color }}>{band.label}</span>
                  <span style={{ fontSize: 11, color: C.muted }}>{band.min}–{band.max}</span>
                </div>
                <Bar pct={((band.max - 300) / 600) * 100} color={band.color} />
              </div>
              {score >= band.min && score <= band.max &&
                <div style={{ fontSize: 16, flexShrink: 0 }}>← You</div>}
            </div>
          ))}
        </div>

        {/* What affects your score */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: 1, marginBottom: 12 }}>What Affects Your Score</div>
          {SCORE_FACTORS.map(f => (
            <div key={f.label} style={{
              background: C.card, border: `1px solid ${C.border}`,
              borderRadius: 12, padding: "12px 16px", marginBottom: 8
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{f.icon} {f.label}</span>
                <Pill text={f.weight} color={C.teal} />
              </div>
              <div style={{ fontSize: 12, color: C.sub, lineHeight: 1.6 }}>💡 {f.tip}</div>
            </div>
          ))}
        </div>

        {/* How to improve */}
        <div style={{ background: `${C.teal}08`, border: `1px solid ${C.teal}20`,
          borderRadius: 14, padding: "16px 18px", marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: C.teal, marginBottom: 10,
            textTransform: "uppercase", letterSpacing: 1 }}>How to Improve in 90 Days</div>
          {[
            "✅ Pay all EMIs and credit card bills on time — even one missed payment drops 50+ points",
            "✅ Reduce credit card utilisation below 30% of your total limit",
            "✅ Avoid applying for multiple loans simultaneously",
            "✅ Don't close your oldest credit card account — age matters",
            "✅ Check your report for errors and raise disputes with the bureau",
          ].map((tip, i) => (
            <div key={i} style={{ fontSize: 12, color: C.sub, lineHeight: 1.8, marginBottom: 4 }}>{tip}</div>
          ))}
        </div>

        <Btn onClick={onClose} variant="ghost" fullWidth>Close</Btn>
      </div>
    </div>
  );
};

// ── Loading Screen with animated steps ───────────────────────────────────────
const LOADING_STEPS = [
  { icon: "🔓", label: "Unlocking your PDF" },
  { icon: "📄", label: "Extracting credit data" },
  { icon: "🧠", label: "Reading score & history" },
  { icon: "💼", label: "Calculating eligibility" },
  { icon: "📊", label: "Preparing your results" },
];

const LoadingScreen = ({ mode }) => {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setStep(prev => prev < LOADING_STEPS.length - 1 ? prev + 1 : prev);
    }, 800);
    return () => clearInterval(timer);
  }, []);
  return (
    <div style={{ maxWidth: 420, margin: "80px auto", padding: "0 24px", textAlign: "center" }}>
      {/* Pulsing ring */}
      <div style={{ position: "relative", width: 80, height: 80, margin: "0 auto 32px" }}>
        <div style={{
          position: "absolute", inset: 0, borderRadius: "50%",
          border: `3px solid ${C.teal}`,
          animation: "spin 1.2s linear infinite",
        }} />
        <div style={{
          position: "absolute", inset: 6, borderRadius: "50%",
          border: `3px solid ${C.teal}30`,
        }} />
        <div style={{
          position: "absolute", inset: 0, display: "flex",
          alignItems: "center", justifyContent: "center",
          fontSize: 28
        }}>{LOADING_STEPS[step]?.icon}</div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <div style={{ fontSize: 18, fontWeight: 700, color: C.text, marginBottom: 8 }}>
        {mode === "pdf" ? "Analysing your credit report…" : "Fetching your credit data…"}
      </div>
      <div style={{ fontSize: 14, color: C.teal, marginBottom: 36 }}>
        {LOADING_STEPS[step]?.label}
      </div>

      {/* Step progress */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, textAlign: "left" }}>
        {LOADING_STEPS.map((s, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 12,
            opacity: i <= step ? 1 : 0.3, transition: "opacity 0.4s"
          }}>
            <div style={{
              width: 24, height: 24, borderRadius: 12, flexShrink: 0,
              background: i < step ? C.teal : i === step ? `${C.teal}30` : C.border,
              border: i === step ? `2px solid ${C.teal}` : "none",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700, color: i < step ? "white" : C.muted,
              transition: "all 0.4s"
            }}>
              {i < step ? "✓" : i + 1}
            </div>
            <span style={{
              fontSize: 13, color: i < step ? C.sub : i === step ? C.text : C.muted,
              fontWeight: i === step ? 600 : 400
            }}>{s.label}</span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 32, fontSize: 11, color: C.muted }}>
        🔒 Your data never leaves your device
      </div>
    </div>
  );
};

// ── Product Card ──────────────────────────────────────────────────────────────
const ProductCard = ({ product, animated }) => {
  const [open, setOpen] = useState(false);
  const color = product.verdict_color === "green" ? C.green
    : product.verdict_color === "teal" ? C.teal
    : product.verdict_color === "amber" ? C.amber : C.red;
  return (
    <div onClick={() => setOpen(!open)} style={{
      background: C.card, border: `1px solid ${open ? color + "50" : C.border}`,
      borderRadius: 14, padding: "16px 18px", cursor: "pointer", transition: "border 0.3s"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ fontSize: 22 }}>{product.icon}</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{product.label}</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 18, fontWeight: 900, color }}>{product.probability_pct}%</span>
          <Pill text={product.verdict} color={color} />
        </div>
      </div>
      <Bar pct={animated ? product.probability_pct : 0} color={color} />
      {open && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
          {product.hard_blocks?.length > 0 && product.hard_blocks.map((b, i) => (
            <div key={i} style={{ fontSize: 12, color: C.red, marginBottom: 4 }}>⛔ {b}</div>
          ))}
          {product.improvement_tips?.map((t, i) => (
            <div key={i} style={{ fontSize: 12, color: C.sub, marginBottom: 6, lineHeight: 1.6 }}>💡 {t}</div>
          ))}
          <div style={{ marginTop: 10, fontSize: 12, color: C.muted }}>
            Estimated EMI: <strong style={{ color: C.text }}>
              ₹{product.estimated_emi?.toLocaleString("en-IN")}/mo
            </strong>
          </div>
        </div>
      )}
    </div>
  );
};

// ── SCREEN 1: Home ────────────────────────────────────────────────────────────
const HomeScreen = ({ onStart, apiOnline }) => {
  const isMobile = useIsMobile();
  return (
    <div style={{ maxWidth: 640, margin: "0 auto", padding: isMobile ? "32px 20px" : "48px 24px", textAlign: "center" }}>
      <div style={{ fontSize: 12, color: C.teal, fontWeight: 700, letterSpacing: 3,
        textTransform: "uppercase", marginBottom: 16 }}>India's Zero-Inquiry Eligibility Check</div>
      <h1 style={{
        fontSize: isMobile ? 32 : 42, fontWeight: 900, color: C.text,
        lineHeight: 1.15, margin: "0 0 20px", letterSpacing: -1
      }}>
        Know Your Loan<br/>
        <span style={{ background: `linear-gradient(135deg, ${C.teal}, ${C.amber})`,
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          Odds Before You Apply
        </span>
      </h1>
      <p style={{ fontSize: isMobile ? 14 : 16, color: C.sub, lineHeight: 1.8,
        maxWidth: 480, margin: "0 auto 36px" }}>
        Check eligibility across 9 loan products without a single hard enquiry.
        Your credit score stays protected.
      </p>

      <div style={{ display: "flex", justifyContent: "center", gap: 8, flexWrap: "wrap", marginBottom: 40 }}>
        {["🔒 No Hard Inquiry", "📊 9 Products", "⚡ 60 Seconds", "🏦 All 4 Bureaus"].map(b => (
          <span key={b} style={{ background: C.card, border: `1px solid ${C.border}`,
            borderRadius: 20, padding: "5px 12px", fontSize: 11, color: C.sub }}>{b}</span>
        ))}
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
        gap: 14, marginBottom: 32
      }}>
        {[
          { icon: "📄", title: "Upload Credit Report", sub: "CIBIL · Experian · Equifax · CRIF", tag: "Most Accurate", tagColor: C.teal, mode: "pdf" },
          { icon: "⚡", title: "Quick Check by PAN", sub: "Instant soft-pull score", tag: "60 Seconds", tagColor: C.amber, mode: "pan" },
        ].map(card => (
          <div key={card.mode} onClick={() => onStart(card.mode)} style={{
            background: C.card, border: `1px solid ${C.border}`, borderRadius: 18,
            padding: "24px 20px", cursor: "pointer", textAlign: "left",
            transition: "border 0.2s, transform 0.2s",
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = C.teal; e.currentTarget.style.transform = "translateY(-2px)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.transform = "none"; }}
          >
            <div style={{ fontSize: 30, marginBottom: 12 }}>{card.icon}</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 4 }}>{card.title}</div>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 14 }}>{card.sub}</div>
            <Pill text={card.tag} color={card.tagColor} />
          </div>
        ))}
      </div>

      <div style={{ fontSize: 12, color: apiOnline ? C.green : C.red }}>
        {apiOnline ? "● API Connected" : "● API Offline — start your FastAPI server"}
      </div>
    </div>
  );
};

// ── SCREEN 2: Income Form ─────────────────────────────────────────────────────
const IncomeForm = ({ mode, onSubmit, onBack, loading }) => {
  const isMobile = useIsMobile();
  const [form, setForm] = useState({
    pan: "", mobile: "", dob: "",
    credit_score: "", gross_monthly_income: "",
    existing_emi_total: "0", proposed_loan_amount: "",
    proposed_loan_tenure: "60", employment_type: "Salaried",
    employment_months: "24", city_tier: "1",
    pdf_password: "", bureau: "CIBIL",
  });
  const [file, setFile]           = useState(null);
  const [foirPreview, setFoirPreview] = useState(null);
  const fileRef = useRef();
  const set = (k) => (v) => setForm(prev => ({ ...prev, [k]: v }));

  useEffect(() => {
    const income = parseFloat(form.gross_monthly_income);
    const emi    = parseFloat(form.existing_emi_total);
    const loan   = parseFloat(form.proposed_loan_amount);
    const tenure = parseInt(form.proposed_loan_tenure);
    if (income > 0 && loan > 0 && tenure > 0) {
      const r = 12 / 12 / 100;
      const propEmi = loan * r * Math.pow(1+r, tenure) / (Math.pow(1+r, tenure) - 1);
      const foir = (((emi + propEmi) / (income * 0.8)) * 100).toFixed(1);
      setFoirPreview({
        foir, propEmi: Math.round(propEmi),
        status: foir < 40 ? "Excellent" : foir < 50 ? "Acceptable" : "High Risk"
      });
    }
  }, [form.gross_monthly_income, form.existing_emi_total, form.proposed_loan_amount, form.proposed_loan_tenure]);

  const handleSubmit = () => onSubmit({
    income: {
      gross_monthly_income: parseFloat(form.gross_monthly_income),
      existing_emi_total:   parseFloat(form.existing_emi_total) || 0,
      proposed_loan_amount: parseFloat(form.proposed_loan_amount),
      proposed_loan_tenure: parseInt(form.proposed_loan_tenure),
      employment_type:      form.employment_type,
      employment_months:    parseInt(form.employment_months),
      city_tier:            parseInt(form.city_tier),
    },
    mode, file,
    pan: form.pan, mobile: form.mobile, dob: form.dob,
    credit_score: parseInt(form.credit_score) || 0,
    pdf_password: form.pdf_password || "",
    bureau: form.bureau,
  });

  const valid = form.gross_monthly_income && form.proposed_loan_amount &&
    (mode === "pdf" ? file : mode === "pan" ? form.pan && form.mobile && form.dob : form.credit_score);

  return (
    <div style={{ maxWidth: 560, margin: "0 auto", padding: isMobile ? "24px 16px" : "32px 24px" }}>
      <button onClick={onBack} style={{ background: "none", border: "none", color: C.muted,
        cursor: "pointer", fontSize: 14, marginBottom: 24, padding: 0 }}>← Back</button>

      <h2 style={{ fontSize: isMobile ? 22 : 26, fontWeight: 800, color: C.text, marginBottom: 6 }}>
        {mode === "pdf" ? "Upload Your Credit Report" : mode === "pan" ? "Quick Check by PAN" : "Enter Your Score"}
      </h2>
      <p style={{ fontSize: 13, color: C.muted, marginBottom: 24 }}>
        All data is processed locally. Nothing is stored or shared.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

        {/* PDF Upload */}
        {mode === "pdf" && (<>
          <div onClick={() => fileRef.current.click()} style={{
            border: `2px dashed ${file ? C.teal : C.border}`, borderRadius: 14,
            padding: "28px", textAlign: "center", cursor: "pointer",
            background: file ? `${C.teal}08` : C.card, transition: "all 0.3s"
          }}>
            <input ref={fileRef} type="file" accept=".pdf" style={{ display: "none" }}
              onChange={e => setFile(e.target.files[0])} />
            <div style={{ fontSize: 32, marginBottom: 8 }}>{file ? "✅" : "📄"}</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: file ? C.teal : C.text }}>
              {file ? file.name : "Click to upload your Credit Report PDF"}
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>
              CIBIL · Experian · Equifax · CRIF · Max 10MB
            </div>
          </div>

          {/* Bureau selector */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: 12, color: C.sub, fontWeight: 600, letterSpacing: 0.5 }}>Bureau</label>
            <select value={form.bureau} onChange={e => set("bureau")(e.target.value)}
              style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 10,
                padding: "12px 14px", color: C.text, fontSize: 14, fontFamily: "inherit", outline: "none" }}>
              {["CIBIL", "Experian", "Equifax", "CRIF"].map(b => <option key={b}>{b}</option>)}
            </select>
          </div>

          {/* Smart password hint */}
          {form.bureau !== "Equifax" ? (<>
            <Input
              label={form.bureau === "CRIF"
                ? "PDF Password — first 4 letters of name + last 4 digits of mobile (e.g. SHAN6987)"
                : "PDF Password — your DOB in DDMMYYYY (e.g. 15031990)"}
              value={form.pdf_password} onChange={set("pdf_password")}
              placeholder={form.bureau === "CRIF" ? "e.g. SHAN6987" : "DDMMYYYY"}
              type="password"
            />
            <div style={{ fontSize: 11, color: C.muted, marginTop: -8 }}>
              🔒 Password only unlocks your PDF. Never stored or sent anywhere.
            </div>
          </>) : (
            <div style={{ fontSize: 12, color: C.green, padding: "10px 14px",
              background: `${C.green}10`, borderRadius: 10, border: `1px solid ${C.green}30` }}>
              ✅ Equifax reports are not password protected — no password needed
            </div>
          )}
        </>)}

        {/* PAN Mode */}
        {mode === "pan" && (<>
          <Input label="PAN Number" value={form.pan} onChange={set("pan")} placeholder="ABCDE1234F" />
          <Input label="Mobile Number" value={form.mobile} onChange={set("mobile")} placeholder="9876543210" />
          <Input label="Date of Birth" value={form.dob} onChange={set("dob")} placeholder="DD-MM-YYYY" />
        </>)}

        {/* Manual mode */}
        {mode === "manual" && (
          <Input label="CIBIL Score" value={form.credit_score}
            onChange={set("credit_score")} placeholder="e.g. 720" type="number" />
        )}

        <div style={{ height: 1, background: C.border }} />
        <div style={{ fontSize: 11, color: C.teal, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Income & Loan Details
        </div>

        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
          <Input label="Gross Monthly Income" value={form.gross_monthly_income}
            onChange={set("gross_monthly_income")} prefix="₹" placeholder="50000" type="number" />
          <Input label="All Existing EMIs / Month" value={form.existing_emi_total}
            onChange={set("existing_emi_total")} prefix="₹" placeholder="0" type="number" />
          <Input label="Loan Amount Needed" value={form.proposed_loan_amount}
            onChange={set("proposed_loan_amount")} prefix="₹" placeholder="500000" type="number" />
          <Input label="Tenure (months)" value={form.proposed_loan_tenure}
            onChange={set("proposed_loan_tenure")} placeholder="60" type="number" />
          <Input label="Months in Current Job" value={form.employment_months}
            onChange={set("employment_months")} placeholder="24" type="number" />
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: 12, color: C.sub, fontWeight: 600, letterSpacing: 0.5 }}>Employment Type</label>
            <select value={form.employment_type} onChange={e => set("employment_type")(e.target.value)}
              style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 10,
                padding: "12px 14px", color: C.text, fontSize: 14, fontFamily: "inherit", outline: "none" }}>
              {["Salaried", "Self-Employed", "Govt", "Gig"].map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
        </div>

        {/* Live FOIR preview */}
        {foirPreview && (
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 10, color: C.muted, marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>
              Live FOIR Preview
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: 22, fontWeight: 800,
                  color: foirPreview.foir < 40 ? C.green : foirPreview.foir < 50 ? C.amber : C.red }}>
                  {foirPreview.foir}%
                </span>
                <span style={{ fontSize: 12, color: C.muted, marginLeft: 8 }}>{foirPreview.status}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 11, color: C.muted }}>Est. EMI</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>
                  ₹{foirPreview.propEmi?.toLocaleString("en-IN")}/mo
                </div>
              </div>
            </div>
          </div>
        )}

        <Btn onClick={handleSubmit} disabled={!valid} loading={loading} fullWidth>
          Check My Eligibility →
        </Btn>
      </div>
    </div>
  );
};

// ── SCREEN 3: Results ─────────────────────────────────────────────────────────
const ResultsScreen = ({ result, reportData, onReset }) => {
  const isMobile = useIsMobile();
  const [animated, setAnimated]       = useState(false);
  const [showScoreInfo, setShowScoreInfo] = useState(false);
  useEffect(() => { setTimeout(() => setAnimated(true), 200); }, []);

  const elig    = result?.eligibility || result;
  const overall = Math.round((elig?.overall_probability || 0) * 100);
  const overallColor = overall >= 70 ? C.green : overall >= 50 ? C.teal : overall >= 30 ? C.amber : C.red;
  const sorted  = [...(elig?.products || [])].sort((a, b) => b.probability - a.probability);
  const score   = reportData?.credit_score || elig?.credit_score || 0;
  const bureau  = reportData?.bureau || "CIBIL";

  return (
    <div style={{ maxWidth: 680, margin: "0 auto", padding: isMobile ? "24px 16px" : "32px 24px" }}>

      {/* Score Explain Modal */}
      {showScoreInfo && score > 0 && (
        <ScoreExplainModal score={score} bureau={bureau} onClose={() => setShowScoreInfo(false)} />
      )}

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 10, color: C.teal, fontWeight: 700, letterSpacing: 2, textTransform: "uppercase", marginBottom: 4 }}>
            Eligibility Report
          </div>
          <h2 style={{ fontSize: isMobile ? 20 : 24, fontWeight: 800, color: C.text, margin: "0 0 8px" }}>
            Your Results
          </h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <BureauBadge bureau={bureau} />
            <Pill text="✓ Zero Score Impact" color={C.green} />
          </div>
        </div>
      </div>

      {/* Score + Overall grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
        gap: 16, marginBottom: 20
      }}>
        {/* Score card — clickable */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 18, padding: "20px 16px" }}>
          <ScoreGauge score={score} onClick={score > 0 ? () => setShowScoreInfo(true) : null} />
        </div>

        {/* Overall eligibility */}
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 18, padding: 24 }}>
          <div style={{ fontSize: 10, color: C.muted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
            Overall Eligibility
          </div>
          <div style={{ fontSize: 52, fontWeight: 900, color: overallColor, lineHeight: 1 }}>{overall}%</div>
          <div style={{ fontSize: 14, color: overallColor, fontWeight: 700, marginBottom: 14 }}>
            {elig?.overall_verdict}
          </div>
          <Bar pct={animated ? overall : 0} color={overallColor} />
          <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              { label: "FOIR", value: `${elig?.foir_with_proposed?.toFixed(1)}%` },
              { label: "Net Income", value: `₹${elig?.net_monthly_income?.toLocaleString("en-IN")}` },
              { label: "Accounts", value: reportData?.total_accounts || "—" },
              { label: "DPD Flag", value: reportData?.dpd_flag || "Clean" },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: C.muted }}>{label}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: C.text }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Score quick insight strip */}
      {score > 0 && (
        <div onClick={() => setShowScoreInfo(true)} style={{
          background: C.card, border: `1px solid ${C.border}`,
          borderRadius: 14, padding: "14px 18px", marginBottom: 16,
          cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
          transition: "border 0.2s"
        }}
          onMouseEnter={e => e.currentTarget.style.borderColor = C.teal}
          onMouseLeave={e => e.currentTarget.style.borderColor = C.border}
        >
          <div>
            <div style={{ fontSize: 11, color: C.teal, fontWeight: 700, textTransform: "uppercase",
              letterSpacing: 1, marginBottom: 4 }}>Score Insights</div>
            <div style={{ fontSize: 13, color: C.sub }}>
              Understand what your {score} score means and how to improve it
            </div>
          </div>
          <span style={{ fontSize: 18, color: C.muted }}>›</span>
        </div>
      )}

      {/* Action plan */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14,
        padding: "18px 20px", marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: C.teal, fontWeight: 700, letterSpacing: 1.5,
          textTransform: "uppercase", marginBottom: 12 }}>Your Action Plan</div>
        {[elig?.credit_score_action, elig?.foir_action, elig?.enquiry_action]
          .filter(Boolean).map((tip, i) => (
          <div key={i} style={{ fontSize: 13, color: C.sub, lineHeight: 1.7, marginBottom: 8,
            paddingLeft: 16, borderLeft: `2px solid ${C.teal}40` }}>{tip}</div>
        ))}
      </div>

      {/* Top recommendation */}
      {elig?.top_recommendation && (
        <div style={{ background: `${C.teal}10`, border: `1px solid ${C.teal}30`,
          borderRadius: 14, padding: "14px 18px", marginBottom: 16 }}>
          <span style={{ fontSize: 13, color: C.teal }}>✅ {elig.top_recommendation}</span>
        </div>
      )}

      {/* Product breakdown */}
      <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: 1, marginBottom: 12 }}>Product-wise Breakdown</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 28 }}>
        {sorted.map(p => <ProductCard key={p.product_key} product={p} animated={animated} />)}
      </div>

      {/* Disclaimer */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12,
        padding: "14px 16px", marginBottom: 20 }}>
        <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.7 }}>
          ⚠️ <strong style={{ color: C.sub }}>Disclaimer:</strong> EligiCheck provides a pre-eligibility estimate for
          self-assessment only. It does not guarantee loan approval. Final eligibility is determined by your
          bank or NBFC. No hard enquiry has been made on your credit report.
        </div>
      </div>

      <Btn onClick={onReset} variant="ghost" fullWidth>← Start a New Check</Btn>
    </div>
  );
};

// ── MAIN APP ──────────────────────────────────────────────────────────────────
export default function App() {
  const [screen,     setScreen]     = useState("home");
  const [mode,       setMode]       = useState(null);
  const [result,     setResult]     = useState(null);
  const [reportData, setReportData] = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");
  const [apiOnline,  setApiOnline]  = useState(false);
  const isMobile = useIsMobile();

  useEffect(() => { checkHealth().then(setApiOnline); }, []);

  const handleStart = (m) => { setMode(m); setScreen("form"); setError(""); };

  const handleSubmit = async (payload) => {
    setLoading(true);
    setError("");
    try {
      let res, reportOut;

      if (payload.mode === "pan") {
        const scoreData = await fetchScoreByPAN(payload.pan, payload.mobile, payload.dob);
        if (!scoreData.success) throw new Error(scoreData.error || "PAN lookup failed");
        reportOut = scoreData;
        res = await manualEligibilityCheck({
          credit_score: scoreData.credit_score, enquiries_6m: scoreData.enquiries_6m || 0,
          written_off: scoreData.written_off || 0, suit_filed: 0,
          worst_dpd_12m: scoreData.dpd_flag !== "Clean" ? 30 : 0,
          credit_utilisation: 25, income: payload.income,
        });

      } else if (payload.mode === "pdf") {
        const parsed = await parseCreditReport(payload.file, payload.pdf_password || "");
        reportOut = parsed.data;
        res = await manualEligibilityCheck({
          credit_score: parsed.data.credit_score, enquiries_6m: parsed.data.enquiries_6m,
          written_off: parsed.data.written_off, suit_filed: parsed.data.suit_filed,
          worst_dpd_12m: parsed.data.worst_dpd_12m,
          credit_utilisation: parsed.data.credit_utilisation, income: payload.income,
        });

      } else {
        reportOut = { credit_score: payload.credit_score };
        res = await manualEligibilityCheck({
          credit_score: payload.credit_score, enquiries_6m: 0, written_off: 0,
          suit_filed: 0, worst_dpd_12m: 0, credit_utilisation: 25, income: payload.income,
        });
      }

      setReportData(reportOut);
      setResult(res);
      setScreen("results");

    } catch (err) {
      setError(err.message || "Something went wrong. Is your API server running?");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setScreen("home"); setMode(null);
    setResult(null); setReportData(null); setError("");
  };

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text,
      fontFamily: "'DM Sans', 'Segoe UI', sans-serif" }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />

      {/* Nav */}
      <nav style={{
        borderBottom: `1px solid ${C.border}`,
        padding: isMobile ? "14px 16px" : "16px 32px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: C.surface, position: "sticky", top: 0, zIndex: 100
      }}>
        <div onClick={handleReset} style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 18, fontWeight: 900, color: C.text }}>Eligi</span>
          <span style={{ fontSize: 18, fontWeight: 900, color: C.teal }}>Check</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Pill text="Beta" color={C.amber} />
          {screen !== "home" && !isMobile && (
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {["Check", "Income", "Results"].map((s, i) => {
                const stepIdx = screen === "form" ? 1 : screen === "results" ? 2 : 0;
                return (
                  <div key={s} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 22, height: 22, borderRadius: 11, fontSize: 10, fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: stepIdx > i ? C.teal : stepIdx === i ? `${C.teal}30` : C.border,
                      color: stepIdx >= i ? "white" : C.muted }}>
                      {stepIdx > i ? "✓" : i + 1}
                    </div>
                    <span style={{ fontSize: 11, color: stepIdx === i ? C.text : C.muted }}>{s}</span>
                    {i < 2 && <span style={{ color: C.border }}>›</span>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </nav>

      {/* Error banner */}
      {error && (
        <div style={{ background: `${C.red}15`, border: `1px solid ${C.red}40`,
          padding: "12px 24px", fontSize: 13, color: C.red, textAlign: "center" }}>
          ⚠️ {error}
        </div>
      )}

      {/* Loading overlay */}
      {loading && <LoadingScreen mode={mode} />}

      {/* Screens */}
      {!loading && screen === "home"    && <HomeScreen    onStart={handleStart} apiOnline={apiOnline} />}
      {!loading && screen === "form"    && <IncomeForm    mode={mode} onSubmit={handleSubmit} onBack={() => setScreen("home")} loading={loading} />}
      {!loading && screen === "results" && <ResultsScreen result={result} reportData={reportData} onReset={handleReset} />}
    </div>
  );
}