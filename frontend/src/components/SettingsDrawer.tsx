import { useState, useEffect } from "react";
import { Settings, X, RotateCcw } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export interface SessionSettings {
  concurrency: number;
  adjudicator_model: string;
  pilot_issue_count: number;
  full_issue_count: number;
  error_rate_elim: number;
  invalid_rate_elim: number;
  request_timeout_sec: number;
  max_retries: number;
}

export const DEFAULT_SETTINGS: SessionSettings = {
  concurrency: 8,
  adjudicator_model: "deepseek-v4-pro",
  pilot_issue_count: 5,
  full_issue_count: 10,
  error_rate_elim: 0.20,
  invalid_rate_elim: 0.20,
  request_timeout_sec: 60,
  max_retries: 3,
};

export function getSessionSettings(): SessionSettings {
  try {
    const stored = sessionStorage.getItem("colosseum_session_settings");
    if (stored) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
    }
  } catch (e) {
    console.error("Failed to load session settings", e);
  }
  return DEFAULT_SETTINGS;
}

export function saveSessionSettings(settings: SessionSettings) {
  try {
    sessionStorage.setItem("colosseum_session_settings", JSON.stringify(settings));
    // Trigger storage event so other components on this page get notified
    window.dispatchEvent(new Event("colosseum_settings_changed"));
  } catch (e) {
    console.error("Failed to save session settings", e);
  }
}

export function SettingsDrawer() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<SessionSettings>(DEFAULT_SETTINGS);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  useEffect(() => {
    setSettings(getSessionSettings());
    api.models()
      .then((res) => {
        setAvailableModels(res.models.map((m) => m.slug));
      })
      .catch(() => {
        setAvailableModels(["deepseek-v4-pro", "gemma-4-31B-it", "mistral-3-14B", "deepseek-4-flash"]);
      });
  }, [open]);

  const handleSave = () => {
    saveSessionSettings(settings);
    setOpen(false);
  };

  const handleReset = () => {
    setSettings(DEFAULT_SETTINGS);
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-foreground)] hover:bg-[var(--color-hover)] transition-all cursor-pointer hover:scale-[1.05]"
          title="Configure Settings"
        >
          <Settings size={16} />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className="fixed right-0 top-0 bottom-0 z-50 w-full sm:w-[440px] border-l border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-2xl flex flex-col justify-between overflow-y-auto">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-[var(--color-border)]">
              <div>
                <Dialog.Title className="text-base font-bold text-[var(--color-foreground)]">Configuration Settings</Dialog.Title>
                <Dialog.Description className="text-xs text-[var(--color-muted)] mt-0.5">Session-scoped run overrides</Dialog.Description>
              </div>
              <Dialog.Close className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-hover)] hover:text-[var(--color-foreground)] cursor-pointer">
                <X size={16} />
              </Dialog.Close>
            </div>

            <div className="mt-5 space-y-5">
              {/* Concurrency */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-[var(--color-foreground)]">Inference Concurrency</span>
                  <span className="font-mono font-bold text-[var(--color-brand)]">{settings.concurrency} threads</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="32"
                  value={settings.concurrency}
                  onChange={(e) => setSettings({ ...settings, concurrency: parseInt(e.target.value) })}
                  className="w-full h-1.5 bg-[var(--color-border)] rounded-lg appearance-none cursor-pointer accent-[var(--color-brand)]"
                />
                <p className="text-[10px] text-[var(--color-muted)]">Parallel inference API worker processes.</p>
              </div>

              {/* Adjudicator Model */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[var(--color-foreground)]">Grading / Adjudicator Model</label>
                <select
                  value={settings.adjudicator_model}
                  onChange={(e) => setSettings({ ...settings, adjudicator_model: e.target.value })}
                  className="w-full h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 text-xs text-[var(--color-foreground)] focus:border-[var(--color-brand)] focus:outline-none"
                >
                  {availableModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <p className="text-[10px] text-[var(--color-muted)]">Grading LLM used for consensus validation on ambiguous issues.</p>
              </div>

              {/* Pilot / Full Counts */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[var(--color-foreground)]">Pilot Issues</label>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={settings.pilot_issue_count}
                    onChange={(e) => setSettings({ ...settings, pilot_issue_count: Math.max(1, parseInt(e.target.value) || 1) })}
                    className="w-full h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 text-xs text-[var(--color-foreground)] focus:border-[var(--color-brand)] focus:outline-none"
                  />
                  <p className="text-[10px] text-[var(--color-muted)]">Stage 2 sample size.</p>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[var(--color-foreground)]">Full Eval Issues</label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={settings.full_issue_count}
                    onChange={(e) => setSettings({ ...settings, full_issue_count: Math.max(1, parseInt(e.target.value) || 1) })}
                    className="w-full h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 text-xs text-[var(--color-foreground)] focus:border-[var(--color-brand)] focus:outline-none"
                  />
                  <p className="text-[10px] text-[var(--color-muted)]">Stage 3 sample size.</p>
                </div>
              </div>

              {/* Elimination Thresholds */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-[var(--color-foreground)]">Max Failure Rate (Error)</span>
                  <span className="font-mono font-bold text-amber-500">{(settings.error_rate_elim * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={settings.error_rate_elim * 100}
                  onChange={(e) => setSettings({ ...settings, error_rate_elim: parseFloat(e.target.value) / 100 })}
                  className="w-full h-1.5 bg-[var(--color-border)] rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-[var(--color-foreground)]">Max Format Error Rate</span>
                  <span className="font-mono font-bold text-amber-500">{(settings.invalid_rate_elim * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={settings.invalid_rate_elim * 100}
                  onChange={(e) => setSettings({ ...settings, invalid_rate_elim: parseFloat(e.target.value) / 100 })}
                  className="w-full h-1.5 bg-[var(--color-border)] rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
              </div>

              {/* Timeout / Retries */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[var(--color-foreground)]">Timeout (sec)</label>
                  <input
                    type="number"
                    min="5"
                    max="300"
                    value={settings.request_timeout_sec}
                    onChange={(e) => setSettings({ ...settings, request_timeout_sec: Math.max(5, parseInt(e.target.value) || 5) })}
                    className="w-full h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 text-xs text-[var(--color-foreground)] focus:border-[var(--color-brand)] focus:outline-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[var(--color-foreground)]">Max Retries</label>
                  <input
                    type="number"
                    min="0"
                    max="5"
                    value={settings.max_retries}
                    onChange={(e) => setSettings({ ...settings, max_retries: Math.max(0, parseInt(e.target.value) || 0) })}
                    className="w-full h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-input-bg)] px-3 text-xs text-[var(--color-foreground)] focus:border-[var(--color-brand)] focus:outline-none"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 flex items-center justify-between gap-3 border-t border-[var(--color-border)] pt-4">
            <Button variant="outline" size="sm" onClick={handleReset} className="flex items-center gap-1">
              <RotateCcw size={12} />
              Reset
            </Button>
            <div className="flex gap-2">
              <Dialog.Close asChild>
                <Button variant="ghost" size="sm">Cancel</Button>
              </Dialog.Close>
              <Button size="sm" onClick={handleSave}>Save Configuration</Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
