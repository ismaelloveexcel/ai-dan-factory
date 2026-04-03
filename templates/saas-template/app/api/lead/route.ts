import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const email: string | undefined = (body as Record<string, unknown>)?.email as string | undefined;

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json({ error: "Valid email required" }, { status: 400 });
  }

  // TODO: store lead (e.g. save to database or send to CRM)
  console.log("[lead] captured");

  return NextResponse.json({ success: true }, { status: 201 });
}
