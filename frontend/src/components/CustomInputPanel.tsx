import { useState } from "react";
import { ChevronDown, FlaskConical } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardTitle } from "@/components/ui/primitives";
import { api, CustomClassifyResult } from "@/lib/api";
import { formatUsd } from "@/lib/utils";
import { cn } from "@/lib/utils";

type Props = {
  modelA: string;
  modelB: string;
};

export function CustomInputPanel({ modelA, modelB }: Props) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CustomClassifyResult | null>(null);

  async function classify() {
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = await api.classifyCustom({
        title: title.trim(),
        body,
        model_a: modelA,
        model_b: modelB,
        use_mock: false,
      });
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Classification failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-5 py-4 text-left"
      >
        <div className="flex items-center gap-2">
          <FlaskConical className="text-[var(--color-brand)]" size={18} />
          <div>
            <CardTitle className="text-[var(--color-foreground)]">
              Custom issue (outside corpus)
            </CardTitle>
            <CardDescription>Optional — classify any title/body without a corpus run.</CardDescription>
          </div>
        </div>
        <ChevronDown
          size={18}
          className={cn(
            "text-[var(--color-muted)] transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <CardContent className="space-y-4 border-t border-[var(--color-border)] pt-4">
          <label className="block text-sm">
            <span className="mb-1 block text-[var(--color-muted)]">Title</span>
            <input
              className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 text-sm text-[var(--color-foreground)]"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Authentication fails on Windows after upgrade"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-[var(--color-muted)]">Body</span>
            <textarea
              className="min-h-[120px] w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 py-2 text-sm text-[var(--color-foreground)]"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Describe the issue text you want both models to classify…"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={classify} disabled={loading || !modelA || !modelB}>
              {loading ? "Classifying…" : "Classify custom issue"}
            </Button>
            <span className="text-xs text-[var(--color-muted)]">
              Uses Model A ({modelA || "—"}) and Model B ({modelB || "—"})
            </span>
          </div>
          {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}
          {result ? (
            <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-[var(--color-foreground)]">Results</span>
                <Badge variant={result.agreement ? "success" : "warning"}>
                  {result.agreement ? "Models agree" : "Models disagree"}
                </Badge>
                {result.model_a.truncated || result.model_b.truncated ? (
                  <Badge variant="muted">Body truncated for context window</Badge>
                ) : null}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {[result.model_a, result.model_b].map((row) => (
                  <div
                    key={row.model}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                  >
                    <p className="text-xs text-[var(--color-muted)]">{row.model}</p>
                    <p className="mt-1 text-lg font-semibold capitalize text-[var(--color-foreground)]">
                      {row.predicted_label ?? "—"}
                    </p>
                    <p className="mt-2 text-xs text-[var(--color-muted)]">
                      {row.latency_ms.toFixed(1)} ms · {formatUsd(row.cost_usd)}
                      {row.status !== "ok" ? ` · ${row.error_type ?? "error"}` : ""}
                    </p>
                    {row.raw_output ? (
                      <pre className="mt-2 max-h-24 overflow-auto rounded bg-[var(--color-surface-muted)] p-2 text-xs text-[var(--color-muted)]">
                        {row.raw_output}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  );
}
