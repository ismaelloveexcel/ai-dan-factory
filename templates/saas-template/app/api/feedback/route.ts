import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const VALID_FEEDBACK_TYPES = [
  "too_expensive",
  "not_clear",
  "not_needed",
  "other",
] as const;

type FeedbackType = (typeof VALID_FEEDBACK_TYPES)[number];

function isValidFeedbackType(value: unknown): value is FeedbackType {
  return (
    typeof value === "string" &&
    VALID_FEEDBACK_TYPES.includes(value as FeedbackType)
  );
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as {
      feedback_type?: unknown;
      project_id?: unknown;
      comment?: unknown;
    };

    if (!isValidFeedbackType(body.feedback_type)) {
      return NextResponse.json(
        {
          error: `feedback_type must be one of: ${VALID_FEEDBACK_TYPES.join(", ")}`,
        },
        { status: 400 },
      );
    }

    const projectId =
      typeof body.project_id === "string" ? body.project_id.trim() : "";
    const comment =
      typeof body.comment === "string" ? body.comment.trim().slice(0, 500) : "";

    const entry = {
      feedback_type: body.feedback_type,
      project_id: projectId,
      comment,
      timestamp: new Date().toISOString(),
    };

    // In production, persist to database, file, or external service.
    // The factory feedback_processor.py script reads these entries for aggregation.

    return NextResponse.json(
      { ok: true, feedback_type: entry.feedback_type, received_at: entry.timestamp },
      { status: 201 },
    );
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 },
    );
  }
}
