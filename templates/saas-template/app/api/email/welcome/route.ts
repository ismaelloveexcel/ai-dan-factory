import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * POST /api/email/welcome — Send a welcome email via Resend.
 *
 * Expects JSON: { email: string, productName?: string }
 *
 * Required env vars:
 *   RESEND_API_KEY — Resend API key (re_...)
 *   EMAIL_FROM — Sender address (e.g. "hello@yourdomain.com")
 */
export async function POST(req: NextRequest) {
  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.EMAIL_FROM || "onboarding@resend.dev";

  if (!apiKey) {
    return NextResponse.json(
      { error: "Email service not configured" },
      { status: 503 },
    );
  }

  let email: string;
  let productName: string;
  try {
    const body = (await req.json()) as { email?: unknown; productName?: unknown };
    if (typeof body.email !== "string" || !EMAIL_REGEX.test(body.email)) {
      return NextResponse.json({ error: "Invalid email" }, { status: 400 });
    }
    email = body.email;
    productName = typeof body.productName === "string" ? body.productName : "our product";
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from,
      to: [email],
      subject: `Welcome to ${productName}!`,
      html: `
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 2rem;">
          <h1 style="font-size: 1.5rem; color: #0f172a;">Welcome aboard! 🎉</h1>
          <p style="color: #475569; line-height: 1.6;">
            Thanks for signing up for <strong>${escapeHtml(productName)}</strong>.
            We're excited to have you.
          </p>
          <p style="color: #475569; line-height: 1.6;">
            We'll keep you posted on new features and updates.
          </p>
          <p style="color: #94a3b8; font-size: 0.85rem; margin-top: 2rem;">
            If you didn't sign up, you can safely ignore this email.
          </p>
        </div>
      `,
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    console.error("Resend error:", err);
    return NextResponse.json(
      { error: "Failed to send email" },
      { status: 502 },
    );
  }

  const result = (await response.json()) as { id: string };
  return NextResponse.json({ ok: true, id: result.id });
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
