import { NextRequest, NextResponse } from "next/server";
import { appendFile, readFile, mkdir } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Directory for lead storage. Uses /tmp on Vercel, ./data locally. */
const LEADS_DIR = process.env.LEADS_DIR || (process.env.VERCEL ? "/tmp" : path.join(process.cwd(), "data"));
const LEADS_FILE = path.join(LEADS_DIR, "leads.jsonl");

async function readPayload(request: NextRequest): Promise<{ email?: string; source?: string }> {
  const contentType = request.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const body = (await request.json()) as { email?: unknown; source?: unknown };
    return {
      email: typeof body.email === "string" ? body.email.trim() : undefined,
      source: typeof body.source === "string" ? body.source.trim() : undefined,
    };
  }

  const formData = await request.formData();
  const emailValue = formData.get("email");
  const sourceValue = formData.get("source");
  return {
    email: typeof emailValue === "string" ? emailValue.trim() : undefined,
    source: typeof sourceValue === "string" ? sourceValue.trim() : undefined,
  };
}

async function persistLead(email: string, source: string): Promise<void> {
  await mkdir(LEADS_DIR, { recursive: true });
  const record = JSON.stringify({
    email,
    source,
    captured_at: new Date().toISOString(),
  });
  await appendFile(LEADS_FILE, record + "\n", "utf-8");
}

export async function POST(req: NextRequest) {
  try {
    const payload = await readPayload(req);
    if (!payload.email) {
      return NextResponse.json({ error: "email is required" }, { status: 400 });
    }
    if (!EMAIL_REGEX.test(payload.email)) {
      return NextResponse.json({ error: "Invalid email format" }, { status: 400 });
    }

    const source = payload.source || "landing-page";

    await persistLead(payload.email, source);

    return NextResponse.json(
      {
        ok: true,
        source,
        received_at: new Date().toISOString(),
      },
      { status: 201 },
    );
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
}

export async function GET() {
  try {
    const content = await readFile(LEADS_FILE, "utf-8");
    const leads = content
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as { email: string; source: string; captured_at: string });
    return NextResponse.json({ count: leads.length, leads });
  } catch {
    return NextResponse.json({ count: 0, leads: [] });
  }
}
