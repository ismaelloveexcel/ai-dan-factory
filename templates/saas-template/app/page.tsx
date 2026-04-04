import { readFile } from "node:fs/promises";
import path from "node:path";
import CtaForm from "./CtaForm";

type ProductBrief = {
  productName: string;
  problem: string;
  solution: string;
  cta: string;
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

export default async function Home() {
  const brief = await loadProductBrief();

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

        <CtaForm cta={brief.cta} />
      </section>
    </main>
  );
}
