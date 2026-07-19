"""Event name constants for observability."""

CORPUS_FETCH_START = "corpus.fetch.start"
CORPUS_FETCH_PAGE = "corpus.fetch.page"
CORPUS_FETCH_COMPLETE = "corpus.fetch.complete"
CORPUS_VALIDATION_PASS = "corpus.validation.pass"
CORPUS_VALIDATION_FAIL = "corpus.validation.fail"
CORPUS_LOAD_COMPLETE = "corpus.load.complete"

GT_RULES_COMPLETE = "ground_truth.rules.complete"
GT_LLM_START = "ground_truth.llm.start"
GT_LLM_ISSUE = "ground_truth.llm.issue"
GT_PIPELINE_COMPLETE = "ground_truth.pipeline.complete"

INFERENCE_COMPLETE = "inference.complete"
METRICS_COMPUTE_START = "metrics.compute.start"
METRICS_COMPUTE_COMPLETE = "metrics.compute.complete"
EVAL_RUN_COMPLETE = "eval.run.complete"
