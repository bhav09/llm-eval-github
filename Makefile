.PHONY: install test fetch-corpus build-ground-truth run-eval ui-install ui-build ui-dev serve docker-build

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

fetch-corpus:
	python -m ingestion.fetch

build-ground-truth:
	python -m ground_truth.pipeline --mock-llm

run-eval:
	python -m eval.run --mock --limit 20

ui-install:
	cd frontend && npm install

ui-build:
	cd frontend && npm run build

ui-dev:
	cd frontend && npm run dev

serve: ui-build
	uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

docker-build:
	docker build -t fde-eval .
