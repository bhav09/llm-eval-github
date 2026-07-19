export type RunManifest = {
  run_id: string;
  status: string;
  model_a: string;
  model_b: string;
  completed: number;
  total: number;
  failed: number;
  concurrency: number;
  started_at?: string;
  finished_at?: string;
  sampled_issue_ids?: string[];
};

export type RunStatus = {
  run_id: string;
  status: string;
  completed: number;
  total: number;
  failed: number;
  rps?: number | null;
  eta_sec?: number | null;
  error?: string | null;
};

export type MetricsPayload = {
  model_a: ModelMetrics;
  model_b: ModelMetrics;
  comparison: {
    agreement_rate: number;
    disagreement_count: number;
    disagreements: Array<{
      issue_id: string;
      model_a_label: string;
      model_b_label: string;
    }>;
  };
};

export type ModelMetrics = {
  model: string;
  total_calls: number;
  ok_count: number;
  scored: {
    accuracy: number;
    macro_f1: number;
    per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
    confusion_matrix: Record<string, Record<string, number>>;
    count: number;
  };
  cost_usd: { total: number; per_call: number; cache_savings_total: number };
  latency_ms: { p50: number; p95: number; p99: number };
  cache: { hit_rate: number; cached_tokens: number; prompt_tokens: number };
  label_distribution: Record<string, number>;
  error_breakdown: Record<string, number>;
  failed_count: number;
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json();
}

export const api = {
  config: () => fetchJson<{ concurrency: number }>("/api/config"),
  models: () => fetchJson<{ models: Array<{ slug: string; tier: string; cache_supported: boolean }> }>("/api/models"),
  recommendations: () =>
    fetchJson<{ model_a: string; model_b: string; rationale: string }>("/api/recommendations"),
  runs: (limit = 20) => fetchJson<{ runs: RunManifest[] }>(`/api/runs?limit=${limit}`),
  run: (id: string) =>
    fetchJson<{ manifest: RunManifest; metrics: MetricsPayload | null; prediction_count: number }>(
      `/api/runs/${id}`,
    ),
  status: (id: string) => fetchJson<RunStatus>(`/api/runs/${id}/status`),
  metrics: (id: string) => fetchJson<MetricsPayload>(`/api/runs/${id}/metrics`),
  issues: (id: string, params: URLSearchParams) =>
    fetchJson<{ items: IssueRow[]; total: number }>(`/api/runs/${id}/issues?${params}`),
  issueDetail: (runId: string, issueId: string) => fetchJson<IssueDetail>(`/api/runs/${runId}/issues/${issueId}`),
  startRun: (body: {
    model_a: string;
    model_b: string;
    limit?: number;
    use_mock?: boolean;
    confirm_spend?: boolean;
    concurrency?: number;
    request_timeout_sec?: number;
    max_retries?: number;
  }) =>
    fetchJson<RunManifest>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelRun: (id: string) =>
    fetchJson<{ run_id: string; status: string }>(`/api/runs/${id}/cancel`, {
      method: "POST",
    }),
  startFunnel: (body: {
    use_mock?: boolean;
    confirm_spend?: boolean;
    concurrency?: number;
    adjudicator_model?: string;
    pilot_issue_count?: number;
    full_issue_count?: number;
    error_rate_elim?: number;
    invalid_rate_elim?: number;
    request_timeout_sec?: number;
    max_retries?: number;
  }) =>
    fetchJson<FunnelRun>("/api/funnel/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  funnels: (limit = 10) => fetchJson<{ funnels: FunnelRun[] }>(`/api/funnel?limit=${limit}`),
  funnel: (id: string) => fetchJson<FunnelRun>(`/api/funnel/${id}`),
  funnelStatus: (id: string) => fetchJson<FunnelStatus>(`/api/funnel/${id}/status`),
  cancelFunnel: (id: string) =>
    fetchJson<{ funnel_id: string; status: string }>(`/api/funnel/${id}/cancel`, {
      method: "POST",
    }),
  corpusStats: () => fetchJson<{ count: number; version: number }>("/api/corpus/stats"),
  classifyCustom: (body: {
    title: string;
    body: string;
    model_a: string;
    model_b: string;
    use_mock?: boolean;
  }) =>
    fetchJson<CustomClassifyResult>("/api/classify/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};

export type CustomClassifyModelResult = {
  model: string;
  predicted_label: string | null;
  raw_output: string;
  status: string;
  error_type?: string | null;
  latency_ms: number;
  cost_usd: number;
  cached_tokens: number;
  truncated: boolean;
  sent_body_chars: number;
};

export type CustomClassifyResult = {
  title: string;
  body_chars: number;
  model_a: CustomClassifyModelResult;
  model_b: CustomClassifyModelResult;
  agreement: boolean;
};

export type IssueRow = {
  issue_id: string;
  label_a?: string;
  label_b?: string;
  latency_a?: number;
  latency_b?: number;
  status_a?: string;
  status_b?: string;
};

export type FunnelCandidate = {
  slug: string;
  family: string;
  parameter_b: number;
  size_class: string;
  reasoning: boolean;
  instruct: boolean;
  selection_reason: string;
};

export type FunnelModelResult = {
  slug: string;
  accuracy: number;
  macro_f1: number;
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  confusion_matrix: Record<string, Record<string, number>>;
  cost_per_call: number;
  cost_total: number;
  p95_latency_ms: number;
  throughput_rps: number;
  error_rate: number;
  invalid_rate: number;
  ok_count: number;
  failed_count: number;
  scored_count: number;
};

export type FunnelPodiumEntry = {
  rank: number;
  slug: string;
  accuracy: number;
  macro_f1: number;
  cost_per_call: number;
  p95_latency_ms: number;
};

export type FunnelFieldSummary = {
  survivors: number;
  avg_accuracy: number;
  avg_cost_per_call: number;
  avg_p95_latency_ms: number;
};

export type FunnelRecommendation = {
  model_a: string;
  model_b: string;
  rationale: string;
  podium: FunnelPodiumEntry[];
  field_summary: FunnelFieldSummary;
  finalists: Array<{
    slug: string;
    story: string;
    accuracy: number;
    macro_f1: number;
    cost_per_call: number;
  }>;
};

export type FunnelStage1Artifact = {
  total_live_slugs: number;
  open_weight_slugs: number;
  selected: FunnelCandidate[];
};

export type FunnelRun = {
  funnel_id: string;
  timestamp: string;
  status: string;
  stage_reached: number;
  pilot_model_slugs: string[];
  full_model_slugs: string[];
  recommended_a?: string | null;
  recommended_b?: string | null;
  rationale: string;
  elimination_summary: Record<string, unknown>;
  started_at?: string;
  finished_at?: string;
  artifacts?: {
    stage1_candidates?: FunnelStage1Artifact;
    stage2_pilot?: FunnelModelResult[];
    stage3_full?: FunnelModelResult[];
    stage4_recommendation?: FunnelRecommendation;
  };
};

export type FunnelStatus = {
  funnel: FunnelRun;
  progress: {
    stage: number;
    model_index: number;
    model_count: number;
    current_slug: string | null;
    issue_index?: number;
    issue_count?: number;
  } | null;
};

export type IssueDetail = {
  issue_id: string;
  title: string;
  body_snippet: string;
  html_url: string;
  ground_truth?: string;
  in_scored_set: boolean;
  predictions: Record<string, Record<string, unknown>>;
  model_a: string;
  model_b: string;
};
