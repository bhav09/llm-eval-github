import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Info, Play, Square, Trophy, Clock, TrendingUp, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { api, FunnelRun, FunnelStatus, FunnelStage1Artifact, FunnelRecommendation, FunnelCandidate, FunnelPodiumEntry } from "@/lib/api";
import { formatPct, formatUsd, msToSec } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useCountUp } from "@/hooks/useCountUp";

export function ModelSelectionPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [funnel, setFunnel] = useState<FunnelRun | null>(null);
  const [progress, setProgress] = useState<FunnelStatus["progress"] | null>(null);
  const [recentFunnels, setRecentFunnels] = useState<FunnelRun[]>([]);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [doApiConfigured, setDoApiConfigured] = useState(true);
  const navigate = useNavigate();

  const urlFunnelId = searchParams.get("funnel");

  async function loadFunnel(id: string) {
    try {
      const f = await api.funnel(id);
      setFunnel(f);
      // Put the funnel_id in the URL
      setSearchParams({ funnel: id }, { replace: true });
    } catch {
      setFunnel(null);
    }
  }

  async function fetchRecent() {
    try {
      const res = await api.funnels(5);
      setRecentFunnels(res.funnels || []);
    } catch {
      /* ignore */
    }
  }

  async function checkApiConfig() {
    try {
      const res = await fetch("/ready");
      const data = await res.json();
      setDoApiConfigured(data.checks?.do_api_configured ?? true);
    } catch {
      setDoApiConfigured(true);
    }
  }

  // On mount: fetch recent runs, load URL funnel, and check API config
  useEffect(() => {
    fetchRecent();
    checkApiConfig();
    if (urlFunnelId) {
      loadFunnel(urlFunnelId);
    } else {
      setFunnel(null);
    }
  }, [urlFunnelId]);

  async function startFunnel() {
    setStarting(true);
    setError(null);
    try {
      const useMock = !doApiConfigured;
      const started = await api.startFunnel({ use_mock: useMock, confirm_spend: !useMock });
      setFunnel(started);
      setSearchParams({ funnel: started.funnel_id }, { replace: true });
      fetchRecent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start");
    } finally {
      setStarting(false);
    }
  }

  async function cancelFunnel() {
    if (!funnel) return;
    setCancelling(true);
    try {
      await api.cancelFunnel(funnel.funnel_id);
      const fresh = await api.funnel(funnel.funnel_id);
      setFunnel(fresh);
      fetchRecent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel");
    } finally {
      setCancelling(false);
    }
  }

  // Poll while running.
  useEffect(() => {
    if (!funnel || funnel.status !== "running") {
      setProgress(null);
      return;
    }
    const timer = setInterval(async () => {
      try {
        const s = await api.funnelStatus(funnel.funnel_id);
        if (s.funnel.status !== "running") {
          clearInterval(timer);
          loadFunnel(funnel.funnel_id);
          fetchRecent();
        } else {
          setFunnel(s.funnel);
          setProgress(s.progress);
        }
      } catch {
        /* ignore */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [funnel?.funnel_id, funnel?.status]);

  const isRunning = funnel?.status === "running";
  const rec = funnel?.artifacts?.stage4_recommendation;
  const hasResult = funnel?.status === "complete" && rec;
  const stage1 = funnel?.artifacts?.stage1_candidates;

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      {!funnel ? (
        // Idle/Empty State: Beautiful two-column onboarding layout
        <div className="space-y-8">
          <div className="grid gap-8 md:grid-cols-5 items-start">
            {/* Left Column: Actions and description */}
            <div className="md:col-span-3 space-y-6">
              <div className="space-y-2">
                <h2 className="text-2xl font-black tracking-tight text-[var(--color-foreground)]">Model Selection</h2>
                <p className="text-sm text-[var(--color-muted)] leading-relaxed">
                  Runs a 4-stage automated funnel across live open-weight models — from stratified sampling through pilot and full evaluation — to surface a ranked podium with a production-ready recommendation.
                </p>
              </div>
              
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-sm space-y-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-tr from-[var(--color-brand)] to-[#4f46e5] text-white">
                    <Trophy size={16} />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-[var(--color-foreground)]">Start New Benchmark</h3>
                    <p className="text-[10px] text-[var(--color-muted)] mt-0.5">Executes the 4-stage selection pipeline (~45-60 API calls across 6 models)</p>
                  </div>
                </div>
                {!doApiConfigured && (
                  <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-500 leading-relaxed">
                    <strong>Notice:</strong> No DigitalOcean API key configured. The benchmark will run in <strong>Mock Mode</strong> (simulated local run).
                  </div>
                )}
                {error && (
                  <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs text-red-500 leading-relaxed">
                    {error}
                  </div>
                )}
                <Button onClick={startFunnel} disabled={starting} className="w-full">
                  <Play size={14} className="mr-2" />
                  {starting ? "Starting Selection Pipeline…" : "Run Selection Benchmark"}
                </Button>
              </div>

              <RecentRunsList runs={recentFunnels} onSelect={loadFunnel} />
            </div>

            {/* Right Column: How it works vertical pipeline */}
            <div className="md:col-span-2">
              <HowItWorks />
            </div>
          </div>

          <div className="border-t border-[var(--color-border)]/50 pt-5">
            <SelectionBasis stage1={stage1} defaultOpen={false} />
          </div>
        </div>
      ) : (
        // Active/Running/Completed State: Stepper, checklist, and results
        <div className="space-y-6 animate-fade-slide">
          <div className="flex items-center justify-between gap-4 border-b border-[var(--color-border)]/50 pb-4">
            <div>
              <h2 className="text-lg font-bold text-[var(--color-foreground)]">Model Selection Run</h2>
              <p className="text-xs text-[var(--color-muted)]">
                {funnel?.timestamp ? new Date(funnel.timestamp).toLocaleString() : ""}
              </p>
            </div>
            {!isRunning && (
              <Button variant="outline" size="sm" onClick={() => setSearchParams({}, { replace: true })}>
                Back to Pipeline
              </Button>
            )}
          </div>

          <SelectionBasis stage1={stage1} defaultOpen={false} />

          <div className="mt-4 flex items-center gap-3">
            {isRunning ? (
              <Button variant="outline" onClick={cancelFunnel} disabled={cancelling}>
                <Square size={14} className="mr-2" />
                {cancelling ? "Stopping…" : "Stop"}
              </Button>
            ) : (
              <Button onClick={startFunnel} disabled={starting}>
                <Play size={14} className="mr-2" />
                {starting ? "Starting…" : "Run again"}
              </Button>
            )}
            {funnel?.funnel_id ? (
              <span className="font-mono text-xs text-[var(--color-muted)]">#{funnel.funnel_id.slice(-8)}</span>
            ) : null}
          </div>

          {error ? (
            <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>
          ) : null}

          {/* Stepper progress (visible during run or completed results) */}
          <FunnelWidget funnel={funnel} progress={progress} stage1={stage1} />

          {/* Drawer for eliminated models metrics (progressive disclosure) */}
          {funnel?.artifacts?.stage2_pilot && (
            <EliminatedModelsPanel rejected={funnel.elimination_summary?.pilot_rejected as any} />
          )}

          {hasResult && rec ? (
            <div className="mt-8 space-y-6">
              <Podium podium={rec.podium} />
              <Insights rec={rec} />
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    const first = rec.podium.find((p) => p.rank === 1)?.slug;
                    const second = rec.podium.find((p) => p.rank === 2)?.slug;
                    if (first && second) {
                      navigate(`/eval?modelA=${encodeURIComponent(first)}&modelB=${encodeURIComponent(second)}`);
                    } else {
                      navigate("/eval");
                    }
                  }}
                >
                  Compare top 2 on Eval page
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </main>
  );
}

/* ---------- Selection basis (inline, expandable) ---------- */
/* Explains how the initial 6 candidates were chosen: one per
 * (size class × reasoning) tier from OPEN-WEIGHT models only, covering
 * small/medium/large/very-large with and without reasoning. Rendered as an
 * inline panel (not a floating tooltip) so it never gets hidden behind the
 * Run button. */

/* ---------- Idle State Helpers ---------- */

function HowItWorks() {
  const [isOpen, setIsOpen] = useState(false);

  const steps = [
    {
      title: "1. Stratified Selection",
      desc: "Pulls the live model catalog and filters to open-weight chat models only, then picks 6 representative candidates — one per (size class × reasoning) tier.",
    },
    {
      title: "2. Pilot Evaluation",
      desc: "Runs all 6 candidates on 5 random issues. Evaluates basic operational error and invalid rates to eliminate low-performing models.",
    },
    {
      title: "3. Full Evaluation",
      desc: "Runs the surviving finalists on 10 random issues (reusing predictions from the pilot to save cost) to collect deeper accuracy and latency data.",
    },
    {
      title: "4. Multi-Criteria Ranking",
      desc: "Ranks finalists by a composite score across accuracy, latency, cost, and reliability, recommending the best Value and Quality picks.",
    },
  ];

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm overflow-hidden">
      {/* Clickable header — always visible */}
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 px-5 py-3.5 text-left hover:bg-[var(--color-surface-muted)] transition-colors"
      >
        <span className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">
          The Evaluation Pipeline
        </span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`text-[var(--color-muted)] transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {/* Collapsable body */}
      {isOpen && (
        <div className="px-5 pb-5 space-y-4">
          <div className="space-y-4 relative">
            {/* Connector Line */}
            <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gradient-to-b from-blue-500/30 to-indigo-500/10" />
            {steps.map((s, idx) => (
              <div key={idx} className="flex gap-3 relative animate-scale-in" style={{ animationDelay: `${idx * 75}ms` }}>
                <div className="h-6 w-6 rounded-full bg-gradient-to-tr from-blue-500 to-[#4f46e5] text-white flex items-center justify-center text-[10px] font-bold z-10 shrink-0 shadow-sm shadow-blue-500/10">
                  {idx + 1}
                </div>
                <div>
                  <h4 className="text-xs font-bold text-[var(--color-foreground)]">{s.title}</h4>
                  <p className="text-[10px] text-[var(--color-muted)] leading-relaxed mt-0.5">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RecentRunsList({
  runs,
  onSelect,
}: {
  runs: FunnelRun[];
  onSelect: (id: string) => void;
}) {
  if (runs.length === 0) return null;
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Recent Evaluation Runs</h3>
      <div className="space-y-2">
        {runs.slice(0, 3).map((r, idx) => (
          <div
            key={r.funnel_id}
            className="flex items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-4 py-3 shadow-sm hover:border-[var(--color-brand)]/30 transition-colors animate-scale-in"
            style={{ animationDelay: `${idx * 50}ms` }}
          >
            <div>
              <div className="font-mono text-xs font-bold text-[var(--color-foreground)]">
                #{r.funnel_id.slice(-8)}
              </div>
              <div className="text-[9px] text-[var(--color-muted)] mt-0.5">
                {new Date(r.timestamp).toLocaleString()} · {r.status}
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={() => onSelect(r.funnel_id)}>
              View Details
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Eliminated Models Drawer ---------- */

function EliminatedModelsPanel({
  rejected,
}: {
  rejected: Array<{
    slug: string;
    reason: string;
    accuracy: number;
    cost_per_call: number;
    p95_latency_ms: number;
    throughput_rps: number;
    composite_score: number;
    weaknesses?: string[];
  }>;
}) {
  const [open, setOpen] = useState(false);
  if (!rejected || rejected.length === 0) return null;

  return (
    <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden shadow-sm animate-scale-in">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-3.5 text-left text-xs font-bold text-[var(--color-foreground)] hover:bg-[var(--color-hover)] transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
          ⚠️ {rejected.length} models eliminated after Stage 2 (Pilot)
        </span>
        <span className="text-[10px] bg-[var(--color-hover)] px-2.5 py-0.5 rounded-full uppercase tracking-wider">
          {open ? "Collapse" : "Expand Metrics"}
        </span>
      </button>

      {open && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-surface-muted)] dark:bg-slate-900/20 p-5 space-y-4 animate-slide-down">
          <p className="text-[10px] text-[var(--color-muted)] leading-relaxed">
            These models failed to meet operational thresholds or received a lower overall composite readiness score (weighted accuracy, cost, latency, throughput, and reliability).
          </p>
          <div className="space-y-3">
            {rejected.map((r, idx) => (
              <div
                key={r.slug}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm space-y-3 animate-scale-in"
                style={{ animationDelay: `${idx * 50}ms` }}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h4 className="font-mono text-xs font-bold text-[var(--color-foreground)]">{r.slug}</h4>
                    <p className="text-[10px] text-[var(--color-muted)] mt-1 font-semibold italic">{r.reason}</p>
                  </div>
                  <div className="flex gap-1">
                    {r.weaknesses?.map((w) => (
                      <span
                        key={w}
                        className="rounded-full bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                      >
                        Low {w}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2 border-t border-[var(--color-border)]/50 text-[10px]">
                  <div>
                    <span className="block text-[var(--color-muted)] font-medium">Accuracy</span>
                    <span className="font-mono font-bold text-[var(--color-foreground)]">{formatPct(r.accuracy)}</span>
                  </div>
                  <div>
                    <span className="block text-[var(--color-muted)] font-medium">Cost/Call</span>
                    <span className="font-mono font-bold text-[var(--color-foreground)]">{formatUsd(r.cost_per_call)}</span>
                  </div>
                  <div>
                    <span className="block text-[var(--color-muted)] font-medium">p95 Latency</span>
                    <span className="font-mono font-bold text-[var(--color-foreground)]">{msToSec(r.p95_latency_ms)}s</span>
                  </div>
                  <div>
                    <span className="block text-[var(--color-muted)] font-medium">Throughput</span>
                    <span className="font-mono font-bold text-[var(--color-foreground)]">{r.throughput_rps.toFixed(1)} rps</span>
                  </div>
                  <div>
                    <span className="block text-[var(--color-muted)] font-medium">Readiness Score</span>
                    <span className="font-mono font-bold text-amber-600 dark:text-amber-400">{(r.composite_score || 0).toFixed(3)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Selection basis (inline, expandable) ---------- */

function SelectionBasis({
  stage1,
  defaultOpen = false,
}: {
  stage1: FunnelStage1Artifact | undefined;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const candidates = stage1?.selected ?? [];
  const openWeightCount = stage1?.open_weight_slugs;
  const total = stage1?.total_live_slugs;

  useEffect(() => {
    setOpen(defaultOpen);
  }, [defaultOpen]);

  const summary = candidates.length > 0
    ? `${candidates.length} open-weight models selected from ${openWeightCount ?? "?"} eligible slugs`
    : "6 open-weight models selected by stratified sampling";

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] dark:bg-[var(--color-brand-muted)] transition-all duration-200 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs font-semibold text-[var(--color-muted)] hover:text-[var(--color-foreground)] cursor-pointer"
      >
        <Info size={14} className="shrink-0 text-[var(--color-brand)]" />
        <span className="flex-1">{summary}</span>
        <span className="text-[10px] bg-[var(--color-hover)] px-2 py-0.5 rounded-full uppercase tracking-wider">{open ? "Hide" : "Details"}</span>
      </button>
      {open ? (
        <div className="border-t border-[var(--color-border)] px-4 py-3 text-xs">
          <p className="leading-relaxed text-[var(--color-muted)] mb-3">
            One model per <span className="text-[var(--color-foreground)] font-medium">(size class × reasoning)</span> tier,
            covering small / medium / large / very-large, with and without reasoning.
            Only <span className="text-[var(--color-foreground)] font-medium">open-weight chat models</span> are eligible —
            closed-source frontier (Anthropic, OpenAI GPT/o-series), embeddings, image/video, TTS, and routers are excluded.
            {total != null ? ` ${total} live slugs found; ${openWeightCount ?? 0} eligible after filtering.` : ""}
          </p>
          {candidates.length > 0 ? (
            <div className="grid gap-2 sm:grid-cols-2 mt-2">
              {candidates.map((c: FunnelCandidate) => (
                <div key={c.slug} className="flex justify-between items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2 shadow-sm">
                  <span className="font-mono text-xs font-semibold text-[var(--color-foreground)] truncate max-w-[170px]" title={c.slug}>{c.slug}</span>
                  <span className="text-[10px] text-[var(--color-muted)] uppercase tracking-wider">
                    {c.size_class}
                    {c.reasoning ? " · reasoning" : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/* ---------- Funnel progress widget ---------- */
/* A real funnel shape: 4 stacked trapezoid layers, each a different DigitalOcean
 * blue shade, narrowing from "all live slugs" down to "2 finalists". The current
 * stage pulses; completed stages are filled; future stages are dim. */

const STAGES = [
  { key: "S1", label: "Stratified select", detail: "Pick 6 from live slugs", gradient: "from-blue-950 to-indigo-950 dark:from-slate-900 dark:to-slate-950" },
  { key: "S2", label: "Pilot", detail: "5 issues × 6 models", gradient: "from-blue-900 to-indigo-900 dark:from-blue-950 dark:to-indigo-950" },
  { key: "S3", label: "Full eval", detail: "10 issues × survivors", gradient: "from-blue-800 to-blue-900 dark:from-blue-900/60 dark:to-blue-950/60" },
  { key: "S4", label: "Recommend", detail: "Rank & pick top 2", gradient: "from-[var(--color-brand)] to-[#4f46e5] dark:from-blue-600 dark:to-indigo-600" },
];

function FunnelWidget({
  funnel,
  progress,
  stage1,
}: {
  funnel: FunnelRun;
  progress: FunnelStatus["progress"];
  stage1: FunnelStage1Artifact | undefined;
}) {
  const stageIdx = progress ? progress.stage - 1 : (funnel.stage_reached > 0 ? funnel.stage_reached - 1 : 0);
  const counts = [
    stage1?.selected?.length ?? 6,
    funnel.pilot_model_slugs.length || 6,
    funnel.full_model_slugs.length || 6,
    funnel.artifacts?.stage4_recommendation?.finalists?.length ?? 2,
  ];

  const modelProgress =
    progress && progress.model_count > 0
      ? `model ${progress.model_index} of ${progress.model_count}`
      : null;

  const [elapsed, setElapsed] = useState<number>(0);

  useEffect(() => {
    if (funnel.status !== "running") return;
    const startStr = funnel.started_at || funnel.timestamp;
    if (!startStr) return;
    const startMs = new Date(startStr).getTime();

    setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));

    const timerId = setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    }, 1000);

    return () => clearInterval(timerId);
  }, [funnel.started_at, funnel.timestamp, funnel.status]);

  const currentStageModels =
    progress?.stage === 2
      ? (funnel.pilot_model_slugs.length > 0 ? funnel.pilot_model_slugs : (stage1?.selected?.map((c) => c.slug) || []))
      : progress?.stage === 3
      ? funnel.full_model_slugs
      : [];

  return (
    <div className="mt-8 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Clock size={16} className="text-[var(--color-brand)] animate-pulse" />
          <h3 className="text-sm font-semibold tracking-tight">Funnel Progress</h3>
        </div>
        <span className="font-mono text-xs text-[var(--color-muted)]">
          {progress?.current_slug ?? ""}
        </span>
      </div>

      <div className="flex flex-col items-center gap-2">
        {STAGES.map((s, i) => {
          const done = i < stageIdx;
          const active = i === stageIdx;
          const width = 100 - i * 14; 
          const layer = (
            <div
              style={{ width: `${width}%` }}
              className={cn(
                "bg-gradient-to-r",
                s.gradient,
                "flex items-center justify-between rounded-xl px-5 py-3.5 transition-all duration-300 shadow-sm border border-white/5",
                active ? "ring-2 ring-[var(--color-brand)] scale-[1.03] animate-pulse-glow" : "",
                done || active ? "opacity-100" : "opacity-35"
              )}
              data-funnel-layer={s.key}
            >
              <div className="text-left">
                <div className="text-xs font-bold tracking-tight text-white">{s.label}</div>
                <div className="text-[10px] text-white/70 font-medium mt-0.5">{s.detail}</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-extrabold text-white tracking-tight">{counts[i]}</div>
                <div className="text-[10px] text-white/70 font-semibold uppercase tracking-wider">
                  {i === 0 ? "slugs" : i === 3 ? "finalists" : "models"}
                </div>
              </div>
            </div>
          );
          return (
            <div key={s.key} style={{ width: "100%" }} className="flex justify-center">
              {layer}
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-center gap-2 text-xs text-[var(--color-muted)] font-medium">
        <span>{STAGES[stageIdx]?.label ?? "Preparing…"}</span>
        {modelProgress ? <span>· {modelProgress}</span> : null}
      </div>

      {currentStageModels.length > 0 ? (
        <div className="mt-6 border-t border-[var(--color-border)] pt-5 space-y-3">
          <div className="flex items-center justify-between text-xs font-bold text-[var(--color-muted)] uppercase tracking-wider mb-1">
            <span>Model Execution Checklist</span>
            {funnel.status === "running" && elapsed > 0 ? (
              <span className="inline-flex items-center gap-1 bg-[var(--color-hover)] px-2.5 py-1 rounded-full text-[10px] text-[var(--color-foreground)] font-mono">
                <Clock size={11} />
                Elapsed: {elapsed >= 60 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : `${elapsed}s`}
              </span>
            ) : null}
          </div>
          <div className="space-y-2">
            {currentStageModels.map((slug, idx) => {
              const modelNum = idx + 1;
              const isCompleted = progress ? modelNum < progress.model_index : false;
              const isActive = progress ? modelNum === progress.model_index : false;

              return (
                <div
                  key={slug}
                  className={cn(
                    "flex items-center justify-between rounded-xl px-4 py-3 text-xs transition-all duration-200 border",
                    isActive
                      ? "bg-[var(--color-brand-muted)] border-[var(--color-brand)]/20 shadow-sm"
                      : "border-transparent bg-[var(--color-surface-muted)] hover:bg-[var(--color-hover)]"
                  )}
                >
                  <div className="flex items-center gap-3 font-mono">
                    {isCompleted ? (
                      <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                    ) : isActive ? (
                      <span className="relative flex h-3 w-3 items-center justify-center shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-brand)] opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[var(--color-brand)]"></span>
                      </span>
                    ) : (
                      <div className="h-2 w-2 rounded-full bg-[var(--color-muted)]/30 shrink-0" />
                    )}
                    <span
                      className={cn(
                        "truncate max-w-[200px] sm:max-w-xs font-semibold",
                        isCompleted ? "line-through text-[var(--color-muted)]/70 font-normal" : "",
                        isActive ? "text-[var(--color-foreground)] font-bold" : "text-[var(--color-muted)]",
                      )}
                    >
                      {slug}
                    </span>
                  </div>
                  <div>
                    {isCompleted ? (
                      <span className="text-[9px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/10 px-2.5 py-0.5 rounded-full font-bold">Done</span>
                    ) : isActive ? (
                      <span className="text-[9px] bg-[var(--color-brand)]/15 text-[var(--color-brand)] border border-[var(--color-brand)]/25 px-2.5 py-0.5 rounded-full font-bold inline-flex items-center gap-1">
                        <Clock size={10} className="animate-spin" />
                        Running
                        {progress?.issue_count && progress?.issue_count > 0 ? (
                          <>: {progress.issue_index}/{progress.issue_count}</>
                        ) : null}
                      </span>
                    ) : (
                      <span className="text-[10px] text-[var(--color-muted)] font-medium">Pending</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        funnel.status === "running" && elapsed > 0 ? (
          <div className="mt-4 flex justify-end text-xs text-[var(--color-muted)]">
            <span className="inline-flex items-center gap-1 bg-[var(--color-hover)] px-2.5 py-1 rounded-full text-[10px] font-mono">
              <Clock size={11} />
              Elapsed: {elapsed >= 60 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : `${elapsed}s`}
            </span>
          </div>
        ) : null
      )}
    </div>
  );
}

/* ---------- Podium (1st / 2nd / 3rd) ---------- */
/* Colosseum-style ranking with DigitalOcean blues. 2nd on left, 1st in the
 * center (tallest), 3rd on the right — a classic podium. */

function PodiumEntryCard({
  p,
  heights,
  borderColors,
  stepGradients,
  badgeGradients,
}: {
  p: FunnelPodiumEntry;
  heights: Record<number, string>;
  borderColors: Record<number, string>;
  stepGradients: Record<number, string>;
  badgeGradients: Record<number, string>;
}) {
  const animatedAccuracy = useCountUp(p.accuracy);

  return (
    <div className="flex flex-col items-center animate-scale-in" style={{ width: "32%" }}>
      <div className="mb-3 text-center">
        <div className="text-[9px] font-bold uppercase tracking-wider text-[var(--color-muted)]">
          {ordinal(p.rank)} place
        </div>
        <div className="mt-1 font-mono text-xs font-bold text-[var(--color-foreground)] truncate max-w-[100px] sm:max-w-none" title={p.slug}>
          {p.slug}
        </div>
        <div className="mt-1.5 text-sm font-extrabold text-[var(--color-brand)]">
          {formatPct(animatedAccuracy)}
        </div>
        <div className="text-[10px] text-[var(--color-muted)] mt-0.5 leading-normal">
          {formatUsd(p.cost_per_call)}/call <br />
          {msToSec(p.p95_latency_ms)}s p95
        </div>
      </div>
      <div
        className={cn(
          "w-full rounded-t-xl text-center font-black flex flex-col justify-between items-center py-2.5 border border-b-0 shadow-lg transition-all duration-300 bg-gradient-to-b",
          heights[p.rank as 1 | 2 | 3],
          borderColors[p.rank],
          stepGradients[p.rank]
        )}
      >
        <span className={cn("flex items-center justify-center h-6 w-6 rounded-full border text-xs font-black bg-gradient-to-tr shadow-sm", badgeGradients[p.rank])}>
          {p.rank}
        </span>
        <div className="text-[9px] text-[var(--color-muted)] tracking-widest font-black uppercase pb-1">
          {p.rank === 1 ? "Champ" : p.rank === 2 ? "Silver" : "Bronze"}
        </div>
      </div>
    </div>
  );
}

function Podium({ podium }: { podium: FunnelPodiumEntry[] }) {
  if (!podium || podium.length === 0) return null;
  // Order for display: 2nd, 1st, 3rd
  const order = [podium.find((p) => p.rank === 2), podium.find((p) => p.rank === 1), podium.find((p) => p.rank === 3)].filter(
    Boolean,
  ) as FunnelPodiumEntry[];
  
  const heights = { 1: "h-32", 2: "h-24", 3: "h-18" };
  const borderColors: Record<number, string> = {
    1: "border-amber-400/40 shadow-amber-400/5",
    2: "border-slate-300/40 shadow-slate-300/5",
    3: "border-amber-700/40 shadow-amber-700/5",
  };
  const badgeGradients: Record<number, string> = {
    1: "from-amber-400 to-yellow-500 text-white border-amber-300",
    2: "from-slate-300 to-slate-400 text-slate-800 border-slate-200",
    3: "from-amber-700 to-amber-800 text-white border-amber-600",
  };
  const stepGradients: Record<number, string> = {
    1: "from-amber-500/10 to-yellow-600/5 hover:from-amber-500/15 border-t-amber-400/30 dark:border-t-amber-400/10",
    2: "from-slate-400/10 to-slate-500/5 hover:from-slate-400/15 border-t-slate-400/30 dark:border-t-slate-400/10",
    3: "from-amber-700/10 to-amber-800/5 hover:from-amber-700/15 border-t-amber-600/30 dark:border-t-amber-600/10",
  };

  return (
    <div className="py-2">
      <div className="flex items-center gap-2 mb-6">
        <Trophy className="text-amber-500 animate-bounce" size={18} />
        <h3 className="text-sm font-semibold tracking-tight">Winners Podium</h3>
      </div>
      <div className="flex items-end justify-center gap-4">
        {order.map((p: FunnelPodiumEntry) => (
          <PodiumEntryCard
            key={p.rank}
            p={p}
            heights={heights}
            borderColors={borderColors}
            stepGradients={stepGradients}
            badgeGradients={badgeGradients}
          />
        ))}
      </div>
    </div>
  );
}

function ordinal(n: number): string {
  if (n === 1) return "1st";
  if (n === 2) return "2nd";
  if (n === 3) return "3rd";
  return `${n}th`;
}

/* ---------- Insights ---------- */
/* Based on the podium winners + field summary — NOT a re-list of the
 * finalists. Adds context the podium doesn't show: a production pick, how the
 * winners compare to the survivor field average, and a one-word trade-off tag
 * for each podium model. Only renders once the run is complete. */

function Insights({ rec }: { rec: FunnelRecommendation }) {
  const podium = rec.podium ?? [];
  const field = rec.field_summary;
  if (podium.length === 0) return null;

  // Production pick = 1st place (highest accuracy). If 2nd matches accuracy
  // within 2pp AND is cheaper, recommend the cheaper one as the value pick.
  const first = podium.find((p) => p.rank === 1) ?? podium[0];
  const second = podium.find((p) => p.rank === 2);
  let pick = first;
  let pickReason = "Highest accuracy among the finalists.";
  if (
    second &&
    Math.abs(first.accuracy - second.accuracy) < 0.02 &&
    (second.cost_per_call ?? 0) < (first.cost_per_call ?? Infinity)
  ) {
    pick = second;
    pickReason = "Matches the top accuracy at a lower cost per call.";
  }

  // Trade-off tags: which podium model is best at each axis.
  const cheapest = [...podium].sort((a, b) => (a.cost_per_call ?? 0) - (b.cost_per_call ?? 0))[0];
  const fastest = [...podium].sort((a, b) => (a.p95_latency_ms ?? 0) - (b.p95_latency_ms ?? 0))[0];
  const mostAccurate = [...podium].sort((a, b) => b.accuracy - a.accuracy)[0];
  const tagFor = (p: FunnelPodiumEntry): string[] => {
    const tags: string[] = [];
    if (p.rank === mostAccurate.rank) tags.push("best accuracy");
    if (p.rank === cheapest.rank) tags.push("cheapest");
    if (p.rank === fastest.rank) tags.push("fastest");
    return tags;
  };

  // Field context deltas (winners vs survivor average).
  const accDelta = field ? (first.accuracy - field.avg_accuracy) * 100 : null;
  const costRatio = field && field.avg_cost_per_call > 0 ? (first.cost_per_call ?? 0) / field.avg_cost_per_call : null;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="text-[var(--color-brand)]" size={18} />
        <h3 className="text-sm font-semibold tracking-tight">Insights & Recommendation</h3>
      </div>

      <div className="space-y-4">
        {/* Production pick */}
        <div className="relative rounded-xl border border-blue-500/20 bg-gradient-to-tr from-blue-500/5 to-indigo-500/5 p-4 shadow-sm overflow-hidden">
          <div className="absolute right-3 top-3 opacity-15">
            <Trophy size={48} className="text-blue-500" />
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
            ★ Recommended Production Pick
          </div>
          <div className="mt-2.5 font-mono text-sm font-bold text-[var(--color-foreground)]">
            {pick.slug}
          </div>
          <div className="mt-1 text-xs text-[var(--color-muted)] leading-relaxed">{pickReason}</div>
        </div>

        {/* Field context */}
        {field && field.survivors > 0 ? (
          <div className="text-xs leading-relaxed text-[var(--color-muted)] bg-[var(--color-surface-muted)] p-3 rounded-lg border border-[var(--color-border)]">
            📋 <span className="font-semibold text-[var(--color-foreground)]">{field.survivors}</span> finalists survived the pilot phase. 
            The winner outperformed the field average by{" "}
            <span className="font-bold text-[var(--color-foreground)]">{accDelta != null ? `${accDelta.toFixed(1)}pp` : "—"}</span>{" "}
            accuracy 
            {costRatio != null ? (
              <> at <span className="font-bold text-[var(--color-foreground)]">{costRatio.toFixed(1)}×</span> the average cost per call</>
            ) : null}
            .
          </div>
        ) : null}

        {/* Trade-off tags per podium model */}
        <div className="grid gap-3 sm:grid-cols-3">
          {podium.map((p) => {
            const tags = tagFor(p);
            return (
              <div key={p.rank} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3 transition-colors hover:bg-[var(--color-hover)]">
                <div className="text-[9px] font-bold uppercase tracking-wider text-[var(--color-muted)]">
                  {ordinal(p.rank)} Place
                </div>
                <div className="mt-1.5 truncate font-mono text-xs font-bold text-[var(--color-foreground)]" title={p.slug}>
                  {p.slug}
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {tags.map((t) => (
                    <span
                      key={t}
                      className="rounded-full bg-blue-500/10 dark:bg-blue-500/20 px-2.5 py-0.5 text-[9px] font-semibold text-blue-600 dark:text-blue-400 border border-blue-500/10"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

