import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * POST /api/checkout — Create a Stripe Checkout session.
 *
 * Expects JSON: { priceId: string }
 * Returns: { url: string } (redirect URL to Stripe-hosted checkout)
 *
 * Required env vars:
 *   STRIPE_SECRET_KEY — Stripe secret key (sk_live_... or sk_test_...)
 *   NEXT_PUBLIC_BASE_URL — The public URL of this app (for success/cancel redirects)
 */
export async function POST(req: NextRequest) {
  const stripeKey = process.env.STRIPE_SECRET_KEY;
  if (!stripeKey) {
    return NextResponse.json(
      { error: "Stripe is not configured" },
      { status: 503 },
    );
  }

  let priceId: string;
  try {
    const body = (await req.json()) as { priceId?: unknown };
    if (typeof body.priceId !== "string" || !body.priceId.startsWith("price_")) {
      return NextResponse.json(
        { error: "Invalid priceId" },
        { status: 400 },
      );
    }
    priceId = body.priceId;
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000";

  // Call Stripe API directly (no SDK dependency needed)
  const response = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${stripeKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      "mode": "subscription",
      "line_items[0][price]": priceId,
      "line_items[0][quantity]": "1",
      "success_url": `${baseUrl}?checkout=success`,
      "cancel_url": `${baseUrl}?checkout=cancel`,
    }),
  });

  if (!response.ok) {
    const err = (await response.json()) as { error?: { message?: string } };
    console.error("Stripe error:", err);
    return NextResponse.json(
      { error: "Failed to create checkout session" },
      { status: 502 },
    );
  }

  const session = (await response.json()) as { url: string };
  return NextResponse.json({ url: session.url });
}
