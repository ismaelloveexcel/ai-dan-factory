import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type BuildResponse = {
  accepted: boolean;
  buildBackendConnected: boolean;
  message: string;
  liveUrl?: string;
  repoUrl?: string;
  health?: "healthy" | "pending" | "issue";
};

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 48);
}

export async function POST(req: NextRequest) {
  let payload: Record<string, unknown>;
  try {
    payload = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const idea = typeof payload.idea === "string" ? payload.idea.trim() : "";
  if (!idea) {
    return NextResponse.json({ error: "Idea is required" }, { status: 400 });
  }

  const buildHookUrl = process.env.FACTORY_BUILD_HOOK_URL;
  const repoUrl = process.env.NEXT_PUBLIC_REPO_URL;
  const defaultLiveUrl = process.env.NEXT_PUBLIC_LIVE_URL;

  if (!buildHookUrl) {
    const fallback: BuildResponse = {
      accepted: true,
      buildBackendConnected: false,
      message:
        "Build pipeline is not connected yet (missing FACTORY_BUILD_HOOK_URL). Connect the factory build endpoint to run live deployments.",
      repoUrl,
      liveUrl: defaultLiveUrl,
      health: defaultLiveUrl ? "healthy" : "issue",
    };
    return NextResponse.json(fallback, { status: 200 });
  }

  const projectId = slugify(idea.split(/[\n.!?]/)[0] || "founder-launch");

  try {
    const hookRes = await fetch(buildHookUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(process.env.FACTORY_BUILD_HOOK_SECRET
          ? { Authorization: `Bearer ${process.env.FACTORY_BUILD_HOOK_SECRET}` }
          : {}),
      },
      body: JSON.stringify({
        project_id: projectId || "founder-launch",
        idea,
        mode: payload.mode,
        analysis: payload.analysis,
      }),
    });

    if (!hookRes.ok) {
      const text = await hookRes.text();
      return NextResponse.json(
        {
          error: `Build request was rejected. ${text ? "Please retry after verifying build hook settings." : ""}`,
        },
        { status: 502 },
      );
    }

    let hookData: Record<string, unknown> = {};
    try {
      hookData = (await hookRes.json()) as Record<string, unknown>;
    } catch {
      // Some webhook endpoints return empty body; this is allowed.
    }

    const response: BuildResponse = {
      accepted: true,
      buildBackendConnected: true,
      message: "Build queued successfully.",
      liveUrl: typeof hookData.deployment_url === "string" ? hookData.deployment_url : defaultLiveUrl,
      repoUrl: typeof hookData.repo_url === "string" ? hookData.repo_url : repoUrl,
      health: typeof hookData.deployment_url === "string" || Boolean(defaultLiveUrl) ? "healthy" : "pending",
    };

    return NextResponse.json(response, { status: 200 });
  } catch {
    return NextResponse.json({ error: "Could not reach build service. Please retry." }, { status: 502 });
  }
}
