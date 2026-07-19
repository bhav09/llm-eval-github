import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Gauge,
  History,
  Layers,
  Play,
  Square,
  Target,
  Zap,
} from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { CustomInputPanel } from "@/components/CustomInputPanel";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/primitives";
import { ProgressBar } from "@/components/ui/progress";
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from "@/components/ui/tabs";
import {
  DialogContent,
  DialogDescription,
  DialogRoot,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  api,
  IssueDetail,
  IssueRow,
  MetricsPayload,
  RunManifest,
  RunStatus,
} from "@/lib/api";
import { formatPct, formatUsd, msToSec, cn } from "@/lib/utils";

const LABELS = ["bug", "enhancement", "question", "documentation", "security", "other"];

const FALLBACK_MODELS = ["alibaba-qwen3-32b", "openai-gpt-oss-120b"];

export default function EvalPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [models, setModels] = useState<string[]>([]);
  const [modelA, setModelA] = useState(() => searchParams.get("modelA") ?? "");
  const [modelB, setModelB] = useState(() => searchParams.get("modelB") ?? "");
  const [manifest, setManifest] = useState<RunManifest | null>(null);
  const [selectedRunId, setSelectedRunId] = useState(() => searchParams.get("run") ?? "");
  const [metrics, setMetrics] = useState<MetricsPayload | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [_corpusCount, setCorpusCount] = useState(534);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issuePage, setIssuePage] = useState(0);
  const [disagreementOnly, setDisagreementOnly] = useState(false);
  const [issues, setIssues] = useState<IssueRow[]>([]);
  const [issueTotal, setIssueTotal] = useState(0);
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [sampleSize, setSampleSize] = useState<number | undefined>(5);
  const useMock = false;
  const [cancelling, setCancelling] = useState(false);

  const modelOptions = useMemo(
    () => (models.length > 0 ? models : FALLBACK_MODELS),
    [models],
  );

  const selectedRun = manifest?.run_id === selectedRunId ? manifest : null;

  const selectRun = useCallback(
    (runId: string) => {
      setSelectedRunId(runId);
      if (runId) {
        setSearchParams({ run: runId });
      } else {
        setSearchParams({});
      }
    },
    [setSearchParams],
  );

  const refreshBootstrap = useCallback(async () => {
    const [recs, stats] = await Promise.all([
      api.recommendations(),
      api.corpusStats(),
    ]);
    setCorpusCount(stats.count);
    // Use recommended models if set, otherwise fall back to the first two
    // available models so the dropdowns are never empty.
    if (!modelA) setModelA(recs.model_a || FALLBACK_MODELS[0]);
    if (!modelB) setModelB(recs.model_b || FALLBACK_MODELS[1]);
  }, [modelA, modelB]);

  const refreshModels = useCallback(async () => {
    try {
      const { models: modelList } = await api.models();
      const slugs = modelList.map((m) => m.slug);
      setModels(slugs.length > 0 ? slugs : FALLBACK_MODELS);
    } catch {
      setModels(FALLBACK_MODELS);
    }
  }, []);

  useEffect(() => {
    refreshModels().catch(console.error);
    refreshBootstrap().catch(console.error);
  }, [refreshModels, refreshBootstrap]);

  useEffect(() => {
    const runParam = searchParams.get("run");
    if (runParam && runParam !== selectedRunId) {
      setSelectedRunId(runParam);
    }
  }, [searchParams, selectedRunId]);

  useEffect(() => {
    const pA = searchParams.get("modelA");
    const pB = searchParams.get("modelB");
    if (pA) setModelA(pA);
    if (pB) setModelB(pB);
  }, [searchParams]);

  useEffect(() => {
    if (!selectedRunId) {
      setManifest(null);
      setMetrics(null);
      setStatus(null);
      return;
    }
    api
      .run(selectedRunId)
      .then((payload) => {
        setManifest(payload.manifest);
        // Only set metrics if non-null — a stale response from when the run
        // was still in progress would otherwise clobber metrics loaded by the
        // complete effect (race condition on fast/mock runs).
        if (payload.metrics) setMetrics(payload.metrics);
      })
      .catch(() => {
        setManifest(null);
      });
    api
      .status(selectedRunId)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) return;
    const params = new URLSearchParams({
      offset: String(issuePage * 50),
      limit: "50",
      disagreement_only: String(disagreementOnly),
    });
    api.issues(selectedRunId, params).then((payload) => {
      setIssues(payload.items);
      setIssueTotal(payload.total);
    });
  }, [selectedRunId, issuePage, disagreementOnly]);

  useEffect(() => {
    if (!selectedRunId || status?.status !== "running") return;
    const timer = setInterval(() => {
      api.status(selectedRunId).then(setStatus).catch(console.error);
    }, 2000);
    return () => clearInterval(timer);
  }, [selectedRunId, status?.status]);

  useEffect(() => {
    const done = status?.status === "complete" || status?.status === "aborted";
    if (!done || !selectedRunId) return;
    api.metrics(selectedRunId).then(setMetrics).catch(console.error);
    api.run(selectedRunId).then((payload) => setManifest(payload.manifest)).catch(console.error);
  }, [status?.status, selectedRunId]);

  async function startRun() {
    setLoading(true);
    setError(null);
    try {
      const runManifest = await api.startRun({
        model_a: modelA,
        model_b: modelB,
        limit: sampleSize,
        use_mock: useMock,
        confirm_spend: !useMock,
      });
      selectRun(runManifest.run_id);
      setStatus({
        run_id: runManifest.run_id,
        status: "running",
        completed: 0,
        total: runManifest.total,
        failed: 0,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setLoading(false);
    }
  }

  async function cancelRun() {
    if (!selectedRunId) return;
    setCancelling(true);
    try {
      await api.cancelRun(selectedRunId);
      // The backend drains in-flight calls, writes partial metrics, and marks
      // the run aborted. Poll status once to reflect the change promptly.
      const fresh = await api.status(selectedRunId);
      setStatus(fresh);
      if (fresh.status === "complete" || fresh.status === "aborted") {
        const payload = await api.run(selectedRunId);
        if (payload.metrics) setMetrics(payload.metrics);
        setManifest(payload.manifest);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel run");
    } finally {
      setCancelling(false);
    }
  }

  const progressPct = status?.total
    ? Math.min(100, ((status.completed || 0) / status.total) * 100)
    : 0;

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {selectedRunId ? (
            <button
              type="button"
              onClick={() => selectRun("")}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm font-medium text-[var(--color-foreground)] transition-colors hover:bg-[var(--color-surface-muted)]"
            >
              <ArrowLeft size={16} />
              New run
            </button>
          ) : null}
          <div>
            <h2 className="text-2xl font-black tracking-tight text-[var(--color-foreground)]">
              {selectedRunId ? "Run Results" : "Eval"}
            </h2>
            <p className="text-sm text-[var(--color-muted)] leading-relaxed">
              {selectedRunId
                ? `${selectedRun?.model_a ?? modelA} vs ${selectedRun?.model_b ?? modelB}`
                : "Compare two models head-to-head on a stratified issue sample — inspect accuracy, F1, confusion matrices, and per-issue disagreements."}
            </p>
          </div>
        </div>
        <Link
          to="/history"
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-foreground)] transition-colors hover:bg-[var(--color-surface-muted)]"
        >
          <History size={13} />
          History
        </Link>
      </div>

      {metrics && selectedRun ? null : (
        <Card className="border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
          <CardContent className="space-y-4 py-5 px-6">
            <div className="grid gap-4 md:grid-cols-3">
            <label className="text-xs font-semibold tracking-wide text-[var(--color-muted)]">
              <span className="mb-1.5 block">Model A</span>
              <select
                className="h-10 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3.5 text-sm text-[var(--color-foreground)] shadow-sm hover:border-[var(--color-brand)]/50 focus:border-[var(--color-brand)] transition-all duration-200 cursor-pointer"
                value={modelA}
                onChange={(e) => setModelA(e.target.value)}
              >
                {modelOptions.map((slug) => (
                  <option key={slug} value={slug}>
                    {slug}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold tracking-wide text-[var(--color-muted)]">
              <span className="mb-1.5 block">Model B</span>
              <select
                className="h-10 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3.5 text-sm text-[var(--color-foreground)] shadow-sm hover:border-[var(--color-brand)]/50 focus:border-[var(--color-brand)] transition-all duration-200 cursor-pointer"
                value={modelB}
                onChange={(e) => setModelB(e.target.value)}
              >
                {modelOptions.map((slug) => (
                  <option key={slug} value={slug}>
                    {slug}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold tracking-wide text-[var(--color-muted)]">
              <span className="mb-1.5 block">Sample size</span>
              <select
                className="h-10 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3.5 text-sm text-[var(--color-foreground)] shadow-sm hover:border-[var(--color-brand)]/50 focus:border-[var(--color-brand)] transition-all duration-200 cursor-pointer"
                value={sampleSize ?? 5}
                onChange={(e) => setSampleSize(Number(e.target.value))}
              >
                <option value="5">5 issues</option>
                <option value="10">10 issues</option>
                <option value="20">20 issues</option>
              </select>
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={startRun} disabled={loading || status?.status === "running"}>
              <Play size={14} className="mr-2" />
              {loading ? "Starting…" : "Run"}
            </Button>
            {status?.status === "running" ? (
              <Button variant="outline" onClick={cancelRun} disabled={cancelling}>
                <Square size={14} className="mr-2" />
                {cancelling ? "Stopping…" : "Stop"}
              </Button>
            ) : null}
            {error ? <span className="text-xs text-red-600 dark:text-red-400">{error}</span> : null}
          </div>
          {status?.status === "running" ? (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3">
              <div className="mb-2 flex items-center justify-between text-xs text-[var(--color-foreground)]">
                <span>
                  {status.completed}/{status.total}
                </span>
                <span>
                  {status.rps ? `${status.rps} req/s` : ""}
                  {status.eta_sec ? ` · ETA ${status.eta_sec}s` : ""}
                </span>
              </div>
              <ProgressBar value={progressPct} />
            </div>
          ) : null}
        </CardContent>
      </Card>
      )}

      {metrics && selectedRun ? null : (
        <CustomInputPanel modelA={modelA} modelB={modelB} />
      )}

      {metrics && selectedRun ? (
        <TabsRoot defaultValue="scored">
          <TabsList>
            <TabsTrigger value="scored">Scored</TabsTrigger>
            <TabsTrigger value="unscored">Unscored</TabsTrigger>
            <TabsTrigger value="ops">Ops</TabsTrigger>
          </TabsList>

          <TabsContent value="scored">
            <div className="grid gap-4 md:grid-cols-4">
              <StatCard
                title="Model A accuracy"
                value={formatPct(metrics.model_a.scored.accuracy)}
                hint={selectedRun.model_a}
                icon={Target}
              />
              <StatCard
                title="Model B accuracy"
                value={formatPct(metrics.model_b.scored.accuracy)}
                hint={selectedRun.model_b}
                icon={Target}
                accent="emerald"
              />
              <StatCard
                title="Macro F1 (A / B)"
                value={`${metrics.model_a.scored.macro_f1.toFixed(3)} / ${metrics.model_b.scored.macro_f1.toFixed(3)}`}
                icon={BarChart3}
                accent="amber"
              />
              <StatCard
                title="Scored issues"
                value={String(metrics.model_a.scored.count)}
                icon={Layers}
                accent="slate"
              />
            </div>
            {metrics.model_a.scored.count === 0 ? (
              <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-400">
                <strong>No issues scored successfully.</strong> Every classified
                issue has a ground-truth label, so a 0 here means all inference
                calls failed (check the Ops tab for the error breakdown) or the
                ground-truth file is missing.
              </div>
            ) : null}
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <MetricsTable title={`${selectedRun.model_a} per-class`} model={metrics.model_a} />
              <MetricsTable title={`${selectedRun.model_b} per-class`} model={metrics.model_b} />
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <ConfusionMatrixCard
                title={`${selectedRun.model_a} confusion matrix`}
                matrix={metrics.model_a.scored.confusion_matrix}
                labels={LABELS}
              />
              <ConfusionMatrixCard
                title={`${selectedRun.model_b} confusion matrix`}
                matrix={metrics.model_b.scored.confusion_matrix}
                labels={LABELS}
              />
            </div>
            <Card className="mt-4 border-[var(--color-border)] bg-[var(--color-surface)]">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-[var(--color-foreground)]">
                    Disagreements with ground truth
                  </CardTitle>
                  <CardDescription>Sample from scored-set drill-down</CardDescription>
                </div>
                <a
                  className="text-sm text-[var(--color-brand)] hover:underline"
                  href={`/api/runs/${selectedRunId}/disagreements/export`}
                >
                  Export CSV
                </a>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
                      <th className="py-2 pr-4">Issue</th>
                      <th className="py-2 pr-4">Model A</th>
                      <th className="py-2 pr-4">Model B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.comparison.disagreements.slice(0, 10).map((row) => (
                      <tr key={row.issue_id} className="border-b border-[var(--color-border)]">
                        <td className="py-2 pr-4 font-mono text-xs text-[var(--color-foreground)]">
                          {row.issue_id.split("#")[1]}
                        </td>
                        <td className="py-2 pr-4 text-[var(--color-foreground)]">{row.model_a_label}</td>
                        <td className="py-2 pr-4 text-[var(--color-foreground)]">{row.model_b_label}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="unscored">
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard
                title="Agreement rate"
                value={formatPct(metrics.comparison.agreement_rate)}
                hint={`${metrics.comparison.disagreement_count} disagreements`}
                icon={Activity}
              />
              <DistributionCard title="Model A distribution" data={metrics.model_a.label_distribution} />
              <DistributionCard title="Model B distribution" data={metrics.model_b.label_distribution} />
            </div>
            <IssueTable
              issues={issues}
              total={issueTotal}
              page={issuePage}
              disagreementOnly={disagreementOnly}
              onPageChange={setIssuePage}
              onToggleDisagreement={setDisagreementOnly}
              onOpenIssue={async (issueId) => {
                const payload = await api.issueDetail(selectedRunId, issueId);
                setDetail(payload);
              }}
            />
          </TabsContent>

          <TabsContent value="ops">
            <WinnerCard
              modelA={selectedRun.model_a}
              modelB={selectedRun.model_b}
              metrics={metrics}
            />
            <div className="mt-4 grid gap-4 md:grid-cols-4">
              <StatCard
                title="Cost / call (A)"
                value={formatUsd(metrics.model_a.cost_usd.per_call)}
                hint={`Total ${formatUsd(metrics.model_a.cost_usd.total)}`}
                icon={Gauge}
              />
              <StatCard
                title="Cost / call (B)"
                value={formatUsd(metrics.model_b.cost_usd.per_call)}
                hint={`Total ${formatUsd(metrics.model_b.cost_usd.total)}`}
                icon={Gauge}
                accent="emerald"
              />
              <StatCard
                title="Cache hit (A / B)"
                value={`${formatPct(metrics.model_a.cache.hit_rate)} / ${formatPct(metrics.model_b.cache.hit_rate)}`}
                hint="Prefix cache per model"
                icon={Zap}
                accent="amber"
              />
              <StatCard
                title="p95 latency (A / B)"
                value={`${msToSec(metrics.model_a.latency_ms.p95)} / ${msToSec(metrics.model_b.latency_ms.p95)}`}
                hint={`Concurrency ${selectedRun.concurrency}`}
                icon={Activity}
                accent="slate"
              />
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <OpsPanel title={selectedRun.model_a} model={metrics.model_a} />
              <OpsPanel title={selectedRun.model_b} model={metrics.model_b} />
            </div>
          </TabsContent>
        </TabsRoot>
      ) : (
        <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
          <CardContent className="py-12 text-center">
            {selectedRunId ? (
              <div className="space-y-1">
                <p className="text-sm font-medium text-[var(--color-foreground)]">
                  {status?.status === "running"
                    ? "Run in progress…"
                    : "Metrics not ready yet."}
                </p>
                <p className="text-sm text-[var(--color-muted)]">
                  {status?.status === "running"
                    ? `${status.completed}/${status.total} completed`
                    : "Try refreshing in a moment."}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-medium text-[var(--color-foreground)]">
                  No run selected
                </p>
                <p className="text-sm text-[var(--color-muted)]">
                  Configure models above and click <span className="font-medium">Run comparison</span>, or open a past run from{" "}
                  <Link to="/history" className="text-[var(--color-brand)] hover:underline">
                    Run history
                  </Link>
                  .
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <DialogRoot open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="border-[var(--color-border)] bg-[var(--color-surface)]">
          {detail ? (
            <>
              <DialogTitle className="text-[var(--color-foreground)]">{detail.title}</DialogTitle>
              <DialogDescription>{detail.issue_id}</DialogDescription>
              <div className="mt-4 space-y-3 text-sm">
                <p className="text-[var(--color-muted)]">{detail.body_snippet}</p>
                <p className="text-[var(--color-foreground)]">
                  Ground truth:{" "}
                  <Badge variant={detail.in_scored_set ? "success" : "muted"}>
                    {detail.ground_truth ?? "unscored"}
                  </Badge>
                </p>
                <div className="grid gap-2 md:grid-cols-2">
                  {[detail.model_a, detail.model_b].map((model) => (
                    <div
                      key={model}
                      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3"
                    >
                      <p className="font-medium text-[var(--color-foreground)]">{model}</p>
                      <p className="text-[var(--color-muted)]">
                        {(detail.predictions[model]?.predicted_label as string) ?? "—"}
                      </p>
                    </div>
                  ))}
                </div>
                <a
                  className="text-[var(--color-brand)] hover:underline"
                  href={detail.html_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  View on GitHub
                </a>
              </div>
            </>
          ) : null}
        </DialogContent>
      </DialogRoot>
    </main>
  );
}

function MetricsTable({ title, model }: { title: string; model: MetricsPayload["model_a"] }) {
  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
      <CardHeader>
        <CardTitle className="text-[var(--color-foreground)]">{title}</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
              <th className="py-2 pr-3">Label</th>
              <th className="py-2 pr-3">P</th>
              <th className="py-2 pr-3">R</th>
              <th className="py-2 pr-3">F1</th>
            </tr>
          </thead>
          <tbody>
            {LABELS.map((label) => (
              <tr key={label} className="border-b border-[var(--color-border)]">
                <td className="py-2 pr-3 text-[var(--color-foreground)]">{label}</td>
                <td className="py-2 pr-3 text-[var(--color-foreground)]">
                  {model.scored.per_class[label]?.precision.toFixed(3) ?? "—"}
                </td>
                <td className="py-2 pr-3 text-[var(--color-foreground)]">
                  {model.scored.per_class[label]?.recall.toFixed(3) ?? "—"}
                </td>
                <td className="py-2 pr-3 text-[var(--color-foreground)]">
                  {model.scored.per_class[label]?.f1.toFixed(3) ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function WinnerCard({
  modelA,
  modelB,
  metrics,
}: {
  modelA: string;
  modelB: string;
  metrics: MetricsPayload;
}) {
  const benchmarks: Array<{
    name: string;
    a: number;
    b: number;
    higherBetter: boolean;
    fmt: (v: number) => string;
  }> = [
    { name: "Accuracy", a: metrics.model_a.scored.accuracy, b: metrics.model_b.scored.accuracy, higherBetter: true, fmt: formatPct },
    { name: "Macro F1", a: metrics.model_a.scored.macro_f1, b: metrics.model_b.scored.macro_f1, higherBetter: true, fmt: (v) => v.toFixed(3) },
    { name: "Cost / call", a: metrics.model_a.cost_usd.per_call, b: metrics.model_b.cost_usd.per_call, higherBetter: false, fmt: formatUsd },
    { name: "p95 latency", a: metrics.model_a.latency_ms.p95, b: metrics.model_b.latency_ms.p95, higherBetter: false, fmt: msToSec },
    { name: "Cache hit", a: metrics.model_a.cache.hit_rate, b: metrics.model_b.cache.hit_rate, higherBetter: true, fmt: formatPct },
  ];
  const winsA = benchmarks.filter((b) => (b.higherBetter ? b.a > b.b : b.a < b.b)).length;
  const winsB = benchmarks.filter((b) => (b.higherBetter ? b.b > b.a : b.b < b.a)).length;
  const overall = winsA === winsB ? "Tie" : winsA > winsB ? modelA : modelB;
  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
      <CardHeader className="pb-4 border-b border-[var(--color-border)]">
        <CardTitle className="flex justify-between items-center text-sm font-semibold text-[var(--color-foreground)]">
          <span>Benchmark Comparisons</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
            Winner: {overall === "Tie" ? "Tie" : `${overall.slice(0, 18)}…`} ({winsA}–{winsB})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        {benchmarks.map((b) => {
          const aWins = b.higherBetter ? b.a > b.b : b.a < b.b;
          const bWins = b.higherBetter ? b.b > b.a : b.b < b.a;
          const tie = b.a === b.b;

          // Determine relative widths (capped to ensure minimum render width of 5%)
          const maxVal = Math.max(b.a, b.b, 0.0001);
          const aPct = Math.max(5, (b.a / maxVal) * 100);
          const bPct = Math.max(5, (b.b / maxVal) * 100);

          return (
            <div key={b.name} className="space-y-1.5 border-b border-[var(--color-border)]/50 pb-3 last:border-b-0 last:pb-0">
              <div className="flex justify-between items-center text-xs">
                <span className="font-bold text-[var(--color-foreground)]">{b.name}</span>
                <span className="text-[10px] bg-[var(--color-hover)] px-2 py-0.5 rounded-full font-bold uppercase text-[var(--color-muted)]">
                  {tie ? "Tie" : aWins ? "A Wins" : "B Wins"}
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-4 items-center">
                {/* Model A Bar */}
                <div className="space-y-1 text-left">
                  <div className="flex justify-between items-baseline text-[9px] text-[var(--color-muted)]">
                    <span className="truncate max-w-[80px] font-mono" title={modelA}>{modelA}</span>
                    <span className={cn("font-mono font-bold", aWins && !tie ? "text-[var(--color-brand)] text-[10px]" : "")}>{b.fmt(b.a)}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-[var(--color-surface-muted)] dark:bg-slate-900 overflow-hidden border border-[var(--color-border)]">
                    <div 
                      style={{ width: `${aPct}%` }} 
                      className={cn("h-full rounded-full transition-all duration-500", aWins && !tie ? "bg-gradient-to-r from-blue-500 to-indigo-500" : "bg-slate-400 dark:bg-slate-600")}
                    />
                  </div>
                </div>

                {/* Model B Bar */}
                <div className="space-y-1 text-left">
                  <div className="flex justify-between items-baseline text-[9px] text-[var(--color-muted)]">
                    <span className="truncate max-w-[80px] font-mono" title={modelB}>{modelB}</span>
                    <span className={cn("font-mono font-bold", bWins && !tie ? "text-[#4f46e5] text-[10px]" : "")}>{b.fmt(b.b)}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-[var(--color-surface-muted)] dark:bg-slate-900 overflow-hidden border border-[var(--color-border)]">
                    <div 
                      style={{ width: `${bPct}%` }} 
                      className={cn("h-full rounded-full transition-all duration-500", bWins && !tie ? "bg-gradient-to-r from-[#4f46e5] to-purple-600" : "bg-slate-400 dark:bg-slate-600")}
                    />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function ConfusionMatrixCard({
  title,
  matrix,
  labels,
}: {
  title: string;
  matrix: Record<string, Record<string, number>>;
  labels: string[];
}) {
  const present = labels.filter((label) => {
    const rowActive = matrix[label] && Object.values(matrix[label]).some((v) => v > 0);
    const colActive = labels.some((other) => (matrix[other]?.[label] ?? 0) > 0);
    return rowActive || colActive;
  });
  const max = Math.max(1, ...present.flatMap((r) => present.map((c) => matrix[r]?.[c] ?? 0)));
  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
      <CardHeader>
        <CardTitle className="text-[var(--color-foreground)]">{title}</CardTitle>
        <CardDescription>Rows = ground truth, columns = predicted</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {present.length === 0 ? (
          <p className="text-sm text-[var(--color-muted)]">No scored predictions yet.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)] text-xs">
                <th className="py-2.5 pr-3 font-semibold">↓ truth / pred →</th>
                {present.map((label) => (
                  <th key={label} className="py-2.5 pr-3 text-right font-mono font-semibold">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {present.map((truth) => (
                <tr key={truth} className="border-b border-[var(--color-border)]/40 last:border-b-0">
                  <td className="py-2.5 pr-3 font-semibold text-[var(--color-foreground)] text-xs">{truth}</td>
                  {present.map((pred) => {
                    const value = matrix[truth]?.[pred] ?? 0;
                    const isDiagonal = truth === pred;
                    const intensity = value / max;
                    const bg = value === 0
                      ? "transparent"
                      : isDiagonal
                        ? `rgba(16, 185, 129, ${0.12 + intensity * 0.58})`
                        : `rgba(245, 158, 11, ${0.08 + intensity * 0.58})`;
                    
                    return (
                      <td
                        key={pred}
                        className={cn(
                          "py-2.5 pr-3 text-right font-mono text-xs font-bold transition-all duration-200 hover:scale-[1.08] hover:shadow-sm cursor-help",
                          value > 0 ? "rounded-[4px] border border-white/5" : ""
                        )}
                        style={{ backgroundColor: bg }}
                        title={`${truth} → ${pred}: ${value}`}
                      >
                        {value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function DistributionCard({ title, data }: { title: string; data: Record<string, number> }) {
  const max = Math.max(...Object.values(data), 1);
  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
      <CardHeader>
        <CardTitle className="text-[var(--color-foreground)]">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {LABELS.map((label) => (
          <div key={label}>
            <div className="mb-1 flex justify-between text-xs text-[var(--color-muted)]">
              <span>{label}</span>
              <span>{data[label] ?? 0}</span>
            </div>
            <div className="h-2 rounded-full bg-[var(--color-surface-muted)]">
              <div
                className="h-2 rounded-full bg-[var(--color-brand)]"
                style={{ width: `${((data[label] ?? 0) / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function OpsPanel({ title, model }: { title: string; model: MetricsPayload["model_a"] }) {
  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
      <CardHeader>
        <CardTitle className="text-[var(--color-foreground)]">{title}</CardTitle>
        <CardDescription>Operational metrics</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Cache savings" value={formatUsd(model.cost_usd.cache_savings_total)} />
        <Row label="Failed requests" value={String(model.failed_count)} />
        <Row
          label="p50 / p95 / p99"
          value={`${msToSec(model.latency_ms.p50)} / ${msToSec(model.latency_ms.p95)} / ${msToSec(model.latency_ms.p99)}`}
        />
        <div className="pt-2">
          <p className="mb-1 text-[var(--color-muted)]">Errors</p>
          {Object.entries(model.error_breakdown).length ? (
            Object.entries(model.error_breakdown).map(([key, value]) => (
              <Row key={key} label={key} value={String(value)} />
            ))
          ) : (
            <p className="text-[var(--color-muted)]">None</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-[var(--color-border)] py-1.5">
      <span className="text-[var(--color-muted)]">{label}</span>
      <span className="font-medium text-[var(--color-foreground)]">{value}</span>
    </div>
  );
}

function IssueTable({
  issues,
  total,
  page,
  disagreementOnly,
  onPageChange,
  onToggleDisagreement,
  onOpenIssue,
}: {
  issues: IssueRow[];
  total: number;
  page: number;
  disagreementOnly: boolean;
  onPageChange: (page: number) => void;
  onToggleDisagreement: (value: boolean) => void;
  onOpenIssue: (issueId: string) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / 50));
  return (
    <Card className="mt-4 border-[var(--color-border)] bg-[var(--color-surface)]">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div>
          <CardTitle className="text-[var(--color-foreground)]">Issue predictions</CardTitle>
          <CardDescription>Paginated corpus view</CardDescription>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--color-muted)]">
          <input
            type="checkbox"
            checked={disagreementOnly}
            onChange={(e) => {
              onToggleDisagreement(e.target.checked);
              onPageChange(0);
            }}
          />
          Disagreements only
        </label>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
              <th className="py-2 pr-4">Issue</th>
              <th className="py-2 pr-4">Model A</th>
              <th className="py-2 pr-4">Model B</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((row) => (
              <tr
                key={row.issue_id}
                className="cursor-pointer border-b border-[var(--color-border)] hover:bg-[var(--color-surface-muted)]"
                onClick={() => onOpenIssue(row.issue_id)}
              >
                <td className="py-2 pr-4 font-mono text-xs text-[var(--color-foreground)]">
                  {row.issue_id.split("#")[1]}
                </td>
                <td className="py-2 pr-4 text-[var(--color-foreground)]">
                  {row.label_a ?? (
                    <span className="text-amber-600 dark:text-amber-400" title="Inference failed or was cancelled">
                      {row.status_a === "error" ? "failed" : row.status_a ?? "—"}
                    </span>
                  )}
                </td>
                <td className="py-2 pr-4 text-[var(--color-foreground)]">
                  {row.label_b ?? (
                    <span className="text-amber-600 dark:text-amber-400" title="Inference failed or was cancelled">
                      {row.status_b === "error" ? "failed" : row.status_b ?? "—"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex items-center justify-between text-sm text-[var(--color-muted)]">
          <span>
            Page {page + 1} of {pages} · {total} issues
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => onPageChange(page - 1)}>
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= pages}
              onClick={() => onPageChange(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
