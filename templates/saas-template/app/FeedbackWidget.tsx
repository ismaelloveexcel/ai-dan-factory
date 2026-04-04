"use client";

import { useState } from "react";

const FEEDBACK_OPTIONS = [
  { type: "too_expensive", label: "Too expensive" },
  { type: "not_clear", label: "Not clear" },
  { type: "not_needed", label: "Not needed" },
  { type: "other", label: "Other" },
] as const;

type FeedbackType = (typeof FEEDBACK_OPTIONS)[number]["type"];

export default function FeedbackWidget({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<"idle" | "submitting" | "done">("idle");
  const [selected, setSelected] = useState<FeedbackType | null>(null);

  async function handleFeedback(feedbackType: FeedbackType) {
    setSelected(feedbackType);
    setStatus("submitting");
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feedback_type: feedbackType,
          project_id: projectId,
        }),
      });
    } catch {
      // Best-effort submission — do not block user experience.
    }
    setStatus("done");
  }

  if (status === "done") {
    return (
      <p
        style={{
          margin: 0,
          fontSize: "0.85rem",
          color: "#64748b",
          textAlign: "center",
        }}
      >
        Thanks for your feedback!
      </p>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.5rem",
        marginTop: "1.5rem",
        paddingTop: "1rem",
        borderTop: "1px solid #e2e8f0",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.8rem",
          color: "#94a3b8",
          letterSpacing: "0.03em",
        }}
      >
        Not for you? Let us know why:
      </p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center" }}>
        {FEEDBACK_OPTIONS.map((opt) => (
          <button
            key={opt.type}
            type="button"
            disabled={status === "submitting"}
            onClick={() => handleFeedback(opt.type)}
            style={{
              border: selected === opt.type ? "2px solid #0f172a" : "1px solid #cbd5e1",
              borderRadius: 8,
              background: selected === opt.type ? "#e2e8f0" : "#f8fafc",
              color: "#475569",
              padding: "0.4rem 0.75rem",
              fontSize: "0.8rem",
              fontWeight: selected === opt.type ? 700 : 400,
              cursor: status === "submitting" ? "not-allowed" : "pointer",
              opacity: status === "submitting" && selected !== opt.type ? 0.5 : 1,
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
