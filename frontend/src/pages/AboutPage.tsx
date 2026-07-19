export function AboutPage() {
  const sections = [
    {
      title: "What is Colosseum?",
      body: "Colosseum is an automated LLM evaluation harness built to recommend the best open-weight production model from the DigitalOcean Serverless Inference catalog. It classifies GitHub issues from the digitalocean/doctl repository into six customer-facing labels (bug, enhancement, question, documentation, security, other) and uses a multi-stage funnel to surface a ranked podium of production candidates — entirely data-driven, not hand-picked.",
    },
    {
      title: "Why the name?",
      body: "The model-selection funnel pits open-weight models against each other in a staged arena — pilot round, full evaluation, multi-criteria ranking — narrowing the field from an initial pool of candidates down to a 1st/2nd/3rd podium. Like the Roman Colosseum, only the strongest survive.",
    },
    {
      title: "Ground Truth Pipeline",
      body: "Labels are produced by a three-stage hybrid pipeline. First, a rules engine classifies ~60-70% of issues at HIGH confidence using native GitHub labels and title/body heuristics. Ambiguous or conflicting matches are forwarded to an LLM adjudicator (deepseek-v4-pro — a frontier model excluded from the evaluation pool to prevent circular trust). Long issue bodies are middle-truncated so both the user description and stack trace ends are preserved. Finally, a stratified human calibration sample validates rules and LLM quality without requiring a full relabeling pass.",
    },
    {
      title: "4-Stage Selection Funnel",
      body: "Stage 1 (Stratified Select) fetches the live /v1/models catalog and picks 6 representative open-weight candidates across size/reasoning tiers. Stage 2 (Pilot) runs all 6 on 5 random issues and scores each on a weighted composite readiness score — accuracy 30%, latency 20%, cost 20%, throughput 15%, reliability 15% — disqualifying models above a 40% failure threshold. Stage 3 (Full Eval) runs survivors on 10 issues (reusing pilot predictions) for deeper metrics. Stage 4 (Recommend) emits a podium ranked by composite score plus two production picks — best value and highest accuracy.",
    },
    {
      title: "Head-to-Head Eval",
      body: "The Eval page lets you compare any two models directly on a stratified sample of 5, 10, or 20 issues. It renders per-class precision/recall/F1, confusion matrices, and a disagreement browser so you can drill into exactly where the models diverge. The Eval page defaults its dropdowns to the funnel's recommended pair when a selection run exists.",
    },
    {
      title: "Design Choices",
      body: "One issue = one API call (hard constraint). Identical system prompt across all requests enables prefix caching for ~533/534 cache hits after warmup. Shared context truncation with smart middle-split preserves tracebacks. Checkpoint/resume every 50 issues means a crash never restarts from zero. SQLite + JSONL artifacts keep results auditable and reviewer-friendly. The open-weight-only filter for the funnel ensures closed-source and embedding models are excluded from benchmarking. Idempotent funnel IDs in the URL make runs shareable and reloadable.",
    },
    {
      title: "Scale Path",
      body: "The harness is designed to scale from the current ~534-issue corpus to 5k-50k issues without a rewrite. The corpus is partitioned, runs checkpoint every N issues, streaming metrics accumulate in-flight, and the UI paginates. The selection funnel's 45-60 API call budget (vs ~900 for a naive full-catalog eval) grows sub-linearly with catalog size.",
    },
  ];

  const stack = [
    { label: "Backend", value: "FastAPI + Python 3.12, asyncio, SQLite, JSONL" },
    { label: "Frontend", value: "React 18 + TypeScript, Vite, Tailwind CSS" },
    { label: "Inference", value: "DigitalOcean Serverless Inference API (OpenAI-compatible)" },
    { label: "Ground Truth", value: "Rules engine + deepseek-v4-pro adjudicator + human calibration" },
    { label: "Deployment", value: "Dockerfile (multi-stage: Vite build → Python runtime), DO App Platform" },
  ];

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      {/* Page header */}
      <div className="mb-10 space-y-2 border-b border-[var(--color-border)] pb-8">
        <h2 className="text-2xl font-black tracking-tight text-[var(--color-foreground)]">About</h2>
        <p className="text-sm text-[var(--color-muted)] leading-relaxed max-w-2xl">
          Colosseum compares multiple open-weight models side-by-side to recommend the best production deployments based on accuracy, cost, latency, throughput, and operational reliability.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        {/* Left: Main content */}
        <div className="lg:col-span-2 space-y-8">
          {sections.map((s) => (
            <div key={s.title} className="space-y-2">
              <h3 className="text-base font-bold text-[var(--color-foreground)]">{s.title}</h3>
              <p className="text-sm text-[var(--color-muted)] leading-relaxed">{s.body}</p>
            </div>
          ))}
        </div>

        {/* Right: Tech stack sidebar */}
        <div className="space-y-6">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5 shadow-sm space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Tech Stack</h3>
            <div className="space-y-3">
              {stack.map((item) => (
                <div key={item.label}>
                  <div className="text-xs font-semibold text-[var(--color-foreground)]">{item.label}</div>
                  <div className="text-[11px] text-[var(--color-muted)] leading-relaxed mt-0.5">{item.value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5 shadow-sm space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Label Taxonomy</h3>
            {[
              { label: "bug", color: "bg-red-500/10 text-red-500", desc: "Crashes, panics, incorrect behavior" },
              { label: "enhancement", color: "bg-blue-500/10 text-blue-500", desc: "Features, optimizations, new flags" },
              { label: "question", color: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400", desc: "Usage help, config queries" },
              { label: "documentation", color: "bg-purple-500/10 text-purple-500", desc: "Typos, missing guides, inline docs" },
              { label: "security", color: "bg-orange-500/10 text-orange-500", desc: "CVEs, credential leaks, TLS issues" },
              { label: "other", color: "bg-[var(--color-surface-muted)] text-[var(--color-muted)]", desc: "Duplicates, CI/CD, admin tasks" },
            ].map((item) => (
              <div key={item.label} className="flex items-start gap-2.5">
                <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${item.color}`}>
                  {item.label}
                </span>
                <span className="text-[11px] text-[var(--color-muted)] leading-relaxed">{item.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
