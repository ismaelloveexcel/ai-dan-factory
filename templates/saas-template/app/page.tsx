import { readFile } from "node:fs/promises";
import path from "node:path";
import CtaForm from "./CtaForm";

type ProductBrief = {
  productName: string;
  problem: string;
  solution: string;
  cta: string;
};

type ProductConfig = {
  headline?: string;
  subheading?: string;
  description?: string;
  cta_text?: string;
  short_pitch?: string;
  benefit_bullets?: string[];
  target_user?: string;
  monetization_method?: string;
  pricing_hint?: string;
};

const FALLBACK_BRIEF: ProductBrief = {
  productName: "Your Product",
  problem: "Replace PRODUCT_BRIEF.md with a real customer pain point.",
  solution: "Describe your focused solution in one clear paragraph.",
  cta: "Get Started",
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

async function loadProductConfig(): Promise<ProductConfig> {
  const configPath = path.join(process.cwd(), "product.config.json");
  try {
    const raw = await readFile(configPath, "utf-8");
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return {
      headline: typeof parsed.headline === "string" ? parsed.headline : undefined,
      subheading: typeof parsed.subheading === "string" ? parsed.subheading : undefined,
      description: typeof parsed.description === "string" ? parsed.description : undefined,
      cta_text: typeof parsed.cta_text === "string" ? parsed.cta_text : undefined,
      short_pitch: typeof parsed.short_pitch === "string" ? parsed.short_pitch : undefined,
      benefit_bullets: Array.isArray(parsed.benefit_bullets) ? parsed.benefit_bullets.filter((b): b is string => typeof b === "string") : undefined,
      target_user: typeof parsed.target_user === "string" ? parsed.target_user : undefined,
      monetization_method: typeof parsed.monetization_method === "string" ? parsed.monetization_method : undefined,
      pricing_hint: typeof parsed.pricing_hint === "string" ? parsed.pricing_hint : undefined,
    };
  } catch {
    return {};
  }
}

export default async function Home() {
  const brief = await loadProductBrief();
  const config = await loadProductConfig();

  const headline = config.headline || brief.productName;
  const subheading = config.subheading || `Stop struggling with ${brief.problem.slice(0, 80)}.`;
  const description = config.description || brief.solution;
  const ctaText = config.cta_text || brief.cta;
  const bullets = config.benefit_bullets || [
    `Solve ${brief.problem.slice(0, 40)} instantly`,
    "Built for speed and simplicity",
    "Start seeing results from day one",
  ];
  const pricing = config.pricing_hint || "";

  return (
    <main
      style={{
        minHeight: "100vh",
        margin: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "0",
        background: "#f8fafc",
        color: "#0f172a",
        fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      {/* Hero Section */}
      <section
        style={{
          width: "100%",
          maxWidth: "100%",
          padding: "4rem 2rem 3rem",
          textAlign: "center",
          background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
        }}
      >
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <h1
            style={{
              margin: "0 0 1rem",
              fontSize: "clamp(2rem, 5vw, 3rem)",
              lineHeight: 1.1,
              fontWeight: 800,
              letterSpacing: "-0.02em",
            }}
          >
            {headline}
          </h1>
          <p
            style={{
              margin: "0 0 2rem",
              fontSize: "clamp(1.05rem, 2.5vw, 1.25rem)",
              lineHeight: 1.5,
              color: "#475569",
              maxWidth: 560,
              marginLeft: "auto",
              marginRight: "auto",
            }}
          >
            {subheading}
          </p>

          <div style={{ maxWidth: 480, margin: "0 auto" }}>
            <CtaForm cta={ctaText} />
          </div>
        </div>
      </section>

      {/* Value Proposition */}
      <section
        style={{
          width: "100%",
          maxWidth: 760,
          padding: "2.5rem 2rem",
          margin: "0 auto",
        }}
      >
        <div
          style={{
            background: "#ffffff",
            border: "1px solid #e2e8f0",
            borderRadius: 16,
            padding: "2rem",
            boxShadow: "0 4px 20px rgba(15, 23, 42, 0.04)",
          }}
        >
          <p
            style={{
              margin: "0 0 1.5rem",
              fontSize: "1.05rem",
              lineHeight: 1.6,
              color: "#334155",
            }}
          >
            {description}
          </p>

          {/* Benefit Bullets */}
          <ul
            style={{
              margin: 0,
              padding: 0,
              listStyle: "none",
              display: "grid",
              gap: "0.75rem",
            }}
          >
            {bullets.map((bullet, i) => (
              <li
                key={i}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.6rem",
                  fontSize: "1rem",
                  color: "#334155",
                  lineHeight: 1.5,
                }}
              >
                <span
                  style={{
                    flexShrink: 0,
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    background: "#10b981",
                    color: "#ffffff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    marginTop: "0.1rem",
                  }}
                >
                  ✓
                </span>
                {bullet}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Pricing / Social Proof */}
      {pricing && (
        <section
          style={{
            width: "100%",
            maxWidth: 760,
            padding: "0 2rem 2rem",
            margin: "0 auto",
            textAlign: "center",
          }}
        >
          <div
            style={{
              background: "#0f172a",
              color: "#f8fafc",
              borderRadius: 16,
              padding: "1.5rem 2rem",
            }}
          >
            <p style={{ margin: 0, fontSize: "0.85rem", letterSpacing: "0.04em", textTransform: "uppercase", opacity: 0.7 }}>
              Pricing
            </p>
            <p style={{ margin: "0.5rem 0 0", fontSize: "1.1rem", fontWeight: 600 }}>
              {pricing}
            </p>
          </div>
        </section>
      )}

      {/* Bottom CTA */}
      <section
        style={{
          width: "100%",
          maxWidth: 720,
          padding: "1rem 2rem 4rem",
          margin: "0 auto",
          textAlign: "center",
        }}
      >
        <p
          style={{
            margin: "0 0 1.5rem",
            fontSize: "1.25rem",
            fontWeight: 700,
          }}
        >
          Ready to get started?
        </p>
        <div style={{ maxWidth: 480, margin: "0 auto" }}>
          <CtaForm cta={ctaText} />
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          width: "100%",
          padding: "1.5rem 2rem",
          textAlign: "center",
          borderTop: "1px solid #e2e8f0",
          fontSize: "0.8rem",
          color: "#94a3b8",
        }}
      >
        Built with AI-DAN Factory
      </footer>
    </main>
  );
}
