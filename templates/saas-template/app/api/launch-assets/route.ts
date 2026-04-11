import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Mode = "venture" | "personal";

type Offer = {
  title: string;
  price: string;
  model: string;
  promise: string;
  cta: string;
};

function sanitize(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function makeAssets(ideaName: string, mode: Mode, reason: string, insight: string, offer: Offer) {
  if (mode === "personal") {
    return {
      launchCopy: `${ideaName} is now live for personal use. ${reason}`,
      outreachCopy: `I built ${ideaName} for my workflow. The main benefit is: ${insight}`,
      shareAssets: `Internal note: ${offer.promise}. Start with one weekly review and iterate from usage.`,
      xPost: `Built ${ideaName} to remove daily workflow friction. Keeping it private, focused, and simple.`,
      linkedInPost: `Today I launched ${ideaName} as a personal operating tool. ${reason}`,
      coldEmailSubject: `${ideaName} workflow update`,
      coldEmailBody: `Quick update: I launched ${ideaName}. ${insight} If useful, I can share a short walkthrough.`,
    };
  }

  return {
    launchCopy: `${offer.title} — ${offer.promise} ${offer.price} ${offer.model}.`,
    outreachCopy: `Launching ${ideaName}. ${reason} Looking for 5 founders to test this week.`,
    shareAssets: `Offer: ${offer.title} | ${offer.price} ${offer.model} | CTA: ${offer.cta}`,
    xPost: `Launching ${ideaName}: ${offer.promise} ${offer.price} ${offer.model}. Looking for 5 early founders this week.`,
    linkedInPost: `I just launched ${ideaName}. ${reason} Offer: ${offer.title} at ${offer.price} ${offer.model}.`,
    coldEmailSubject: `${ideaName} for founders: early access`,
    coldEmailBody: `I built ${ideaName}. ${insight} Current offer is ${offer.price} ${offer.model}. Want early access?`,
  };
}

export async function POST(req: NextRequest) {
  let payload: Record<string, unknown>;

  try {
    payload = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const ideaName = sanitize(payload.ideaName) || "Untitled Idea";
  const mode: Mode = payload.mode === "personal" ? "personal" : "venture";
  const reason = sanitize(payload.reason) || "Strong enough to test quickly.";
  const insight = sanitize(payload.founderInsight) || "Scope should stay tight in week one.";
  const offerRaw = payload.offer as Record<string, unknown> | undefined;

  const offer: Offer = {
    title: sanitize(offerRaw?.title) || `${ideaName} Starter`,
    price: sanitize(offerRaw?.price) || (mode === "venture" ? "$49" : "$0"),
    model: sanitize(offerRaw?.model) || (mode === "venture" ? "one-time" : "internal"),
    promise: sanitize(offerRaw?.promise) || "Launch faster with less operational drag.",
    cta: sanitize(offerRaw?.cta) || (mode === "venture" ? "Get early access" : "Use this workflow"),
  };

  return NextResponse.json(makeAssets(ideaName, mode, reason, insight, offer), { status: 200 });
}
