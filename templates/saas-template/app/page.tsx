"use client";

import { useState } from "react";

export default function Home() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    try {
      const res = await fetch("/api/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error("Request failed");
      setStatus("success");
      setEmail("");
    } catch {
      setStatus("error");
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "sans-serif",
        background: "#f9fafb",
        padding: "2rem",
      }}
    >
      {/* Hero */}
      <section style={{ textAlign: "center", maxWidth: 640 }}>
        <h1 style={{ fontSize: "3rem", fontWeight: 800, color: "#111827", margin: 0 }}>
          {{PRODUCT_NAME}}
        </h1>
        <p style={{ fontSize: "1.25rem", color: "#6b7280", margin: "1rem 0 2rem" }}>
          {{PRODUCT_TAGLINE}}
        </p>

        {/* CTA */}
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem", justifyContent: "center", flexWrap: "wrap" }}>
          <input
            type="email"
            required
            placeholder="Enter your email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{
              padding: "0.75rem 1rem",
              borderRadius: "0.5rem",
              border: "1px solid #d1d5db",
              fontSize: "1rem",
              minWidth: 260,
            }}
          />
          <button
            type="submit"
            disabled={status === "loading"}
            style={{
              padding: "0.75rem 1.5rem",
              borderRadius: "0.5rem",
              background: "#2563eb",
              color: "#fff",
              fontWeight: 700,
              fontSize: "1rem",
              border: "none",
              cursor: status === "loading" ? "not-allowed" : "pointer",
            }}
          >
            {status === "loading" ? "Sending…" : "Get Early Access"}
          </button>
        </form>

        {status === "success" && (
          <p style={{ marginTop: "1rem", color: "#16a34a" }}>
            🎉 You&apos;re on the list! We&apos;ll be in touch soon.
          </p>
        )}
        {status === "error" && (
          <p style={{ marginTop: "1rem", color: "#dc2626" }}>
            Something went wrong. Please try again.
          </p>
        )}
      </section>
    </main>
  );
}
