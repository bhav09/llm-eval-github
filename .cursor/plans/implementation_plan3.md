# Implementation Plan — Resolving Label Tagging Bottlenecks

## Goal
Improve the ground-truth labeling pipeline by resolving key bottlenecks and limitations in issue classification:
1. **Reduce LLM adjudication routing** by implementing a score-based heuristic density tie-breaker.
2. **Prevent silent mislabeling** by validating native labels against text-based heuristics.
3. **Incorporate thread/comment context** by fetching and cache-storing GitHub issue comments for ambiguous cases.
4. **Ensure 100% decision reproducibility** for unchanged issues by caching LLM adjudication results.

---

## Proposed Changes

### Component 1: Score-based Density Resolution & Heuristic Overrides

#### [MODIFY] [rules_engine.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/ground_truth/rules_engine.py)
Update `_heuristic_label` to perform density scoring and priority overrides:
- If multiple heuristic patterns match the text, calculate a match score for each category (count of matching regex patterns in the title + body).
- **Security Override:** If `"security"` matches via a high-value pattern (like `CVE-` or `GHSA-`), automatically select `"security"` regardless of other matches.
- **Density Tie-Breaker:** Sort categories by score. If the highest score is $\ge 2$ times the second-highest score (or the score difference is $\ge 2$), resolve the conflict deterministically in favor of the highest-scoring category.
- When resolved via density scoring, classify the issue with `confidence = "MED"` (meaning it bypasses the ambiguous LLM queue but has a lower confidence than native label matches).

---

### Component 2: Native-Heuristic Cross-Validation

#### [MODIFY] [rules_engine.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/ground_truth/rules_engine.py)
Update `classify_with_rules` to validate mapped native labels against the resolved text heuristics:
- Mapped native labels are currently mapped as `confidence = "HIGH"`.
- If both a mapped native label and a resolved text heuristic (either single or resolved via density scoring) exist, compare them:
  - If they **conflict** (e.g. native label says `bug` but text heuristics indicate `question`), demote the confidence to `"LOW"` and set `proposed_label = None` with a conflict reason.
  - This routes the conflict directly to the LLM adjudicator for validation, preventing silent maintainer mislabeling.
- If multiple conflicting native labels are assigned (e.g. both `bug` and `enhancement`), do not prioritize them statically; instead, route them to the LLM as low confidence.

---

### Component 3: Comment-Aware Ingestion and Adjudication

#### [MODIFY] [github_client.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/ingestion/github_client.py)
Add a method to fetch comments for a specific issue number:
```python
    def fetch_issue_comments(self, repo: str, issue_number: int) -> list[dict]:
        owner, name = repo.split("/", 1)
        try:
            response = self._client.get(f"/repos/{owner}/{name}/issues/{issue_number}/comments")
            response.raise_for_status()
            return response.json()
        except Exception:
            return []
```

#### [MODIFY] [pipeline.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/ground_truth/pipeline.py)
Integrate comment context into the LLM adjudication step:
- For issues entering the ambiguous queue, if a `GITHUB_TOKEN` is configured, fetch the issue's comments.
- Extract comments from the original author and maintainers/collaborators.
- Format the last 3 comments (excluding system automated comments) into a text block: `Comments:\n- User: ...\n- Maintainer: ...`
- Cache fetched comments in `data/ground_truth/comments_cache.json` (indexed by `issue_id`) to avoid redundant API requests in subsequent runs.
- Append comments context to the text sent to the LLM adjudicator.

---

### Component 4: Ground Truth Decision Caching

#### [MODIFY] [pipeline.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/ground_truth/pipeline.py)
Implement local caching of LLM adjudication results:
- Create `data/ground_truth/adjudication_cache.json` to store past decisions.
- Calculate a SHA-256 hash of the input context (title + body + comments).
- If the hash matches a cached decision, reuse the label and rationale directly without invoking the LLM API.
- This guarantees 100% reproducibility across identical pipeline runs and reduces token costs.

---

## Verification Plan

### Automated Tests
- Create a test file `tests/test_pipeline_refinements.py` covering:
  - Density-based heuristic conflict resolution (e.g. 3 bug hits vs 1 documentation hit).
  - Native-heuristic conflict demotion (e.g. native label `bug` demoted due to heuristic `question` patterns).
  - Caching logic (reusing results based on content hashes).
- Run `pytest tests/ -v` to ensure all tests pass.

### Manual Verification
- Run `python -m ground_truth.pipeline` to check metrics (total resolved by rules vs. routed to LLM).
- Verify that `labels.json` lists the new conflict resolution reasons and cache hits correctly.
