"use client";

import { useState } from "react";

export default function CtaForm({ cta }: { cta: string }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("submitting");
    setErrorMessage("");
    try {
      const res = await fetch("/api/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, source: "hero-cta" }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        setErrorMessage(data.error ?? "Submission failed. Please try again.");
        setStatus("error");
        return;
      }
      setStatus("success");
    } catch {
      setErrorMessage("Network error. Please try again.");
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <p style={{ margin: 0, color: "#16a34a", fontWeight: 600 }}>
        You&apos;re on the list — we&apos;ll be in touch!
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
      <input
        type="email"
        name="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        style={{
          flex: "1 1 200px",
          border: "1px solid #cbd5e1",
          borderRadius: 12,
          padding: "0.85rem 1rem",
          fontSize: "1rem",
          color: "#0f172a",
          background: "#f8fafc",
          outline: "none",
        }}
      />
      <button
        type="submit"
        disabled={status === "submitting"}
        style={{
          border: "none",
          borderRadius: 12,
          background: "#0f172a",
          color: "#f8fafc",
          padding: "0.85rem 1.2rem",
          fontSize: "1rem",
          fontWeight: 700,
          cursor: status === "submitting" ? "not-allowed" : "pointer",
          opacity: status === "submitting" ? 0.7 : 1,
        }}
      >
        {status === "submitting" ? "Submitting…" : cta}
      </button>
      {status === "error" && (
        <p style={{ width: "100%", margin: 0, color: "#dc2626", fontSize: "0.875rem" }}>
          {errorMessage}
        </p>
      )}
    </form>
  );
}
