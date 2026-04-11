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

type Offer = {
  title: string;
  price: string;
  model: string;
  promise: string;
  cta: string;
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
  offer: Offer;
  nextAction: string;
};

type BuildResult = {
  accepted: boolean;
  buildBackendConnected: boolean;
  message: string;
  liveUrl?: string;
  repoUrl?: string;
  health?: "healthy" | "pending" | "issue";
};

type SetupCheck = {
  key: string;
  label: string;
  required: boolean;
  configured: boolean;
  group: "Build" | "Monetization" | "Growth";
  notes: string;
};

type SetupHealth = {
  status: "ready" | "partial" | "blocked";
  readiness: number;
  configuredRequired: number;
  requiredTotal: number;
  checks: SetupCheck[];
  summary: string;
};

type LaunchAssets = {
  launchCopy: string;
  outreachCopy: string;
  shareAssets: string;
  xPost: string;
  linkedInPost: string;
  coldEmailSubject: string;
  coldEmailBody: string;
};

type Metrics = {
  leadsTotal: number;
  leadsLast7Days: number;
  paidOrdersLast30Days: number;
  revenueLast30Days: string;
  currency: string;
  monetizationReady: boolean;
  revenueTrackingNote: string;
};

type ProjectItem = {
  id: string;
  name: string;
  mode: Mode;
  status: "Analyzed" | "Building" | "Live" | "Failed";
  recommendation: Recommendation;
  score: number;
};

const BUILD_STEPS = ["Idea validated", "Template selected", "Copy prepared", "Deploying", "Live"] as const;

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function averageSignal(signals: DecisionSignal[]): number {
  if (!signals.length) return 0;
  return Math.round(signals.reduce((acc, item) => acc + item.score, 0) / signals.length);
}

function toCurrencySymbol(code: string): string {
  const normalized = code.toUpperCase();
  if (normalized === "USD") return "$";
  if (normalized === "EUR") return "€";
  if (normalized === "GBP") return "£";
  return `${normalized} `;
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
  const [setup, setSetup] = useState<SetupHealth | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [assets, setAssets] = useState<LaunchAssets | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [assetLoading, setAssetLoading] = useState(false);

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

  useEffect(() => {
    void refreshSetup();
    void refreshMetrics();
  }, []);

  const score = useMemo(() => {
    if (!analysis) return 0;
    return averageSignal(analysis.signals);
  }, [analysis]);

  const canAnalyze = idea.trim().length >= 12;

  async function refreshSetup() {
    setSetupLoading(true);
    try {
      const res = await fetch("/api/setup-health", { cache: "no-store" });
      if (!res.ok) return;
      const result = (await res.json()) as SetupHealth;
      setSetup(result);
    } finally {
      setSetupLoading(false);
    }
  }

  async function refreshMetrics() {
    try {
      const res = await fetch("/api/metrics", { cache: "no-store" });
      if (!res.ok) return;
      const result = (await res.json()) as Metrics;
      setMetrics(result);
    } catch {
      // no-op
    }
  }

  async function generateAssets(fromAnalysis: AnalysisResult) {
    setAssetLoading(true);
    try {
      const res = await fetch("/api/launch-assets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ideaName: fromAnalysis.ideaName,
          mode: fromAnalysis.mode,
          reason: fromAnalysis.reason,
          founderInsight: fromAnalysis.founderInsight,
          offer: fromAnalysis.offer,
        }),
      });

      if (!res.ok) {
        setFailureMessage("Could not generate launch assets. Please retry.");
        return;
      }

      const result = (await res.json()) as LaunchAssets;
      setAssets(result);
    } finally {
      setAssetLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!canAnalyze) return;

    setFailureMessage("");
    setBuildResult(null);
    setBuildStepIndex(0);
    setAssets(null);
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
      await generateAssets(result);

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
          if (result.liveUrl) return { ...item, status: "Live" };
          return { ...item, status: "Building" };
        }),
      );

      await refreshSetup();
      await refreshMetrics();
    } catch {
      setFailureMessage("Build pipeline could not be reached. Please retry.");
      setAppState("failed");
      setProjects((prev) => prev.map((item, idx) => (idx === 0 ? { ...item, status: "Failed" } : item)));
    }
  }

  const activeLiveUrl = buildResult?.liveUrl || defaultLiveUrl;
  const requiredChecks = setup?.checks.filter((check) => check.required) || [];
  const missingCritical = requiredChecks.filter((check) => !check.configured);

  return (
    <main className="workspace-shell">
      <div className="backdrop-glow" aria-hidden="true" />

      <section className="hero-card">
        <p className="eyebrow">AI-DAN Managing Director</p>
        <h1>What do you want to build?</h1>
        <p className="hero-subtext">Describe it. AI-DAN will analyze it, decide, and help you build it.</p>

        <div className="mode-toggle" role="tablist" aria-label="Build mode">
          <button className={mode === "venture" ? "mode-btn active" : "mode-btn"} onClick={() => setMode("venture")} type="button">
            Venture
          </button>
          <button className={mode === "personal" ? "mode-btn active" : "mode-btn"} onClick={() => setMode("personal")} type="button">
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
          placeholder="Example: A simple founder CRM that turns conversations into next actions and launch priorities."
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

      <section className="glass-card">
        <div className="section-top">
          <h3>Setup Health</h3>
          <button type="button" className="secondary-btn" onClick={refreshSetup} disabled={setupLoading}>
            {setupLoading ? "Checking..." : "Run Check"}
          </button>
        </div>

        {setup ? (
          <>
            <p className="setup-summary">
              {setup.summary} Readiness: <strong>{setup.readiness}%</strong>
            </p>
            {missingCritical.length > 0 ? (
              <div className="state-note warning">
                <p>Missing critical setup: {missingCritical.map((item) => item.label).join(", ")}</p>
              </div>
            ) : (
              <div className="state-note ok">
                <p>Critical setup is complete.</p>
              </div>
            )}
          </>
        ) : (
          <p className="muted">Run check to confirm build and monetization settings.</p>
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
          <p className="next-action">Next action: {analysis.nextAction}</p>

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

          <div className="offer-card">
            <p className="small-label">Monetization Offer</p>
            <h4>{analysis.offer.title}</h4>
            <p>{analysis.offer.promise}</p>
            <p className="offer-price">
              {analysis.offer.price} <span>{analysis.offer.model}</span>
            </p>
            <p className="muted">CTA: {analysis.offer.cta}</p>
          </div>

          <div className="action-row">
            <button type="button" className="build-now-btn" onClick={handleBuildNow}>
              Build Now
            </button>
            <button type="button" className="secondary-btn" onClick={() => void generateAssets(analysis)}>
              {assetLoading ? "Generating..." : "Generate Launch Assets"}
            </button>
            <button type="button" className="secondary-btn" onClick={handleAnalyze}>
              Refine
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
                appState === "live" || index < buildStepIndex ? "done" : index === buildStepIndex ? "active" : "pending";

              return (
                <li key={step} className={`step-item ${state}`}>
                  <span className="step-dot" aria-hidden="true" />
                  <span>{step}</span>
                </li>
              );
            })}
          </ol>

          {activeLiveUrl && (
            <div className="live-panel">
              <p>Live URL</p>
              <a href={activeLiveUrl} target="_blank" rel="noreferrer">
                {activeLiveUrl}
              </a>
              <div className="live-actions">
                <a href={activeLiveUrl} target="_blank" rel="noreferrer" className="secondary-btn as-link">
                  Open
                </a>
                <button type="button" className="secondary-btn" onClick={async () => await navigator.clipboard.writeText(activeLiveUrl)}>
                  Copy Link
                </button>
              </div>
            </div>
          )}

          <div className="action-row">
            <button type="button" className="secondary-btn" onClick={handleBuildNow} disabled={!analysis}>
              Retry Build
            </button>
            <button type="button" className="secondary-btn" onClick={refreshSetup}>
              Re-check Setup
            </button>
          </div>
        </section>
      )}

      <section className="glass-card">
        <h3>Launch Assets</h3>
        {assets ? (
          <div className="outputs-grid simple">
            <article className="output-card">
              <p className="small-label">Launch copy</p>
              <p>{assets.launchCopy}</p>
            </article>
            <article className="output-card">
              <p className="small-label">Outreach copy</p>
              <p>{assets.outreachCopy}</p>
            </article>
            <article className="output-card">
              <p className="small-label">Share assets</p>
              <p>{assets.shareAssets}</p>
            </article>
            <article className="output-card">
              <p className="small-label">X post</p>
              <p>{assets.xPost}</p>
            </article>
            <article className="output-card">
              <p className="small-label">LinkedIn post</p>
              <p>{assets.linkedInPost}</p>
            </article>
            <article className="output-card">
              <p className="small-label">Cold email</p>
              <p>
                <strong>{assets.coldEmailSubject}</strong>
              </p>
              <p>{assets.coldEmailBody}</p>
            </article>
          </div>
        ) : (
          <p className="muted">Analyze an idea to generate launch assets automatically.</p>
        )}
      </section>

      <section className="glass-card">
        <h3>Revenue Snapshot</h3>
        {metrics ? (
          <div className="metrics-grid">
            <div>
              <span className="meta-label">Leads (7 days)</span>
              <strong>{metrics.leadsLast7Days}</strong>
            </div>
            <div>
              <span className="meta-label">Leads (all time)</span>
              <strong>{metrics.leadsTotal}</strong>
            </div>
            <div>
              <span className="meta-label">Paid orders (30 days)</span>
              <strong>{metrics.paidOrdersLast30Days}</strong>
            </div>
            <div>
              <span className="meta-label">Revenue (30 days)</span>
              <strong>
                {toCurrencySymbol(metrics.currency)}
                {metrics.revenueLast30Days}
              </strong>
            </div>
          </div>
        ) : (
          <p className="muted">Revenue metrics will appear after setup check and first events.</p>
        )}

        <p className="footnote">{metrics?.revenueTrackingNote || "Run build and checkout flow to start tracking revenue."}</p>
      </section>

      <section className="glass-card projects-card">
        <h3>Projects Command Center</h3>
        {projects.length === 0 ? (
          <p className="muted">No projects yet.</p>
        ) : (
          <div className="projects-table" role="table" aria-label="Projects">
            <div className="row head" role="row">
              <span>Name</span>
              <span>Type</span>
              <span>Status</span>
              <span>Recommendation / Score</span>
              <span>Action</span>
            </div>
            {projects.map((project, index) => (
              <div key={project.id} className="row" role="row">
                <span>{project.name}</span>
                <span>{project.mode === "venture" ? "Venture" : "Personal"}</span>
                <span>{project.status}</span>
                <span>
                  {project.recommendation} / {project.score}
                </span>
                <span>
                  {index === 0 ? (
                    <button type="button" className="secondary-btn" onClick={handleBuildNow} disabled={!analysis}>
                      Build
                    </button>
                  ) : activeLiveUrl ? (
                    <a href={activeLiveUrl}>Open</a>
                  ) : (
                    "Manage"
                  )}
                </span>
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
            <span className="meta-label">Issue flag</span>
            <p>{appState === "failed" ? "Action needed" : "None"}</p>
          </div>
        </div>

        {analysis && (
          <p className="footnote">
            Analysis source: {analysis.source === "brief_fields" ? "mapped from structured brief" : "derived from idea text"}. Current score: {score}.
          </p>
        )}
      </section>
    </main>
  );
}
