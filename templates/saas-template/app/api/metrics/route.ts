import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

const DATA_DIR = process.env.LEADS_DIR || (process.env.VERCEL ? "/tmp" : path.join(process.cwd(), "data"));
const LEADS_FILE = path.join(DATA_DIR, "leads.jsonl");
const PAYMENTS_FILE = path.join(DATA_DIR, "payments.jsonl");

type LeadRow = {
  captured_at?: string;
};

type PaymentRow = {
  amount_total?: number;
  currency?: string;
  paid_at?: string;
};

async function readJsonLines<T>(filePath: string): Promise<T[]> {
  try {
    const raw = await readFile(filePath, "utf-8");
    return raw
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as T);
  } catch {
    return [];
  }
}

function inLastDays(iso: string | undefined, days: number): boolean {
  if (!iso) return false;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return false;
  const diff = Date.now() - date.getTime();
  return diff <= days * 24 * 60 * 60 * 1000;
}

export async function GET() {
  const leads = await readJsonLines<LeadRow>(LEADS_FILE);
  const payments = await readJsonLines<PaymentRow>(PAYMENTS_FILE);

  const leadsLast7Days = leads.filter((lead) => inLastDays(lead.captured_at, 7)).length;
  const paymentsLast30Days = payments.filter((payment) => inLastDays(payment.paid_at, 30));
  const totalRevenueCents = paymentsLast30Days.reduce(
    (total, payment) => total + (typeof payment.amount_total === "number" ? payment.amount_total : 0),
    0,
  );

  const currency = paymentsLast30Days.find((payment) => payment.currency)?.currency || "usd";
  const revenueLast30Days = (totalRevenueCents / 100).toFixed(2);

  const monetizationReady = Boolean(
    process.env.STRIPE_SECRET_KEY &&
      process.env.NEXT_PUBLIC_STRIPE_PRICE_STARTER &&
      process.env.NEXT_PUBLIC_STRIPE_PRICE_PRO &&
      process.env.NEXT_PUBLIC_STRIPE_PRICE_SCALE,
  );

  return NextResponse.json(
    {
      leadsTotal: leads.length,
      leadsLast7Days,
      paidOrdersLast30Days: paymentsLast30Days.length,
      revenueLast30Days,
      currency,
      monetizationReady,
      revenueTrackingNote:
        payments.length > 0
          ? "Live payment events are being tracked."
          : "Revenue tracking starts after first Stripe checkout completion.",
    },
    { status: 200 },
  );
}
