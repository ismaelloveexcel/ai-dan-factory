"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        background: "#f8fafc",
        fontFamily:
          "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        textAlign: "center",
      }}
    >
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 800,
          color: "#0f172a",
          margin: "0 0 1rem",
        }}
      >
        Something went wrong
      </h1>
      <p
        style={{
          color: "#64748b",
          fontSize: "1rem",
          maxWidth: 480,
          margin: "0 0 2rem",
          lineHeight: 1.6,
        }}
      >
        {error.message.includes("Missing product configuration")
          ? "This product hasn't been configured yet. Please add a PRODUCT_BRIEF.md or product.config.json."
          : "An unexpected error occurred. Please try again."}
      </p>
      <button
        onClick={reset}
        style={{
          border: "none",
          borderRadius: 12,
          background: "#0f172a",
          color: "#f8fafc",
          padding: "0.85rem 1.5rem",
          fontSize: "1rem",
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        Try again
      </button>
    </main>
  );
}
