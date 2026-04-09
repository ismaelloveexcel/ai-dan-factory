"use client";

import { useState } from "react";

type PricingTier = {
  name: string;
  price: string;
  period: string;
  priceId: string;
  features: string[];
  highlighted?: boolean;
};

const TIERS: PricingTier[] = [
  {
    name: "Starter",
    price: "$9",
    period: "/month",
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_STARTER || "price_starter",
    features: [
      "Core features",
      "Up to 1,000 requests/mo",
      "Email support",
    ],
  },
  {
    name: "Pro",
    price: "$29",
    period: "/month",
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_PRO || "price_pro",
    features: [
      "Everything in Starter",
      "Up to 10,000 requests/mo",
      "Priority support",
      "Advanced analytics",
    ],
    highlighted: true,
  },
  {
    name: "Scale",
    price: "$99",
    period: "/month",
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_SCALE || "price_scale",
    features: [
      "Everything in Pro",
      "Unlimited requests",
      "Dedicated support",
      "Custom integrations",
    ],
  },
];

function PricingCard({ tier }: { tier: PricingTier }) {
  const [loading, setLoading] = useState(false);

  async function handleCheckout() {
    setLoading(true);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priceId: tier.priceId }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        alert(data.error || "Something went wrong");
        return;
      }
      const { url } = (await res.json()) as { url: string };
      window.location.href = url;
    } catch {
      alert("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        flex: "1 1 280px",
        maxWidth: 340,
        background: tier.highlighted ? "#0f172a" : "#ffffff",
        color: tier.highlighted ? "#f8fafc" : "#0f172a",
        border: tier.highlighted ? "2px solid #0f172a" : "1px solid #e2e8f0",
        borderRadius: 16,
        padding: "2rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        position: "relative",
      }}
    >
      {tier.highlighted && (
        <span
          style={{
            position: "absolute",
            top: -12,
            left: "50%",
            transform: "translateX(-50%)",
            background: "#10b981",
            color: "#fff",
            fontSize: "0.75rem",
            fontWeight: 700,
            padding: "0.25rem 0.75rem",
            borderRadius: 999,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          Most Popular
        </span>
      )}

      <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>
        {tier.name}
      </h3>

      <div style={{ display: "flex", alignItems: "baseline", gap: "0.25rem" }}>
        <span style={{ fontSize: "2.5rem", fontWeight: 800 }}>{tier.price}</span>
        <span style={{ fontSize: "0.9rem", opacity: 0.7 }}>{tier.period}</span>
      </div>

      <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.5rem", flex: 1 }}>
        {tier.features.map((f, i) => (
          <li key={i} style={{ display: "flex", gap: "0.5rem", fontSize: "0.95rem" }}>
            <span style={{ color: tier.highlighted ? "#10b981" : "#10b981" }}>✓</span>
            {f}
          </li>
        ))}
      </ul>

      <button
        onClick={handleCheckout}
        disabled={loading}
        style={{
          width: "100%",
          border: "none",
          borderRadius: 12,
          padding: "0.85rem",
          fontSize: "1rem",
          fontWeight: 700,
          cursor: loading ? "not-allowed" : "pointer",
          opacity: loading ? 0.7 : 1,
          background: tier.highlighted ? "#f8fafc" : "#0f172a",
          color: tier.highlighted ? "#0f172a" : "#f8fafc",
        }}
      >
        {loading ? "Redirecting…" : "Get Started"}
      </button>
    </div>
  );
}

export default function PricingPage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "4rem 2rem",
        background: "#f8fafc",
        fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <h1
        style={{
          margin: "0 0 0.5rem",
          fontSize: "clamp(2rem, 5vw, 2.5rem)",
          fontWeight: 800,
          color: "#0f172a",
          textAlign: "center",
        }}
      >
        Simple, transparent pricing
      </h1>
      <p
        style={{
          margin: "0 0 3rem",
          color: "#64748b",
          fontSize: "1.1rem",
          textAlign: "center",
        }}
      >
        Start free, upgrade when you&apos;re ready.
      </p>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "1.5rem",
          justifyContent: "center",
          maxWidth: 1100,
        }}
      >
        {TIERS.map((tier) => (
          <PricingCard key={tier.name} tier={tier} />
        ))}
      </div>
    </main>
  );
}
