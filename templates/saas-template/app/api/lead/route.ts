import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const email: string | undefined = body?.email;

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json({ error: "Valid email required" }, { status: 400 });
  }

  // TODO: store lead (e.g. save to database or send to CRM)
  console.log(`[lead] captured: ${email}`);

  return NextResponse.json({ success: true }, { status: 201 });
}
