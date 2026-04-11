"use client";

import { useEffect, useMemo, useState } from "react";

type Mode = "venture" | "personal";
type Confidence = "High" | "Medium" | "Low";
type Recommendation = "Build Now" | "Refine" | "Drop";
type AppState = "empty" | "loading" | "analyzed" | "building" | "live" | "failed";

type DecisionSignal = {
  name: "Demand" | "Monetization" | "Speed" | "Competition";
  score: number;
};

type AnalysisResult = {
  ideaName: string;
  mode: Mode;
  recommendation: Recommendation;
  reason: string;
  founderInsight: string;
  confidence: Confidence;
  timeToLaunch: string;
  signals: DecisionSignal[];
  source: "brief_fields" | "idea_text";
};

type BuildResult = {
  accepted: boolean;
  buildBackendConnected: boolean;
  message: string;
  liveUrl?: string;
  repoUrl?: string;
  health?: "healthy" | "pending" | "issue";
};

type ProjectItem = {
  id: string;
  name: string;
  mode: Mode;
  status: "Analyzed" | "Building" | "Live" | "Failed";
  recommendation: Recommendation;
  score: number;
};

const BUILD_STEPS = [
  "Idea validated",
  "Template selected",
  "Copy prepared",
  "Deploying",
  "Live",
] as const;

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function averageSignal(signals: DecisionSignal[]): number {
  if (!signals.length) return 0;
  return Math.round(signals.reduce((acc, item) => acc + item.score, 0) / signals.length);
}

function outputsFor(analysis: AnalysisResult) {
  const strengths = [...analysis.signals].sort((a, b) => b.score - a.score);
  const topSignal = strengths[0]?.name ?? "Demand";

  if (analysis.mode === "venture") {
    return {
      title: "Outputs",
      cards: [
        {
          label: "Launch copy",
          value: `${analysis.ideaName}: ${analysis.reason}`,
        },
        {
          label: "Outreach copy",
          value: `Testing ${analysis.ideaName} with ${topSignal.toLowerCase()} as the lead angle. Interested in trying the first version this week?`,
        },
        {
          label: "Share assets",
          value: `One-page pitch + short founder note focused on ${topSignal.toLowerCase()} and ${analysis.timeToLaunch.toLowerCase()} execution speed.`,
        },
      ],
    };
  }

  return {
    title: "Outputs",
    cards: [
      {
        label: "Purpose",
        value: `Build ${analysis.ideaName} to remove repeated friction in your weekly workflow.`,
      },
      {
        label: "Workflow benefit",
        value: `Primary win: better ${topSignal.toLowerCase()} decisions with less context switching.`,
      },
      {
        label: "Internal usage notes",
        value: `Start with one core flow, then tighten it over ${analysis.timeToLaunch.toLowerCase()} based on daily use.`,
      },
    ],
  };
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("venture");
  const [idea, setIdea] = useState("");
  const [appState, setAppState] = useState<AppState>("empty");
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [buildResult, setBuildResult] = useState<BuildResult | null>(null);
  const [buildStepIndex, setBuildStepIndex] = useState(0);
  const [failureMessage, setFailureMessage] = useState("");
  const [projects, setProjects] = useState<ProjectItem[]>([]);

  const repoUrl = process.env.NEXT_PUBLIC_REPO_URL || "";
  const defaultLiveUrl = process.env.NEXT_PUBLIC_LIVE_URL || "";

  useEffect(() => {
    const raw = window.localStorage.getItem("aidan-projects");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as ProjectItem[];
      if (Array.isArray(parsed)) {
        setProjects(parsed.slice(0, 8));
      }
    } catch {
      // ignore invalid cached state
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("aidan-projects", JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
    if (appState !== "building") return;

    const interval = window.setInterval(() => {
      setBuildStepIndex((current) => {
        if (current >= BUILD_STEPS.length - 2) {
          window.clearInterval(interval);
          return current;
        }
        return current + 1;
      });
    }, 1300);

    return () => window.clearInterval(interval);
  }, [appState]);

  const score = useMemo(() => {
    if (!analysis) return 0;
    return averageSignal(analysis.signals);
  }, [analysis]);

  const canAnalyze = idea.trim().length >= 12;

  async function handleAnalyze() {
    if (!canAnalyze) return;

    setFailureMessage("");
    setBuildResult(null);
    setBuildStepIndex(0);
    setAppState("loading");

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea, mode }),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setFailureMessage(body.error || "Analysis failed. Please try again.");
        setAppState("failed");
        return;
      }

      const result = (await res.json()) as AnalysisResult;
      setAnalysis(result);
      setAppState("analyzed");

      const item: ProjectItem = {
        id: `${Date.now()}`,
        name: result.ideaName,
        mode,
        status: "Analyzed",
        recommendation: result.recommendation,
        score: averageSignal(result.signals),
      };
      setProjects((prev) => [item, ...prev].slice(0, 8));
    } catch {
      setFailureMessage("We could not analyze this idea right now. Please retry.");
      setAppState("failed");
    }
  }

  async function handleBuildNow() {
    if (!analysis) return;

    setFailureMessage("");
    setBuildResult(null);
    setBuildStepIndex(0);
    setAppState("building");

    try {
      const res = await fetch("/api/factory-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea, mode, analysis }),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setFailureMessage(body.error || "Build failed to start. Please retry.");
        setAppState("failed");
        return;
      }

      const result = (await res.json()) as BuildResult;
      setBuildResult(result);

      if (!result.buildBackendConnected) {
        setFailureMessage(result.message);
        setAppState("failed");
      } else if (result.liveUrl) {
        setBuildStepIndex(BUILD_STEPS.length - 1);
        setAppState("live");
      }

      setProjects((prev) =>
        prev.map((item, idx) => {
          if (idx !== 0) return item;
          if (result.liveUrl) {
            return { ...item, status: "Live" };
          }
          return { ...item, status: "Building" };
        }),
      );
    } catch {
      setFailureMessage("Build pipeline could not be reached. Please retry.");
      setAppState("failed");
      setProjects((prev) => prev.map((item, idx) => (idx === 0 ? { ...item, status: "Failed" } : item)));
    }
  }

  const output = analysis ? outputsFor(analysis) : null;
  const activeLiveUrl = buildResult?.liveUrl || defaultLiveUrl;

  return (
    <main className="workspace-shell">
      <div className="backdrop-glow" aria-hidden="true" />

      <section className="hero-card">
        <p className="eyebrow">AI-DAN Managing Director</p>
        <h1>What do you want to build?</h1>
        <p className="hero-subtext">Describe it. AI-DAN will analyze it, decide, and help you build it.</p>

        <div className="mode-toggle" role="tablist" aria-label="Build mode">
          <button
            className={mode === "venture" ? "mode-btn active" : "mode-btn"}
            onClick={() => setMode("venture")}
            type="button"
          >
            Venture
          </button>
          <button
            className={mode === "personal" ? "mode-btn active" : "mode-btn"}
            onClick={() => setMode("personal")}
            type="button"
          >
            Personal
          </button>
        </div>

        <label className="input-label" htmlFor="idea-input">
          Idea
        </label>
        <textarea
          id="idea-input"
          className="idea-input"
          value={idea}
          onChange={(event) => {
            setIdea(event.target.value);
            if (appState === "failed") {
              setFailureMessage("");
              setAppState("empty");
            }
          }}
          placeholder="Example: A lightweight founder CRM that turns WhatsApp conversations into next actions and weekly launch priorities."
        />

        <button className="primary-cta" type="button" onClick={handleAnalyze} disabled={!canAnalyze || appState === "loading"}>
          {appState === "loading" ? "Analyzing..." : "Analyze Idea"}
        </button>

        {appState === "failed" && failureMessage && (
          <div className="state-note error">
            <p>{failureMessage}</p>
            <button type="button" className="text-action" onClick={handleAnalyze} disabled={!canAnalyze}>
              Retry
            </button>
          </div>
        )}
      </section>

      {analysis && (
        <section className="glass-card decision-card">
          <div className="decision-topline">
            <p className="small-label">Decision</p>
            <p className="idea-name">{analysis.ideaName}</p>
          </div>

          <h2 className={analysis.recommendation === "Build Now" ? "recommendation positive" : "recommendation neutral"}>
            {analysis.recommendation}
          </h2>
          <p className="reason">{analysis.reason}</p>
          <p className="insight">{analysis.founderInsight}</p>

          <div className="meta-row">
            <div>
              <span className="meta-label">Confidence</span>
              <strong>{analysis.confidence}</strong>
            </div>
            <div>
              <span className="meta-label">Time to Launch</span>
              <strong>{analysis.timeToLaunch}</strong>
            </div>
          </div>

          <div className="signal-list" aria-label="Scoring signals">
            {analysis.signals.map((signal) => (
              <div key={signal.name} className="signal-row">
                <div className="signal-label-row">
                  <span>{signal.name}</span>
                  <span>{signal.score}</span>
                </div>
                <div className="signal-track">
                  <div className="signal-fill" style={{ width: `${clampScore(signal.score)}%` }} />
                </div>
              </div>
            ))}
          </div>

          <div className="action-row">
            <button type="button" className="build-now-btn" onClick={handleBuildNow}>
              Build Now
            </button>
            <button type="button" className="secondary-btn" onClick={handleAnalyze}>
              Refine
            </button>
            <button type="button" className="secondary-btn" onClick={() => setProjects((prev) => prev)}>
              Save
            </button>
            <button
              type="button"
              className="secondary-btn"
              onClick={() => {
                setAnalysis(null);
                setBuildResult(null);
                setBuildStepIndex(0);
                setAppState("empty");
              }}
            >
              Discard
            </button>
          </div>
        </section>
      )}

      {(appState === "building" || appState === "live" || buildResult) && (
        <section className="glass-card">
          <h3>Build Status</h3>

          <ol className="build-steps">
            {BUILD_STEPS.map((step, index) => {
              const state =
                appState === "live" || index < buildStepIndex
                  ? "done"
                  : index === buildStepIndex
                    ? "active"
                    : "pending";

              return (
                <li key={step} className={`step-item ${state}`}>
                  <span className="step-dot" aria-hidden="true" />
                  <span>{step}</span>
                </li>
              );
            })}
          </ol>

          {appState === "live" && activeLiveUrl && (
            <div className="live-panel">
              <p>Live URL</p>
              <a href={activeLiveUrl} target="_blank" rel="noreferrer">
                {activeLiveUrl}
              </a>
              <div className="live-actions">
                <a href={activeLiveUrl} target="_blank" rel="noreferrer" className="secondary-btn as-link">
                  Open
                </a>
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={async () => {
                    await navigator.clipboard.writeText(activeLiveUrl);
                  }}
                >
                  Copy Link
                </button>
              </div>
            </div>
          )}

          {appState === "failed" && buildResult?.buildBackendConnected === false && (
            <div className="state-note warning">
              <p>{buildResult.message}</p>
            </div>
          )}

          {appState === "building" && buildResult?.buildBackendConnected && !buildResult.liveUrl && (
            <div className="state-note warning">
              <p>{buildResult.message || "Build is running. Live URL will appear after deployment callback is connected."}</p>
            </div>
          )}
        </section>
      )}

      {output && (
        <section className="glass-card">
          <h3>{output.title}</h3>
          <div className="outputs-grid">
            {output.cards.map((card) => (
              <article key={card.label} className="output-card">
                <p className="small-label">{card.label}</p>
                <p>{card.value}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="glass-card projects-card">
        <h3>Projects</h3>
        {projects.length === 0 ? (
          <p className="muted">No projects yet.</p>
        ) : (
          <div className="projects-table" role="table" aria-label="Projects">
            <div className="row head" role="row">
              <span>Name</span>
              <span>Type</span>
              <span>Status</span>
              <span>Recommendation / Score</span>
              <span>Open / Manage</span>
            </div>
            {projects.map((project) => (
              <div key={project.id} className="row" role="row">
                <span>{project.name}</span>
                <span>{project.mode === "venture" ? "Venture" : "Personal"}</span>
                <span>{project.status}</span>
                <span>{project.recommendation} / {project.score}</span>
                <span>{activeLiveUrl ? <a href={activeLiveUrl}>Open</a> : "Manage"}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="glass-card repo-card">
        <h3>Repo / Deployment Awareness</h3>
        <div className="repo-grid">
          <div>
            <span className="meta-label">Repo</span>
            {repoUrl ? <a href={repoUrl}>{repoUrl}</a> : <p className="muted">Not linked</p>}
          </div>
          <div>
            <span className="meta-label">Live</span>
            {activeLiveUrl ? <a href={activeLiveUrl}>{activeLiveUrl}</a> : <p className="muted">Not live yet</p>}
          </div>
          <div>
            <span className="meta-label">Health</span>
            <p>{buildResult?.health || (activeLiveUrl ? "healthy" : "pending")}</p>
          </div>
          <div>
            <span className="meta-label">Issue Flag</span>
            <p>{appState === "failed" ? "Needs backend build connection" : "None"}</p>
          </div>
        </div>

        {analysis && (
          <p className="footnote">
            Analysis source: {analysis.source === "brief_fields" ? "mapped from structured brief fields" : "derived from idea text"}.
            Current score: {score}.
          </p>
        )}
      </section>
    </main>
  );
}
