import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Mode = "venture" | "personal";
type Confidence = "High" | "Medium" | "Low";
type Recommendation = "Build Now" | "Refine" | "Drop";

type DecisionSignal = {
  name: "Demand" | "Monetization" | "Speed" | "Competition";
  score: number;
};

type AnalysisResponse = {
  ideaName: string;
  mode: Mode;
  recommendation: Recommendation;
  reason: string;
  founderInsight: string;
  confidence: Confidence;
  timeToLaunch: string;
  signals: DecisionSignal[];
  source: "brief_fields" | "idea_text";
  offer: {
    title: string;
    price: string;
    model: string;
    promise: string;
    cta: string;
  };
  nextAction: string;
};

type BriefLike = {
  product_name?: unknown;
  productName?: unknown;
  demand_level?: unknown;
  monetization_proof?: unknown;
  speed_to_revenue?: unknown;
  market_saturation?: unknown;
  build_complexity?: unknown;
};

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function parseBriefLike(idea: string): BriefLike | null {
  try {
    const parsed = JSON.parse(idea) as BriefLike;
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function normalizeLevel(value: unknown): string {
  return typeof value === "string" ? value.trim().toUpperCase() : "";
}

function mapBriefSignals(brief: BriefLike): DecisionSignal[] {
  const demandLevel = normalizeLevel(brief.demand_level);
  const monetizationProof = normalizeLevel(brief.monetization_proof);
  const speedToRevenue = normalizeLevel(brief.speed_to_revenue);
  const marketSaturation = normalizeLevel(brief.market_saturation);
  const buildComplexity = normalizeLevel(brief.build_complexity);

  const demandScore =
    demandLevel === "HIGH" ? 86 : demandLevel === "MEDIUM" ? 62 : demandLevel === "LOW" ? 28 : 54;

  const monetizationScore =
    monetizationProof === "YES" ? 82 : monetizationProof === "NO" ? 24 : 56;

  let speedScore = speedToRevenue === "FAST" ? 84 : speedToRevenue === "MEDIUM" ? 58 : speedToRevenue === "SLOW" ? 34 : 56;

  if (buildComplexity === "LOW") {
    speedScore += 8;
  } else if (buildComplexity === "HIGH") {
    speedScore -= 8;
  }

  const competitionScore =
    marketSaturation === "LOW" ? 82 : marketSaturation === "MEDIUM" ? 56 : marketSaturation === "HIGH" ? 30 : 54;

  return [
    { name: "Demand", score: clampScore(demandScore) },
    { name: "Monetization", score: clampScore(monetizationScore) },
    { name: "Speed", score: clampScore(speedScore) },
    { name: "Competition", score: clampScore(competitionScore) },
  ];
}

function countKeywordHits(text: string, keywords: string[]): number {
  return keywords.reduce((count, keyword) => (text.includes(keyword) ? count + 1 : count), 0);
}

function deriveIdeaSignals(idea: string, mode: Mode): DecisionSignal[] {
  const text = idea.toLowerCase();

  const audienceKeywords = ["founder", "creator", "team", "freelancer", "agency", "coach", "student", "operator"];
  const painKeywords = ["manual", "slow", "waste", "friction", "chaos", "expensive", "mess", "lost", "bottleneck"];
  const demandHits = countKeywordHits(text, audienceKeywords) + countKeywordHits(text, painKeywords);
  const demandScore = clampScore(38 + demandHits * 8 + Math.min(text.length / 12, 16));

  const monetizationKeywords = ["subscription", "pricing", "paid", "sell", "checkout", "b2b", "saas", "revenue", "invoice"];
  const utilityKeywords = ["automation", "workflow", "assistant", "template", "scheduler", "tracker"];
  const monetizationHits = countKeywordHits(text, monetizationKeywords);
  const utilityHits = countKeywordHits(text, utilityKeywords);
  const monetizationBase = mode === "venture" ? 42 : 34;
  const monetizationScore = clampScore(monetizationBase + monetizationHits * 10 + utilityHits * 4);

  const complexityHigh = ["marketplace", "multi-tenant", "real-time", "blockchain", "social network", "video editing", "3d"];
  const complexityLow = ["landing page", "directory", "single page", "tool", "generator", "notion", "template"];
  const highComplexityHits = countKeywordHits(text, complexityHigh);
  const lowComplexityHits = countKeywordHits(text, complexityLow);
  const speedScore = clampScore(58 + lowComplexityHits * 9 - highComplexityHits * 11);

  const redOcean = ["crm", "email marketing", "project management", "chat", "ai writing", "todo app"];
  const niche = ["for", "niche", "vertical", "specific", "local", "micro"];
  const competitionScore = clampScore(54 + countKeywordHits(text, niche) * 6 - countKeywordHits(text, redOcean) * 9);

  return [
    { name: "Demand", score: demandScore },
    { name: "Monetization", score: monetizationScore },
    { name: "Speed", score: speedScore },
    { name: "Competition", score: competitionScore },
  ];
}

function recommendationFromSignals(signals: DecisionSignal[]): Recommendation {
  const demand = signals.find((s) => s.name === "Demand")?.score ?? 0;
  const monetization = signals.find((s) => s.name === "Monetization")?.score ?? 0;
  const speed = signals.find((s) => s.name === "Speed")?.score ?? 0;
  const competition = signals.find((s) => s.name === "Competition")?.score ?? 0;
  const weighted = demand * 0.3 + monetization * 0.3 + speed * 0.2 + competition * 0.2;

  if (weighted >= 67 && demand >= 52 && monetization >= 52 && speed >= 42) {
    return "Build Now";
  }

  if (demand < 35 || monetization < 35 || competition < 25) {
    return "Drop";
  }

  return "Refine";
}

function reasonFromSignals(signals: DecisionSignal[], recommendation: Recommendation): string {
  const sorted = [...signals].sort((a, b) => b.score - a.score);
  const best = sorted[0];
  const weakest = sorted[sorted.length - 1];

  if (recommendation === "Build Now") {
    return `${best.name} and execution speed are strong enough to test this fast.`;
  }

  if (recommendation === "Drop") {
    return `${weakest.name} is currently too weak for a reliable launch outcome.`;
  }

  return `${best.name} is promising, but ${weakest.name.toLowerCase()} needs refinement before building.`;
}

function insightFromSignals(signals: DecisionSignal[], recommendation: Recommendation): string {
  const demand = signals.find((s) => s.name === "Demand")?.score ?? 0;
  const monetization = signals.find((s) => s.name === "Monetization")?.score ?? 0;
  const speed = signals.find((s) => s.name === "Speed")?.score ?? 0;
  const competition = signals.find((s) => s.name === "Competition")?.score ?? 0;

  if (recommendation === "Build Now") {
    if (speed >= 70) return "Fast to launch and easy to test with paid ads.";
    return "Signals support launch, but keep scope tight in week one.";
  }

  if (recommendation === "Drop") {
    if (competition < 35) return "Too crowded unless niche is refined.";
    if (monetization < 35) return "Demand may exist, but monetization path is still weak.";
    return "This idea needs sharper positioning before execution.";
  }

  if (demand >= 65 && competition < 50) {
    return "Good demand, but positioning is too broad.";
  }

  return "Refine audience and offer before committing build cycles.";
}

function confidenceFromSignals(signals: DecisionSignal[]): Confidence {
  const scores = signals.map((s) => s.score);
  const avg = scores.reduce((acc, value) => acc + value, 0) / scores.length;
  const variance = scores.reduce((acc, value) => acc + (value - avg) ** 2, 0) / scores.length;

  if (avg >= 66 && variance <= 180) return "High";
  if (avg >= 48) return "Medium";
  return "Low";
}

function timeToLaunchFromSignals(signals: DecisionSignal[]): string {
  const speed = signals.find((s) => s.name === "Speed")?.score ?? 0;

  if (speed >= 75) return "3-7 days";
  if (speed >= 55) return "1-2 weeks";
  if (speed >= 40) return "2-4 weeks";
  return "4+ weeks";
}

function ideaNameFromInput(idea: string, brief: BriefLike | null): string {
  const productName = brief?.product_name ?? brief?.productName;
  if (typeof productName === "string" && productName.trim()) {
    return productName.trim();
  }

  const trimmed = idea.trim();
  if (!trimmed) return "Untitled Idea";

  const firstSentence = trimmed.split(/[\n.!?]/)[0]?.trim() || trimmed;
  if (firstSentence.length <= 58) return firstSentence;

  return `${firstSentence.slice(0, 55).trimEnd()}...`;
}

function priceFromSignals(mode: Mode, signals: DecisionSignal[]): string {
  if (mode === "personal") return "$0";
  const monetization = signals.find((s) => s.name === "Monetization")?.score ?? 0;
  if (monetization >= 75) return "$79";
  if (monetization >= 60) return "$49";
  return "$29";
}

function modelFromSignals(mode: Mode, signals: DecisionSignal[]): string {
  if (mode === "personal") return "internal";
  const speed = signals.find((s) => s.name === "Speed")?.score ?? 0;
  return speed >= 65 ? "one-time" : "monthly";
}

function nextActionFor(recommendation: Recommendation): string {
  if (recommendation === "Build Now") return "Ship a focused v1 and open early access today.";
  if (recommendation === "Refine") return "Narrow the target user and sharpen the value promise, then re-run analysis.";
  return "Drop this version and test a tighter niche angle before building.";
}

export async function POST(req: NextRequest) {
  let payload: { idea?: unknown; mode?: unknown };

  try {
    payload = (await req.json()) as { idea?: unknown; mode?: unknown };
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const idea = typeof payload.idea === "string" ? payload.idea.trim() : "";
  if (idea.length < 12) {
    return NextResponse.json({ error: "Please describe your idea with more detail." }, { status: 400 });
  }

  const mode: Mode = payload.mode === "personal" ? "personal" : "venture";

  const brief = parseBriefLike(idea);
  const hasMappedFields = Boolean(
    brief && (brief.demand_level || brief.monetization_proof || brief.speed_to_revenue || brief.market_saturation || brief.build_complexity),
  );

  const signals = hasMappedFields ? mapBriefSignals(brief as BriefLike) : deriveIdeaSignals(idea, mode);

  const recommendation = recommendationFromSignals(signals);
  const offerPrice = priceFromSignals(mode, signals);
  const offerModel = modelFromSignals(mode, signals);
  const response: AnalysisResponse = {
    ideaName: ideaNameFromInput(idea, brief),
    mode,
    recommendation,
    reason: reasonFromSignals(signals, recommendation),
    founderInsight: insightFromSignals(signals, recommendation),
    confidence: confidenceFromSignals(signals),
    timeToLaunch: timeToLaunchFromSignals(signals),
    signals,
    source: hasMappedFields ? "brief_fields" : "idea_text",
    offer: {
      title: `${ideaNameFromInput(idea, brief)} ${mode === "venture" ? "Launch Offer" : "Workflow Plan"}`,
      price: offerPrice,
      model: offerModel,
      promise:
        recommendation === "Build Now"
          ? "Get to live launch quickly with clear founder steps."
          : "Reduce uncertainty before committing full build effort.",
      cta: mode === "venture" ? "Get early access" : "Use this workflow",
    },
    nextAction: nextActionFor(recommendation),
  };

  return NextResponse.json(response, { status: 200 });
}
