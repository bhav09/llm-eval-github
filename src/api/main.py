"""FastAPI application for the eval harness UI."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import ROOT_DIR, get_settings
from eval.custom_classify import classify_custom
from eval.funnel import FUNNELS_DIR
from eval.model_catalog import get_models_for_ui, load_recommendations
from eval.orchestrator import DB_PATH, RUNS_DIR, load_run_metrics, reload_run
from eval.persistence import RunStore
from eval.run_manager import run_manager
from ingestion.corpus_store import latest_version, load_issues_from_snapshot

import sys
import shutil

STATIC_DIR = ROOT_DIR / "static"
IS_TESTING = "pytest" in sys.modules or "unittest" in sys.modules

# Seed persistent volume if mounted empty
PRELOADED_DIR = ROOT_DIR / "preloaded_results"
RESULTS_DIR = ROOT_DIR / "results"
if PRELOADED_DIR.exists() and not (RESULTS_DIR / "eval.db").exists():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(PRELOADED_DIR, RESULTS_DIR, dirs_exist_ok=True)
    except Exception:
        pass

app = FastAPI(title="FDE Issue Classification Eval", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRunRequest(BaseModel):
    model_a: str
    model_b: str
    limit: int | None = Field(default=None, ge=1, le=534)
    use_mock: bool = False
    confirm_spend: bool = False
    concurrency: int | None = Field(default=None, ge=1, le=32)
    request_timeout_sec: int | None = Field(default=None, ge=5, le=300)
    max_retries: int | None = Field(default=None, ge=0, le=5)


class CustomClassifyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=50000)
    model_a: str
    model_b: str
    use_mock: bool = False


class StartFunnelRequest(BaseModel):
    use_mock: bool = False
    confirm_spend: bool = False
    concurrency: int | None = Field(default=None, ge=1, le=32)
    adjudicator_model: str | None = Field(default=None, min_length=1)
    pilot_issue_count: int | None = Field(default=None, ge=1, le=20)
    full_issue_count: int | None = Field(default=None, ge=1, le=50)
    error_rate_elim: float | None = Field(default=None, ge=0.0, le=1.0)
    invalid_rate_elim: float | None = Field(default=None, ge=0.0, le=1.0)
    request_timeout_sec: int | None = Field(default=None, ge=5, le=300)
    max_retries: int | None = Field(default=None, ge=0, le=5)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    settings = get_settings()
    corpus_root = settings.resolve_path(settings.corpus_path)
    gt_path = settings.resolve_path(settings.ground_truth_path) / "labels.json"
    checks = {
        "corpus": corpus_root.exists(),
        "ground_truth": gt_path.exists(),
        "results_writable": RUNS_DIR.parent.exists() or True,
        "do_api_configured": bool(settings.do_api),
    }
    return {"ready": all(checks.values()), "checks": checks}


@app.get("/api/config")
def api_config() -> dict:
    settings = get_settings()
    return {
        "concurrency": settings.concurrency,
        "github_repo": settings.github_repo,
        "allow_runtime_concurrency": False,
    }


@app.get("/api/models")
async def api_models() -> dict:
    try:
        models = await get_models_for_ui()
    except Exception:
        from eval.model_catalog import list_comparison_models, load_recommendations

        recs = load_recommendations()
        models = list_comparison_models() or [
            {"slug": recs["model_a"], "tier": "fallback", "available": True, "cache_supported": True},
            {"slug": recs["model_b"], "tier": "fallback", "available": True, "cache_supported": True},
        ]
    return {"models": models}


@app.get("/api/recommendations")
def api_recommendations() -> dict:
    return load_recommendations()


@app.get("/api/runs")
def api_runs(limit: int = Query(default=20, le=200)) -> dict:
    store = RunStore(DB_PATH)
    return {"runs": store.list_runs(limit=limit)}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict:
    store = RunStore(DB_PATH)
    manifest = store.get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Run not found")
    metrics_path = RUNS_DIR / run_id / "metrics.json"
    predictions_path = RUNS_DIR / run_id / "predictions.jsonl"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
    prediction_count = sum(1 for line in predictions_path.open(encoding="utf-8") if line.strip()) if predictions_path.exists() else 0
    return {"manifest": manifest, "metrics": metrics, "prediction_count": prediction_count}


@app.get("/api/runs/{run_id}/status")
def api_run_status(run_id: str) -> dict:
    status = run_manager.get_progress(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@app.get("/api/runs/{run_id}/metrics")
def api_run_metrics(run_id: str) -> dict:
    path = RUNS_DIR / run_id / "metrics.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Metrics not ready")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    result = await run_manager.cancel_run(run_id)
    return result


@app.post("/api/funnel/start")
async def start_funnel(body: StartFunnelRequest) -> dict:
    settings = get_settings()
    run_use_mock = body.use_mock
    if not run_use_mock and not body.confirm_spend:
        raise HTTPException(
            status_code=400,
            detail="Live funnel requires confirm_spend=true (~45-60 API calls across 6 models).",
        )
    if not run_use_mock and not settings.do_api:
        raise HTTPException(status_code=400, detail="DO_API is required for live inference.")
    try:
        custom_settings = body.model_dump(exclude={"use_mock", "confirm_spend"}, exclude_none=True)
        funnel = await run_manager.start_funnel(use_mock=run_use_mock, custom_settings=custom_settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return funnel.model_dump()


@app.get("/api/funnel")
def list_funnels(limit: int = Query(default=10, le=50)) -> dict:
    store = RunStore(DB_PATH)
    return {"funnels": store.list_funnels(limit=limit)}


@app.get("/api/funnel/{funnel_id}")
def get_funnel(funnel_id: str) -> dict:
    store = RunStore(DB_PATH)
    funnel = store.get_funnel(funnel_id)
    if not funnel:
        raise HTTPException(status_code=404, detail="Funnel not found")
    # Attach stage artifacts (candidates, pilot, full, recommendation) if present.
    funnel_dir = FUNNELS_DIR / funnel_id
    artifacts: dict = {}
    for name, key in [
        ("stage1_candidates.json", "stage1_candidates"),
        ("stage2_pilot.json", "stage2_pilot"),
        ("stage3_full.json", "stage3_full"),
        ("stage4_recommendation.json", "stage4_recommendation"),
    ]:
        path = funnel_dir / name
        if path.exists():
            artifacts[key] = json.loads(path.read_text(encoding="utf-8"))
    return {**funnel, "artifacts": artifacts}


@app.get("/api/funnel/{funnel_id}/status")
def funnel_status(funnel_id: str) -> dict:
    store = RunStore(DB_PATH)
    funnel = store.get_funnel(funnel_id)
    if not funnel:
        raise HTTPException(status_code=404, detail="Funnel not found")
    
    funnel_dir = FUNNELS_DIR / funnel_id
    artifacts = {}
    for name, key in [
        ("stage1_candidates.json", "stage1_candidates"),
        ("stage2_pilot.json", "stage2_pilot"),
        ("stage3_full.json", "stage3_full"),
        ("stage4_recommendation.json", "stage4_recommendation"),
    ]:
        path = funnel_dir / name
        if path.exists():
            artifacts[key] = json.loads(path.read_text(encoding="utf-8"))
    
    progress = run_manager.get_funnel_progress(funnel_id)
    return {"funnel": {**funnel, "artifacts": artifacts}, "progress": progress}


@app.post("/api/funnel/{funnel_id}/cancel")
async def cancel_funnel(funnel_id: str) -> dict:
    result = await run_manager.cancel_funnel(funnel_id)
    return result


@app.get("/api/runs/{run_id}/issues")
def api_run_issues(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    disagreement_only: bool = False,
    dataset_filter: str = "all",
) -> dict:
    store = RunStore(DB_PATH)
    manifest = store.get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Run not found")
    predictions_path = RUNS_DIR / run_id / "predictions.jsonl"
    if predictions_path.exists():
        store.index_predictions(run_id, predictions_path)
    scored_ids = manifest.get("sampled_issue_ids", [])
    rows, total = store.paginate_issues(
        run_id,
        offset=offset,
        limit=limit,
        disagreement_only=disagreement_only,
        model_a=manifest["model_a"],
        model_b=manifest["model_b"],
        dataset_filter=dataset_filter,
        scored_ids=scored_ids,
    )
    return {"items": rows, "total": total, "offset": offset, "limit": limit}


@app.get("/api/runs/{run_id}/issues/{issue_id}")
def api_issue_detail(run_id: str, issue_id: str) -> dict:
    detail = run_manager.get_issue_detail(run_id, issue_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Issue not found")
    return detail


@app.get("/api/runs/{run_id}/disagreements/export")
def export_disagreements(run_id: str) -> StreamingResponse:
    manifest = RunStore(DB_PATH).get_run(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Run not found")
    metrics = load_run_metrics(run_id)
    rows = metrics.get("comparison", {}).get("disagreements", [])
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["issue_id", "model_a", "model_a_label", "model_b", "model_b_label"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-disagreements.csv"'},
    )


@app.post("/api/runs")
async def start_run(body: StartRunRequest) -> dict:
    settings = get_settings()
    run_use_mock = body.use_mock
    if not run_use_mock and not body.confirm_spend:
        raise HTTPException(
            status_code=400,
            detail="Live inference requires confirm_spend=true (every classified issue is scored against ground truth).",
        )
    if not run_use_mock and not settings.do_api:
        raise HTTPException(status_code=400, detail="DO_API is required for live inference.")
    try:
        custom_settings = body.model_dump(exclude={"model_a", "model_b", "limit", "use_mock", "confirm_spend"}, exclude_none=True)
        manifest = await run_manager.start_run(
            body.model_a,
            body.model_b,
            limit=body.limit,
            use_mock=run_use_mock,
            custom_settings=custom_settings,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return manifest.model_dump()


@app.post("/api/classify/custom")
async def classify_custom_issue(body: CustomClassifyRequest) -> dict:
    settings = get_settings()
    run_use_mock = body.use_mock
    if not run_use_mock and not settings.do_api:
        raise HTTPException(status_code=400, detail="DO_API is required for live inference.")
    if body.model_a == body.model_b:
        raise HTTPException(status_code=400, detail="Model A and Model B must differ.")
    return await classify_custom(
        body.title,
        body.body,
        body.model_a,
        body.model_b,
        use_mock=run_use_mock,
    )


@app.get("/api/corpus/stats")
def corpus_stats() -> dict:
    settings = get_settings()
    corpus_root = settings.resolve_path(settings.corpus_path)
    version = latest_version(corpus_root, settings.github_repo)
    issues = load_issues_from_snapshot(corpus_root, settings.github_repo, version)
    return {"repo": settings.github_repo, "version": version, "count": len(issues)}


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        index = STATIC_DIR / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Frontend not built")
        return FileResponse(index)


def run_server() -> None:
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8080, reload=False)
