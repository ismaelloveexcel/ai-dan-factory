import { NextRequest, NextResponse } from "next/server";
import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

/**
 * POST /api/webhook/stripe — Stripe webhook handler.
 *
 * Verifies the Stripe signature and processes checkout.session.completed events.
 *
 * Required env vars:
 *   STRIPE_SECRET_KEY — Stripe secret key
 *   STRIPE_WEBHOOK_SECRET — Webhook endpoint signing secret (whsec_...)
 */

async function verifyStripeSignature(
  payload: string,
  sigHeader: string,
  secret: string,
): Promise<boolean> {
  const parts = sigHeader.split(",");
  const timestamp = parts.find((p) => p.startsWith("t="))?.slice(2);
  const v1Sig = parts.find((p) => p.startsWith("v1="))?.slice(3);
  if (!timestamp || !v1Sig) return false;

  const signedPayload = `${timestamp}.${payload}`;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(signedPayload));
  const expectedSig = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Timing-safe comparison
  if (expectedSig.length !== v1Sig.length) return false;
  let result = 0;
  for (let i = 0; i < expectedSig.length; i++) {
    result |= expectedSig.charCodeAt(i) ^ v1Sig.charCodeAt(i);
  }
  return result === 0;
}

export async function POST(req: NextRequest) {
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!webhookSecret) {
    return NextResponse.json({ error: "Webhook not configured" }, { status: 503 });
  }

  const sig = req.headers.get("stripe-signature");
  if (!sig) {
    return NextResponse.json({ error: "Missing signature" }, { status: 400 });
  }

  const body = await req.text();
  const valid = await verifyStripeSignature(body, sig, webhookSecret);
  if (!valid) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  const event = JSON.parse(body) as {
    type: string;
    data: { object: Record<string, unknown> };
  };

  if (event.type === "checkout.session.completed") {
    const session = event.data.object;
    console.log("Payment completed:", {
      customer_email: session.customer_email,
      amount_total: session.amount_total,
      subscription: session.subscription,
    });
    await persistPaymentEvent(session);
  }

  return NextResponse.json({ received: true });
}
const DATA_DIR = process.env.LEADS_DIR || (process.env.VERCEL ? "/tmp" : path.join(process.cwd(), "data"));
const PAYMENTS_FILE = path.join(DATA_DIR, "payments.jsonl");

async function persistPaymentEvent(event: {
  customer_email?: unknown;
  amount_total?: unknown;
  currency?: unknown;
  subscription?: unknown;
}) {
  await mkdir(DATA_DIR, { recursive: true });
  const record = JSON.stringify({
    customer_email: typeof event.customer_email === "string" ? event.customer_email : "",
    amount_total: typeof event.amount_total === "number" ? event.amount_total : 0,
    currency: typeof event.currency === "string" ? event.currency : "usd",
    subscription: typeof event.subscription === "string" ? event.subscription : "",
    paid_at: new Date().toISOString(),
  });
  await appendFile(PAYMENTS_FILE, `${record}\n`, "utf-8");
}
