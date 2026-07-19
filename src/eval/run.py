"""CLI entry point for eval runs."""

from __future__ import annotations

import argparse
import asyncio

from eval.orchestrator import EvalOrchestrator
from observability.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dual-model issue classification eval")
    parser.add_argument("--model-a", default="mock-model-a", help="First model slug")
    parser.add_argument("--model-b", default="mock-model-b", help="Second model slug")
    parser.add_argument("--mock", action="store_true", help="Use mock classifier (no API calls)")
    parser.add_argument("--limit", type=int, default=None, help="Limit issues for pilot runs")
    args = parser.parse_args()

    configure_logging()
    orchestrator = EvalOrchestrator()
    manifest = asyncio.run(
        orchestrator.run_from_corpus(
            args.model_a,
            args.model_b,
            use_mock=args.mock or args.model_a.startswith("mock"),
            limit=args.limit,
        )
    )
    print(f"Run complete: {manifest.run_id}")
    print(f"Status: {manifest.status}")
    print(f"Completed: {manifest.completed}/{manifest.total}")


if __name__ == "__main__":
    main()
