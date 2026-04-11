import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type CheckItem = {
  key: string;
  label: string;
  required: boolean;
  configured: boolean;
  group: "Build" | "Monetization" | "Growth";
  notes: string;
};

function isSet(value: string | undefined): boolean {
  return Boolean(value && value.trim().length > 0);
}

export async function GET() {
  const checks: CheckItem[] = [
    {
      key: "FACTORY_BUILD_HOOK_URL",
      label: "Factory build hook",
      required: true,
      configured: isSet(process.env.FACTORY_BUILD_HOOK_URL),
      group: "Build",
      notes: "Needed for Build Now to trigger real builds.",
    },
    {
      key: "FACTORY_BUILD_HOOK_SECRET",
      label: "Factory hook secret",
      required: false,
      configured: isSet(process.env.FACTORY_BUILD_HOOK_SECRET),
      group: "Build",
      notes: "Recommended for authenticated build requests.",
    },
    {
      key: "NEXT_PUBLIC_BASE_URL",
      label: "Public base URL",
      required: true,
      configured: isSet(process.env.NEXT_PUBLIC_BASE_URL),
      group: "Build",
      notes: "Used for redirects and callback URLs.",
    },
    {
      key: "STRIPE_SECRET_KEY",
      label: "Stripe secret key",
      required: true,
      configured: isSet(process.env.STRIPE_SECRET_KEY),
      group: "Monetization",
      notes: "Required for checkout and billing APIs.",
    },
    {
      key: "NEXT_PUBLIC_STRIPE_PRICE_STARTER",
      label: "Starter price ID",
      required: true,
      configured: isSet(process.env.NEXT_PUBLIC_STRIPE_PRICE_STARTER),
      group: "Monetization",
      notes: "Stripe price id used by portal plans.",
    },
    {
      key: "NEXT_PUBLIC_STRIPE_PRICE_PRO",
      label: "Pro price ID",
      required: true,
      configured: isSet(process.env.NEXT_PUBLIC_STRIPE_PRICE_PRO),
      group: "Monetization",
      notes: "Stripe price id used by portal plans.",
    },
    {
      key: "NEXT_PUBLIC_STRIPE_PRICE_SCALE",
      label: "Scale price ID",
      required: true,
      configured: isSet(process.env.NEXT_PUBLIC_STRIPE_PRICE_SCALE),
      group: "Monetization",
      notes: "Stripe price id used by portal plans.",
    },
    {
      key: "STRIPE_WEBHOOK_SECRET",
      label: "Stripe webhook secret",
      required: false,
      configured: isSet(process.env.STRIPE_WEBHOOK_SECRET),
      group: "Monetization",
      notes: "Enables trusted payment event tracking.",
    },
    {
      key: "RESEND_API_KEY",
      label: "Resend API key",
      required: false,
      configured: isSet(process.env.RESEND_API_KEY),
      group: "Growth",
      notes: "Sends welcome/onboarding emails.",
    },
    {
      key: "EMAIL_FROM",
      label: "Email sender",
      required: false,
      configured: isSet(process.env.EMAIL_FROM),
      group: "Growth",
      notes: "Sender identity for email automation.",
    },
    {
      key: "NEXT_PUBLIC_REPO_URL",
      label: "Repository URL",
      required: false,
      configured: isSet(process.env.NEXT_PUBLIC_REPO_URL),
      group: "Growth",
      notes: "Displayed in repo awareness card.",
    },
    {
      key: "NEXT_PUBLIC_LIVE_URL",
      label: "Default live URL",
      required: false,
      configured: isSet(process.env.NEXT_PUBLIC_LIVE_URL),
      group: "Growth",
      notes: "Fallback live URL when callbacks are delayed.",
    },
  ];

  const requiredChecks = checks.filter((check) => check.required);
  const configuredRequired = requiredChecks.filter((check) => check.configured).length;
  const requiredTotal = requiredChecks.length;
  const readiness = requiredTotal > 0 ? Math.round((configuredRequired / requiredTotal) * 100) : 100;

  const status =
    readiness >= 100
      ? "ready"
      : readiness >= 60
        ? "partial"
        : "blocked";

  return NextResponse.json(
    {
      status,
      readiness,
      configuredRequired,
      requiredTotal,
      checks,
      summary:
        status === "ready"
          ? "Portal is fully configured for build and monetization."
          : status === "partial"
            ? "Portal is usable but some automations are not connected yet."
            : "Portal is missing critical settings for build/monetization.",
    },
    { status: 200 },
  );
}
