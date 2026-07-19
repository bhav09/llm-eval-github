import { Link } from "react-router-dom";
import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Badge, Button, Card, CardContent } from "@/components/ui/primitives";
import { api, FunnelRun, RunManifest } from "@/lib/api";

type HistoryRow =
  | {
      kind: "eval";
      id: string;
      started: string | undefined;
      status: string;
      models: string[];
      progress: { completed: number; total: number; failed: number };
      issueIds: string[];
      viewUrl: string;
    }
  | {
      kind: "selection";
      id: string;
      started: string | undefined;
      status: string;
      pilotSlugs: string[];
      fullSlugs: string[];
      stageReached: number;
      recommendedA: string | null | undefined;
      recommendedB: string | null | undefined;
      viewUrl: string;
    };

export function RunHistoryPage() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [evalRes, funnelRes] = await Promise.all([
        api.runs(100).catch(() => ({ runs: [] as RunManifest[] })),
        api.funnels(100).catch(() => ({ funnels: [] as FunnelRun[] })),
      ]);
      const evalRows: HistoryRow[] = (evalRes.runs ?? []).map((r) => ({
        kind: "eval" as const,
        id: r.run_id,
        started: r.started_at,
        status: r.status,
        models: [r.model_a, r.model_b],
        progress: { completed: r.completed, total: r.total, failed: r.failed },
        issueIds: r.sampled_issue_ids ?? [],
        viewUrl: `/eval?run=${r.run_id}`,
      }));
      const funnelRows: HistoryRow[] = (funnelRes.funnels ?? []).map((f) => ({
        kind: "selection" as const,
        id: f.funnel_id,
        started: f.started_at ?? f.timestamp,
        status: f.status,
        pilotSlugs: f.pilot_model_slugs,
        fullSlugs: f.full_model_slugs,
        stageReached: f.stage_reached,
        recommendedA: f.recommended_a,
        recommendedB: f.recommended_b,
        viewUrl: `/selection?funnel=${f.funnel_id}`,
      }));
      // Merge and sort by started time descending (newest first). Runs without
      // a timestamp sink to the bottom.
      const merged = [...evalRows, ...funnelRows].sort((a, b) => {
        const ta = a.started ? Date.parse(a.started) : 0;
        const tb = b.started ? Date.parse(b.started) : 0;
        return tb - ta;
      });
      setRows(merged);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-6 py-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black tracking-tight text-[var(--color-foreground)]">Run History</h2>
          <p className="text-sm text-[var(--color-muted)] leading-relaxed">
            A unified, time-sorted log of all selection funnel and head-to-head eval runs — with expandable detail and direct links back to each result.
          </p>
        </div>
        <Button variant="outline" onClick={load} className="text-xs shrink-0 mt-1">
          <RefreshCw size={13} className="mr-1.5" />
          Refresh
        </Button>
      </div>

      <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
        <CardContent className="overflow-x-auto py-4">
          {error ? (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          ) : loading ? (
            <p className="text-sm text-[var(--color-muted)]">Loading…</p>
          ) : rows.length === 0 ? (
            <div className="py-8 text-center">
              <p className="text-sm text-[var(--color-muted)]">No runs yet.</p>
              <div className="mt-2 flex justify-center gap-3 text-xs">
                <Link to="/selection" className="text-[var(--color-brand)] hover:underline">
                  Start a selection →
                </Link>
                <Link to="/eval" className="text-[var(--color-brand)] hover:underline">
                  Start an eval →
                </Link>
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-[var(--color-muted)]">
                  <th className="py-2 pr-4 font-medium">Type</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Detail</th>
                  <th className="py-2 pr-4 font-medium">Progress</th>
                  <th className="py-2 pr-4 font-medium">Started</th>
                  <th className="py-2 pr-4"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isOpen = expanded === row.id;
                  return (
                    <Fragment key={`${row.kind}-${row.id}`}>
                      <tr
                        className="cursor-pointer border-b border-[var(--color-border)] hover:bg-[var(--color-hover)]"
                        onClick={() => setExpanded(isOpen ? null : row.id)}
                      >
                        <td className="py-2.5 pr-4">
                          <Badge variant={row.kind === "selection" ? "default" : "muted"}>
                            {row.kind === "selection" ? "Selection" : "Eval"}
                          </Badge>
                        </td>
                        <td className="py-2.5 pr-4">
                          <Badge
                            variant={
                              row.status === "complete"
                                ? "success"
                                : row.status === "failed"
                                  ? "warning"
                                  : row.status === "aborted"
                                    ? "muted"
                                    : "default"
                            }
                          >
                            {row.status}
                          </Badge>
                        </td>
                        <td className="py-2.5 pr-4 text-xs text-[var(--color-foreground)]">
                          {row.kind === "eval" ? (
                            <span>
                              <span className="block">{row.models[0]}</span>
                              <span className="block text-[var(--color-muted)]">{row.models[1]}</span>
                            </span>
                          ) : (
                            <span>
                              <span className="block">{row.pilotSlugs.length} candidates</span>
                              <span className="block text-[var(--color-muted)]">
                                {row.recommendedA ? `${row.recommendedA} · ${row.recommendedB ?? ""}` : "no recommendation"}
                              </span>
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-xs text-[var(--color-foreground)]">
                          {row.kind === "eval" ? (
                            <span>
                              {row.progress.completed}/{row.progress.total}
                              {row.progress.failed ? (
                                <span className="text-red-600 dark:text-red-400"> · {row.progress.failed} fail</span>
                              ) : null}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[var(--color-brand)]">
                              {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                              stage {row.stageReached}/4
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-xs text-[var(--color-muted)]">
                          {row.started ? new Date(row.started).toLocaleString() : "—"}
                        </td>
                        <td className="py-2.5 pr-4">
                          <Link
                            className="text-xs text-[var(--color-brand)] hover:underline"
                            to={row.viewUrl}
                            onClick={(e) => e.stopPropagation()}
                          >
                            View
                          </Link>
                        </td>
                      </tr>
                      {isOpen ? (
                        <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]">
                          <td colSpan={6} className="px-6 py-3">
                            <RowDetail row={row} />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </main>
  );
}

function RowDetail({ row }: { row: HistoryRow }) {
  if (row.kind === "eval") {
    const ids = row.issueIds;
    return (
      <div className="flex flex-wrap gap-1.5">
        {ids.length === 0 ? (
          <span className="text-xs text-[var(--color-muted)]">No issue IDs recorded.</span>
        ) : (
          ids.map((id) => (
            <a
              key={id}
              href={`https://github.com/${id.replace("#", "/issues/")}`}
              target="_blank"
              rel="noreferrer"
              className="inline-block rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 font-mono text-xs text-[var(--color-foreground)] hover:bg-[var(--color-hover)]"
            >
              {id.split("#")[1]}
            </a>
          ))
        )}
      </div>
    );
  }
  // selection
  return (
    <div className="space-y-2 text-xs">
      <div>
        <span className="text-[var(--color-muted)]">Pilot candidates: </span>
        <span className="font-mono text-[var(--color-foreground)]">{row.pilotSlugs.join(", ") || "—"}</span>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Full-eval survivors: </span>
        <span className="font-mono text-[var(--color-foreground)]">{row.fullSlugs.join(", ") || "—"}</span>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Recommended: </span>
        <span className="font-mono text-[var(--color-foreground)]">
          {row.recommendedA ? `${row.recommendedA} · ${row.recommendedB ?? ""}` : "—"}
        </span>
      </div>
    </div>
  );
}
