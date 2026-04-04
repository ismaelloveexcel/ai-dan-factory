import { readFile } from "node:fs/promises";
import path from "node:path";
import CtaForm from "./CtaForm";
import FeedbackWidget from "./FeedbackWidget";

type ProductBrief = {
  productName: string;
  problem: string;
  solution: string;
  cta: string;
};

type PaymentConfig = {
  project_id: string;
  payment_link: string;
  pricing_display: string;
  pricing_value: number;
  monetization_model: string;
};

const FALLBACK_BRIEF: ProductBrief = {
  productName: "Your Product",
  problem: "Replace PRODUCT_BRIEF.md with a real customer pain point.",
  solution: "Describe your focused solution in one clear paragraph.",
  cta: "Get Started",
};

const FALLBACK_PAYMENT: PaymentConfig = {
  project_id: "",
  payment_link: "",
  pricing_display: "",
  pricing_value: 0,
  monetization_model: "",
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractSection(markdown: string, sectionTitle: string): string {
  const heading = escapeRegExp(sectionTitle);
  const regex = new RegExp(`^##\\s+${heading}\\s*\\n([\\s\\S]*?)(?=\\n##\\s+|\\n#\\s+|$)`, "im");
  const match = markdown.match(regex);
  return match?.[1]?.trim() ?? "";
}

async function loadProductBrief(): Promise<ProductBrief> {
  const briefPath = path.join(process.cwd(), "PRODUCT_BRIEF.md");
  try {
    const markdown = await readFile(briefPath, "utf-8");
    return {
      productName: extractSection(markdown, "Product Name") || FALLBACK_BRIEF.productName,
      problem: extractSection(markdown, "Problem") || FALLBACK_BRIEF.problem,
      solution: extractSection(markdown, "Solution") || FALLBACK_BRIEF.solution,
      cta: extractSection(markdown, "CTA") || FALLBACK_BRIEF.cta,
    };
  } catch {
    return FALLBACK_BRIEF;
  }
}

async function loadPaymentConfig(): Promise<PaymentConfig> {
  const configPath = path.join(process.cwd(), "payment.config.json");
  try {
    const raw = await readFile(configPath, "utf-8");
    const data = JSON.parse(raw) as Record<string, unknown>;
    return {
      project_id: typeof data.project_id === "string" ? data.project_id : "",
      payment_link: typeof data.payment_link === "string" ? data.payment_link : "",
      pricing_display: typeof data.pricing_display === "string" ? data.pricing_display : "",
      pricing_value: typeof data.pricing_value === "number" ? data.pricing_value : 0,
      monetization_model: typeof data.monetization_model === "string" ? data.monetization_model : "",
    };
  } catch {
    return FALLBACK_PAYMENT;
  }
}

export default async function Home() {
  const brief = await loadProductBrief();
  const payment = await loadPaymentConfig();

  return (
    <main
      style={{
        minHeight: "100vh",
        margin: 0,
        display: "grid",
        placeItems: "center",
        padding: "2rem",
        background: "#f8fafc",
        color: "#0f172a",
      }}
    >
      <section
        style={{
          width: "100%",
          maxWidth: 760,
          background: "#ffffff",
          border: "1px solid #e2e8f0",
          borderRadius: 20,
          padding: "2.5rem 2rem",
          boxShadow: "0 16px 40px rgba(15, 23, 42, 0.06)",
        }}
      >
        <p style={{ margin: 0, fontSize: "0.85rem", letterSpacing: "0.04em", color: "#475569" }}>
          PRODUCT BRIEF
        </p>
        <h1 style={{ margin: "0.75rem 0 1rem", fontSize: "2.25rem", lineHeight: 1.1 }}>{brief.productName}</h1>

        <div style={{ display: "grid", gap: "1rem", marginBottom: "1.75rem" }}>
          <p style={{ margin: 0, color: "#334155" }}>
            <strong>Problem:</strong> {brief.problem}
          </p>
          <p style={{ margin: 0, color: "#334155" }}>
            <strong>Solution:</strong> {brief.solution}
          </p>
        </div>

        {payment.pricing_display && (
          <div
            style={{
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              borderRadius: 12,
              padding: "1rem 1.25rem",
              marginBottom: "1.25rem",
              textAlign: "center",
            }}
          >
            <p style={{ margin: 0, fontSize: "0.8rem", color: "#166534", letterSpacing: "0.03em" }}>PRICING</p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "1.1rem", fontWeight: 700, color: "#15803d" }}>
              {payment.pricing_display}
            </p>
          </div>
        )}

        {payment.payment_link ? (
          <a
            href={payment.payment_link}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-block",
              border: "none",
              borderRadius: 12,
              background: "#0f172a",
              color: "#f8fafc",
              padding: "0.85rem 1.5rem",
              fontSize: "1rem",
              fontWeight: 700,
              textDecoration: "none",
              textAlign: "center",
              width: "100%",
              boxSizing: "border-box",
            }}
          >
            {brief.cta}
          </a>
        ) : (
          <CtaForm cta={brief.cta} />
        )}

        <FeedbackWidget projectId={payment.project_id || "unknown"} />
      </section>
    </main>
  );
}
