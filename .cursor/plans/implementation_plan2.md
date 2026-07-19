# Implementation Plan - Adjudicator Model Switch & Ground Truth Pipeline Improvements

## Goal
Switch the ground-truth adjudicator LLM to **`deepseek-v4-pro`** (a super intelligent frontier model verified to work on the current subscription tier, which is excluded from the open-weight model selection benchmark) and address the identified blind spots and bottlenecks in the labeling pipeline.

---

## Proposed Changes

### Component 1: Adjudicator Model Configuration

#### [MODIFY] [config.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/config.py)
Change the default adjudicator model from `"alibaba-qwen3-32b"` to **`"deepseek-v4-pro"`**:
```python
    adjudicator_model: str = Field(
        default="deepseek-v4-pro",
        alias="ADJUDICATOR_MODEL",
    )
```
*Rationale:* Live API checks revealed that the `openai-gpt-4o` model is not available under the current subscription tier (`forbidden_error`). Probing the available models confirmed that **`deepseek-v4-pro`** is fully authorized and works correctly. Since it is a proprietary frontier model, it is excluded from the open-weight chat model selection tests, satisfying all constraints.

---

### Component 2: Rules Engine Refinement (Conflict Delegation)

#### [MODIFY] [rules_engine.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/ground_truth/rules_engine.py)
Modify `classify_with_rules` to delegate multi-hit conflicts to the LLM adjudicator:
- **Single regex pattern hit:** Classify as `confidence = "MED"` (queue for LLM verification).
- **Multiple pattern hits:** Classify as `confidence = "LOW"`, `proposed_label = None`, and `mapping_reason = "conflicting heuristics: <hits>"`. This forces the issue into the LLM queue to be resolved by the super-intelligent model instead of a rigid priority rule.

---

### Component 3: Prompt Enrichment & Guidelines

#### [MODIFY] [ground_truth_adjudication_v1.txt](file:///Users/bhavishya/VSC Projects/llm-eval-github/config/ground_truth_adjudication_v1.txt)
We will expand the concise system prompt into a comprehensive, high-quality labeling guideline:
1. **Explicit Label Definitions:**
   - `bug`: Code failures, compilation errors, panics, crashes, incorrect outputs, or unexpected behavior.
   - `enhancement`: Feature requests, performance optimizations, additions of new flags/commands.
   - `question`: Troubleshooting help, user configuration queries, asking for instructions.
   - `documentation`: Typos in readmes/docs, missing tutorials, inline code comment corrections.
   - `security`: CVEs, dependency vulnerability warnings, authentication failures, credential leaks.
   - `other`: Duplicate issues, admin tasks, CI/CD setup, cleanup chores.
2. **Edge-case Rules:**
   - Typo in README is `documentation`, not a `bug`.
   - Setup/installation issues are `other` or `question`, not a `bug`, unless a bug in the install script is found.
3. **Few-Shot Examples:** Provide two clear inputs and JSON outputs illustrating the taxonomy.

---

### Component 4: Smart Context Truncation (Preserving Tracebacks)

#### [MODIFY] [context.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/inference/context.py)
We will implement **Smart Middle Truncation**:
- If the issue body exceeds the character limit (e.g., `8000` characters):
  - Extract the first `4000` characters (typically containing the user description and context).
  - Extract the last `3800` characters (typically containing the stack trace, traceback, and error exit logs).
  - Concatenate them with a middle marker: `\n\n... [TRUNCATED LOGS/STACK TRACE CONTD.] ...\n\n`.
  - This ensures the adjudicator sees both the user's initial description and the final error trace.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/ -v` to ensure the rules engine adjustments and context truncation logic pass. We will add a unit test checking that conflicting heuristics are delegated as `confidence = "LOW"` rather than being resolved by priority.

### Manual Verification
- Run a ground-truth pipeline test run (using the live API key) and inspect `labels.json` to confirm that:
  - Ambiguous regex hits are correctly resolved by `deepseek-v4-pro`.
  - The rationalize strings demonstrate the new guidelines are followed.
