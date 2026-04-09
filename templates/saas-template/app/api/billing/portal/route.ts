import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * POST /api/billing/portal — Create a Stripe Customer Portal session.
 *
 * Expects JSON: { customerId: string }
 * Returns: { url: string } (redirect URL to Stripe's self-service portal)
 *
 * Required env vars:
 *   STRIPE_SECRET_KEY — Stripe secret key
 *   NEXT_PUBLIC_BASE_URL — Return URL after portal session
 *
 * Users can manage subscriptions, update payment methods, and cancel
 * through the Stripe-hosted portal (required for compliance).
 */
export async function POST(req: NextRequest) {
  const stripeKey = process.env.STRIPE_SECRET_KEY;
  if (!stripeKey) {
    return NextResponse.json(
      { error: "Stripe is not configured" },
      { status: 503 },
    );
  }

  let customerId: string;
  try {
    const body = (await req.json()) as { customerId?: unknown };
    if (typeof body.customerId !== "string" || !body.customerId.startsWith("cus_")) {
      return NextResponse.json(
        { error: "Invalid customerId" },
        { status: 400 },
      );
    }
    customerId = body.customerId;
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000";

  const response = await fetch(
    "https://api.stripe.com/v1/billing_portal/sessions",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${stripeKey}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        customer: customerId,
        return_url: baseUrl,
      }),
    },
  );

  if (!response.ok) {
    const err = (await response.json()) as { error?: { message?: string } };
    console.error("Stripe portal error:", err);
    return NextResponse.json(
      { error: "Failed to create portal session" },
      { status: 502 },
    );
  }

  const session = (await response.json()) as { url: string };
  return NextResponse.json({ url: session.url });
}
