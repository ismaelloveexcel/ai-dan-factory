import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

export async function POST(req: NextRequest) {
  try {
    const payload = await readPayload(req);
    if (!payload.email) {
      return NextResponse.json({ error: "email is required" }, { status: 400 });
    }
    if (!EMAIL_REGEX.test(payload.email)) {
      return NextResponse.json({ error: "Invalid email format" }, { status: 400 });
    }

    // Replace this with persistence (database, CRM, etc.) in production.
    return NextResponse.json(
      {
        ok: true,
        source: payload.source || "landing-page",
        received_at: new Date().toISOString(),
      },
      { status: 201 },
    );
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
}
