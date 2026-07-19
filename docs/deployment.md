# Deployment on DigitalOcean

## Target platform

**DigitalOcean App Platform** — single container from the repo `Dockerfile`.

The PDF requires a **public URL** in the README. Inference must use **DO Serverless Inference** (`DO_API`). The database is **SQLite file storage** inside the app — not a separate DO Managed Database (not required by the PDF).

---

## App Platform setup

### 1. Create the app

```bash
doctl auth init
doctl apps create --spec .do/app.yaml
```

Or via Control Panel: **Apps → Create App → GitHub → select repo**.

### 2. Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DO_API` | Yes (live runs) | Serverless Inference key — **SECRET** |
| `GITHUB_TOKEN` | Optional | Corpus refresh only |
| `CONCURRENCY` | No | Default `8` |
| `CHECKPOINT_EVERY_N` | No | Default `50` |

### 3. Health checks

- `GET /health` — process alive (App Platform health check)
- `GET /ready` — corpus + ground truth loaded

### 4. Persistence

Eval results write to `results/eval.db` and `results/runs/`. On App Platform:

- **Option A (demo):** Ship canonical run in the image (current Dockerfile copies `results/`)
- **Option B (live runs):** Attach a **DO Volume** mounted at `/app/results`

---

## Local Docker smoke test

```bash
docker build -t fde-eval .
docker run -p 8080:8080 --env-file .env fde-eval
curl http://localhost:8080/health
curl http://localhost:8080/ready
open http://localhost:8080
```

---

## Spend guard

The UI defaults to **mock inference** for pilots. Full-corpus live runs require `confirm_spend=true` via API or unchecking mock + selecting full corpus in the UI (with confirmation).

Preloaded runs in `results/runs/` let reviewers inspect metrics without spending credits.

---

## Architecture (single container)

```
Browser → App Platform (uvicorn :8080)
              ├── /api/*     FastAPI JSON
              ├── /health
              └── /*         React SPA (static/)
Inference → DO Serverless Inference (external)
Storage   → SQLite + JSONL (local/volume)
```
