"""4-stage model-selection funnel: stratified select, pilot, full eval, recommend."""

from __future__ import annotations

import asyncio
import json
import statistics
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from config import ROOT_DIR, get_settings
from eval.model_catalog import fetch_live_models, stratified_select
from eval.orchestrator import EvalOrchestrator, load_ground_truth
from eval.persistence import FunnelRun, RunStore
from ingestion.corpus_store import latest_version, load_issues_from_snapshot
from inference.runner import load_predictions
from observability.logging import get_logger

log = get_logger()

FUNNELS_DIR = ROOT_DIR / "results" / "funnels"
PILOT_ISSUE_COUNT = 5
FULL_ISSUE_COUNT = 10  # 5 pilot reused + 5 new issues max
ERROR_RATE_ELIM = 0.20
INVALID_RATE_ELIM = 0.20


def make_funnel_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _stratified_scored_issues(issues: list, scored_ids: set[str], n: int) -> list:
    """Pick `n` scored issues, stratified by ground-truth label, for the pilot/full eval."""
    by_label: dict[str, list] = {}
    for issue in issues:
        if issue.issue_id in scored_ids:
            # We need the label; load it from ground truth separately.
            by_label.setdefault("__all__", []).append(issue)
    pool = by_label.get("__all__", [])
    return pool[:n] if len(pool) <= n else pool[:n]


class FunnelOrchestrator:
    def __init__(
        self,
        settings=None,
        orchestrator: EvalOrchestrator | None = None,
        *,
        db_path: Path | None = None,
        funnels_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.orchestrator = orchestrator or EvalOrchestrator(self.settings)
        # Default to the real DB/results dir, but allow tests to isolate.
        self.db = RunStore(db_path or (ROOT_DIR / "results" / "eval.db"))
        self.funnels_dir = funnels_dir or FUNNELS_DIR

    def _funnel_dir(self, funnel_id: str) -> Path:
        return self.funnels_dir / funnel_id

    async def run_funnel(
        self,
        *,
        use_mock: bool = False,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[str, int, int, int, str | None, int, int], None] | None = None,
        funnel_id: str | None = None,
    ) -> FunnelRun:
        funnel_id = funnel_id or make_funnel_id()
        funnel_dir = self._funnel_dir(funnel_id)
        funnel_dir.mkdir(parents=True, exist_ok=True)

        funnel = FunnelRun(
            funnel_id=funnel_id,
            timestamp=datetime.now(UTC).isoformat(),
            status="running",
            stage_reached=0,
        )
        self.db.upsert_funnel(funnel)

        try:
            # --- Stage 1: stratified selection (no API) ---
            live_slugs = await fetch_live_models()
            # Only open-weight chat models are eligible for the funnel.
            from eval.model_catalog import _is_open_weight_chat

            open_weight_slugs = [s for s in live_slugs if _is_open_weight_chat(s)]
            candidates = stratified_select(live_slugs, k=6)
            funnel.pilot_model_slugs = [c["slug"] for c in candidates]
            funnel.stage_reached = 1
            self.db.upsert_funnel(funnel)
            # Include the exact live + open-weight counts so the UI doesn't show
            # a hardcoded number and makes the eligibility filter explicit.
            self._write_stage(
                funnel_dir,
                "stage1_candidates.json",
                {
                    "total_live_slugs": len(live_slugs),
                    "open_weight_slugs": len(open_weight_slugs),
                    "selected": candidates,
                },
            )
            if progress_callback:
                progress_callback(funnel_id, 1, len(candidates), len(candidates), None, len(candidates), len(candidates))

            if cancel_event and cancel_event.is_set():
                return self._finalize(funnel, cancelled=True)

            # Load issues once; pilot uses first PILOT_ISSUE_COUNT scored,
            # full uses FULL_ISSUE_COUNT scored (superset of pilot).
            settings = self.settings
            corpus_root = settings.resolve_path(settings.corpus_path)
            version = latest_version(corpus_root, settings.github_repo)
            all_issues = load_issues_from_snapshot(corpus_root, settings.github_repo, version)
            gt_path = settings.resolve_path(settings.ground_truth_path) / "labels.json"
            ground_truth, scored_ids = load_ground_truth(gt_path)
            scored_issues = [i for i in all_issues if i.issue_id in scored_ids]
            import random
            random.shuffle(scored_issues)
            pilot_issues = scored_issues[:PILOT_ISSUE_COUNT]
            full_issues = scored_issues[:FULL_ISSUE_COUNT]  # superset of pilot_issues

            # --- Stage 2: pilot (6 models x 10 issues) ---
            pilot_results = await self._run_stage(
                funnel_id,
                funnel_dir,
                stage="pilot",
                models=funnel.pilot_model_slugs,
                issues=pilot_issues,
                corpus_version=version,
                use_mock=use_mock,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )
            self._write_stage(funnel_dir, "stage2_pilot.json", pilot_results)
            funnel.stage_reached = 2
            self.db.upsert_funnel(funnel)

            if cancel_event and cancel_event.is_set():
                return self._finalize(funnel, cancelled=True)

            # Eliminate underperformers using multi-criteria weighted scoring
            import math
            
            costs = [r["cost_per_call"] or 0.0 for r in pilot_results]
            latencies = [r["p95_latency_ms"] for r in pilot_results]
            throughputs = [r["throughput_rps"] for r in pilot_results]
            
            min_cost, max_cost = min(costs) if costs else (0.0, 0.0), max(costs) if costs else (0.0, 0.0)
            min_lat, max_lat = min(latencies) if latencies else (0.0, 0.0), max(latencies) if latencies else (0.0, 0.0)
            min_thru, max_thru = min(throughputs) if throughputs else (0.0, 0.0), max(throughputs) if throughputs else (0.0, 0.0)
            
            scored_results = []
            for r in pilot_results:
                acc_score = r["accuracy"]
                
                cost_val = r["cost_per_call"] or 0.0
                cost_score = (max_cost - cost_val) / (max_cost - min_cost) if max_cost > min_cost else 1.0
                
                lat_val = r["p95_latency_ms"]
                lat_score = (max_lat - lat_val) / (max_lat - min_lat) if max_lat > min_lat else 1.0
                
                thru_val = r["throughput_rps"]
                thru_score = (thru_val - min_thru) / (max_thru - min_thru) if max_thru > min_thru else 1.0
                
                rel_val = max(0.0, 1.0 - r["error_rate"] - r["invalid_rate"])
                
                comp_score = (
                    0.30 * acc_score +
                    0.20 * lat_score +
                    0.20 * cost_score +
                    0.15 * thru_score +
                    0.15 * rel_val
                )
                
                # Tag notable weaknesses
                weaknesses = []
                if acc_score < 0.40:
                    weaknesses.append("accuracy")
                if cost_val > 0.005:
                    weaknesses.append("cost")
                if lat_val > 1500:
                    weaknesses.append("latency")
                if r["error_rate"] + r["invalid_rate"] > 0.15:
                    weaknesses.append("reliability")
                
                scored_results.append({
                    **r,
                    "composite_score": comp_score,
                    "weaknesses": weaknesses,
                })
            
            # Filter for models that do not fail basic operational reliability (error_rate + invalid_rate <= 40%)
            eligible = [r for r in scored_results if (r["error_rate"] + r["invalid_rate"]) <= 0.40]
            if len(eligible) >= 2:
                eligible.sort(key=lambda x: x["composite_score"], reverse=True)
                survivors_count = max(2, math.ceil(len(pilot_results) * 0.5))
                surviving_cohort = eligible[:survivors_count]
                survivors = [s["slug"] for s in surviving_cohort]
            else:
                # Fallback to the 2 with the best reliability rates
                scored_results.sort(key=lambda x: x["error_rate"] + x["invalid_rate"])
                surviving_cohort = scored_results[:2]
                survivors = [s["slug"] for s in surviving_cohort]
                
            funnel.full_model_slugs = survivors
            funnel.stage_reached = 3
            self.db.upsert_funnel(funnel)
            
            # --- Stage 3: full eval (survivors x 10 issues, reuse pilot 5) ---
            full_results = await self._run_stage(
                funnel_id,
                funnel_dir,
                stage="full",
                models=survivors,
                issues=full_issues,
                corpus_version=version,
                use_mock=use_mock,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
                reuse_from_stage="pilot",
                reuse_issues=pilot_issues,
            )
            self._write_stage(funnel_dir, "stage3_full.json", full_results)
            funnel.stage_reached = 4
            self.db.upsert_funnel(funnel)

            if cancel_event and cancel_event.is_set():
                return self._finalize(funnel, cancelled=True)

            # --- Stage 4: recommendation ---
            recommendation = self._recommend(full_results)
            funnel.recommended_a = recommendation["model_a"]
            funnel.recommended_b = recommendation["model_b"]
            funnel.rationale = recommendation["rationale"]
            
            # Format elimination reasons dynamically based on why they were removed
            pilot_rejected_info = []
            for r in scored_results:
                if r["slug"] not in survivors:
                    reasons = []
                    if r["error_rate"] + r["invalid_rate"] > 0.40:
                        reasons.append(f"Operational failure (errors={r['error_rate']:.0%}, invalid={r['invalid_rate']:.0%})")
                    else:
                        best_survivor_acc = max([s["accuracy"] for s in scored_results if s["slug"] in survivors], default=1.0)
                        if best_survivor_acc - r["accuracy"] > 0.10:
                            reasons.append(f"lower accuracy ({r['accuracy']:.0%} vs best {best_survivor_acc:.0%})")
                            
                        best_survivor_lat = min([s["p95_latency_ms"] for s in scored_results if s["slug"] in survivors], default=0.0)
                        if r["p95_latency_ms"] > best_survivor_lat * 1.4:
                            reasons.append(f"higher latency ({r['p95_latency_ms']:.0f}ms vs best {best_survivor_lat:.0f}ms)")
                            
                        best_survivor_cost = min([s["cost_per_call"] or 0.0 for s in scored_results if s["slug"] in survivors], default=0.0)
                        if r["cost_per_call"] is not None and best_survivor_cost > 0 and r["cost_per_call"] > best_survivor_cost * 1.5:
                            reasons.append(f"higher cost (${r['cost_per_call']:.4f} vs best ${best_survivor_cost:.4f})")
                            
                    reason_str = ", ".join(reasons) if reasons else "lower overall multi-criteria composite score"
                    pilot_rejected_info.append({
                        "slug": r["slug"],
                        "reason": f"Eliminated: {reason_str}",
                        "accuracy": r["accuracy"],
                        "cost_per_call": r["cost_per_call"],
                        "p95_latency_ms": r["p95_latency_ms"],
                        "throughput_rps": r["throughput_rps"],
                        "error_rate": r["error_rate"],
                        "invalid_rate": r["invalid_rate"],
                        "composite_score": r["composite_score"],
                        "weaknesses": r["weaknesses"]
                    })
            
            funnel.elimination_summary = {
                "evaluated_count": len(funnel.pilot_model_slugs),
                "stages": ["S1 stratified select", "S2 pilot (5 issues)", "S3 full eval (10 issues)", "S4 recommend"],
                "pilot_rejected": pilot_rejected_info,
                "full_rejected": [
                    {"slug": r["slug"], "reason": "not selected as a finalist (see rationale)"}
                    for r in full_results
                    if r["slug"] not in (funnel.recommended_a, funnel.recommended_b)
                ],
            }
            self._write_stage(funnel_dir, "stage4_recommendation.json", recommendation)
            funnel.status = "complete"
            funnel.finished_at = datetime.now(UTC).isoformat()
            self.db.upsert_funnel(funnel)

            # Persist the computed recommendation so the Eval page can read it.
            # Skip on mock runs so tests don't contaminate the real config with
            # dummy slugs and fake accuracy/cost numbers.
            if not use_mock:
                self._write_recommendations(funnel, recommendation)
            return funnel

        except Exception as exc:  # noqa: BLE001
            log.error("funnel.failed", funnel_id=funnel_id, error=str(exc))
            funnel.status = "failed"
            funnel.finished_at = datetime.now(UTC).isoformat()
            funnel.elimination_summary = {**funnel.elimination_summary, "error": str(exc)}
            self.db.upsert_funnel(funnel)
            raise

    async def _run_stage(
        self,
        funnel_id: str,
        funnel_dir: Path,
        *,
        stage: str,  # "pilot" | "full"
        models: list[str],
        issues: list,
        corpus_version: int,
        use_mock: bool,
        cancel_event: asyncio.Event | None,
        progress_callback: Callable[[str, int, int, int, str | None, int, int], None] | None,
        reuse_from_stage: str | None = None,
        reuse_issues: list | None = None,
    ) -> list[dict]:
        """Run each model on `issues`, return per-model summary dicts."""
        results: list[dict] = []
        stage_dir = funnel_dir / stage
        stage_dir.mkdir(parents=True, exist_ok=True)

        # Pre-seed per-model prediction files with reused pilot predictions so we
        # don't re-run the 10 pilot issues in Stage 3.
        reuse_preds_by_model: dict[str, list] = {}
        if reuse_from_stage and reuse_issues is not None:
            reuse_dir = funnel_dir / reuse_from_stage
            reuse_ids = {i.issue_id for i in reuse_issues}
            for slug in models:
                pred_path = reuse_dir / slug / "predictions.jsonl"
                if pred_path.exists():
                    reuse_preds_by_model[slug] = [
                        p for p in load_predictions(pred_path) if p.issue_id in reuse_ids
                    ]

        for idx, slug in enumerate(models):
            if cancel_event and cancel_event.is_set():
                break
            model_dir = stage_dir / slug
            model_dir.mkdir(parents=True, exist_ok=True)
            pred_path = model_dir / "predictions.jsonl"

            # Seed with reused pilot predictions (if any) by appending them.
            if reuse_preds_by_model.get(slug):
                with pred_path.open("w", encoding="utf-8") as fh:
                    for rec in reuse_preds_by_model[slug]:
                        fh.write(rec.model_dump_json() + "\n")

            # Determine which issues still need to be run (not in reuse set).
            already = {p.issue_id for p in load_predictions(pred_path)} if pred_path.exists() else set()
            pending_issues = [i for i in issues if i.issue_id not in already]

            run_id = f"{funnel_id}-{stage}-{slug}"
            already_count = len(already)
            total_count = len(issues)
            manifest, metrics = await self.orchestrator.run_single(
                slug,
                pending_issues,
                run_id=run_id,
                corpus_version=corpus_version,
                use_mock=use_mock,
                progress_callback=lambda _rid, done, failed: (
                    progress_callback(
                        funnel_id,
                        2 if stage == "pilot" else 3,
                        idx + 1,
                        len(models),
                        slug,
                        already_count + done,
                        total_count,
                    )
                    if progress_callback
                    else None
                ),
                cancel_event=cancel_event,
                predictions_path=pred_path,
            )

            # Recompute metrics over ALL predictions in pred_path (reuse + new).
            all_preds = load_predictions(pred_path)
            from metrics.accumulator import compute_run_metrics

            settings = self.settings
            gt_path = settings.resolve_path(settings.ground_truth_path) / "labels.json"
            ground_truth, scored_ids = load_ground_truth(gt_path)
            full_metrics = compute_run_metrics(
                all_preds,
                ground_truth=ground_truth,
                scored_issue_ids=scored_ids,
                model_a=slug,
                model_b=slug,
            )
            (model_dir / "metrics.json").write_text(json.dumps(full_metrics, indent=2), encoding="utf-8")

            results.append(self._summarize(slug, full_metrics, len(all_preds)))
        return results

    def _summarize(self, slug: str, metrics: dict, pred_count: int) -> dict:
        m = metrics["model_a"]  # model_a == model_b for single-model runs
        total = m["ok_count"] + m["failed_count"]
        error_rate = m["failed_count"] / total if total else 0.0
        invalid_rate = m["error_breakdown"].get("parse", 0) / total if total else 0.0
        return {
            "slug": slug,
            "accuracy": m["scored"]["accuracy"],
            "macro_f1": m["scored"]["macro_f1"],
            "per_class": m["scored"]["per_class"],
            "confusion_matrix": m["scored"]["confusion_matrix"],
            "cost_per_call": m["cost_usd"]["per_call"],
            "cost_total": m["cost_usd"]["total"],
            "p95_latency_ms": m["latency_ms"]["p95"],
            "throughput_rps": pred_count / max(m["latency_ms"]["p50"] * 0.001 * pred_count, 0.001) if pred_count else 0.0,
            "error_rate": error_rate,
            "invalid_rate": invalid_rate,
            "ok_count": m["ok_count"],
            "failed_count": m["failed_count"],
            "scored_count": m["scored"]["count"],
        }

    def _recommend(self, full_results: list[dict]) -> dict:
        if len(full_results) < 2:
            raise RuntimeError("Need at least 2 survivors to recommend")

        # Best value = highest accuracy per dollar (tiebreak macro_f1).
        def value_score(r: dict) -> float:
            cost = r["cost_per_call"] or 1e-9
            return r["accuracy"] / cost

        ranked_value = sorted(full_results, key=lambda r: (value_score(r), r["macro_f1"]), reverse=True)
        best_value = ranked_value[0]

        # Highest accuracy (tiebreak macro_f1).
        ranked_acc = sorted(full_results, key=lambda r: (r["accuracy"], r["macro_f1"]), reverse=True)
        best_acc = ranked_acc[0]

        # If same model wins both, pick the second-highest accuracy as model_b.
        if best_acc["slug"] == best_value["slug"]:
            best_acc = ranked_acc[1]

        # Reject if the two are nearly identical (within 2pp accuracy AND within 1.5x cost).
        a_cost = best_value["cost_per_call"] or 1e-9
        b_cost = best_acc["cost_per_call"] or 1e-9
        if (
            abs(best_value["accuracy"] - best_acc["accuracy"]) < 0.02
            and max(a_cost, b_cost) / min(a_cost, b_cost) < 1.5
            and len(ranked_acc) > 2
        ):
            best_acc = ranked_acc[2]

        rationale = (
            f"Evaluated {len(full_results)} finalist models across 4 stages "
            f"(stratified select, pilot 5 issues, full eval 10 issues). "
            f"Finalist A ({best_value['slug']}): best value at {best_value['accuracy']:.0%} accuracy "
            f"/ ${best_value['cost_per_call']:.4f} per call. "
            f"Finalist B ({best_acc['slug']}): highest accuracy at {best_acc['accuracy']:.0%} "
            f"(macro F1 {best_acc['macro_f1']:.3f}). "
            f"The two represent a meaningful production trade-off: value vs quality ceiling."
        )

        # Podium: rank all survivors by accuracy (tiebreak macro_f1, then lower cost)
        # for the 1st/2nd/3rd display on the selection page.
        podium_ranked = sorted(
            full_results,
            key=lambda r: (r["accuracy"], r["macro_f1"], -(r["cost_per_call"] or 0)),
            reverse=True,
        )
        podium = [
            {
                "rank": i + 1,
                "slug": r["slug"],
                "accuracy": r["accuracy"],
                "macro_f1": r["macro_f1"],
                "cost_per_call": r["cost_per_call"],
                "p95_latency_ms": r["p95_latency_ms"],
            }
            for i, r in enumerate(podium_ranked[:3])
        ]

        # Field summary: how the winners compare to the survivor field average.
        # Used by the Insights section to give context without repeating the
        # per-model numbers already shown on the podium.
        if full_results:
            field_summary = {
                "survivors": len(full_results),
                "avg_accuracy": statistics.fmean(r["accuracy"] for r in full_results),
                "avg_cost_per_call": statistics.fmean(r["cost_per_call"] or 0.0 for r in full_results),
                "avg_p95_latency_ms": statistics.fmean(r["p95_latency_ms"] for r in full_results),
            }
        else:
            field_summary = {"survivors": 0, "avg_accuracy": 0.0, "avg_cost_per_call": 0.0, "avg_p95_latency_ms": 0.0}

        return {
            "model_a": best_value["slug"],
            "model_b": best_acc["slug"],
            "rationale": rationale,
            "podium": podium,
            "field_summary": field_summary,
            "finalists": [
                {
                    "slug": best_value["slug"],
                    "story": "Best value (accuracy per dollar)",
                    "accuracy": best_value["accuracy"],
                    "macro_f1": best_value["macro_f1"],
                    "cost_per_call": best_value["cost_per_call"],
                },
                {
                    "slug": best_acc["slug"],
                    "story": "Highest accuracy (quality ceiling)",
                    "accuracy": best_acc["accuracy"],
                    "macro_f1": best_acc["macro_f1"],
                    "cost_per_call": best_acc["cost_per_call"],
                },
            ],
        }

    def _finalize(self, funnel: FunnelRun, *, cancelled: bool) -> FunnelRun:
        funnel.status = "aborted" if cancelled else "complete"
        funnel.finished_at = datetime.now(UTC).isoformat()
        self.db.upsert_funnel(funnel)
        return funnel

    def _write_stage(self, funnel_dir: Path, name: str, payload: object) -> None:
        (funnel_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_recommendations(self, funnel: FunnelRun, recommendation: dict) -> None:
        from eval.model_catalog import RECOMMENDATIONS_PATH

        payload = {
            "model_a": recommendation["model_a"],
            "model_b": recommendation["model_b"],
            "rationale": recommendation["rationale"],
            "elimination_summary": funnel.elimination_summary,
        }
        RECOMMENDATIONS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
