"""Model catalog and production recommendations."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from config import ROOT_DIR, get_settings

CATALOG_PATH = ROOT_DIR / "config" / "models_catalog.json"
RECOMMENDATIONS_PATH = ROOT_DIR / "config" / "recommendations.json"

# Slug prefixes for models that are NOT open-weight chat models. Used to filter
# the live DO /v1/models list so the UI dropdown only shows open-weight chat
# models. Closed-source frontier (Anthropic, OpenAI GPT/o-series), embeddings,
# image/video gen, TTS, and routers are excluded.
_EXCLUDED_PREFIXES = (
    "anthropic-",          # Claude — closed-source
    "openai-gpt-",         # GPT-4/5 — closed-source (openai-gpt-oss- is open-weight, handled separately)
    "openai-o1",           # o1 reasoning — closed-source
    "openai-o3",           # o3 reasoning — closed-source
    "openai-gpt-image-",   # image gen
    "stable-diffusion-",   # image gen
    "wan2-",               # video gen
    "qwen3-tts-",          # TTS
    "qwen3-embedding-",    # embedding
    "all-mini-lm-",        # embedding
    "bge-",                # embedding
    "e5-",                 # embedding
    "gte-",                # embedding
    "multi-qa-",           # embedding
    "router:",             # router
)

# Size class thresholds in billions of parameters.
_SIZE_THRESHOLDS = (
    ("small", 8),
    ("medium", 20),
    ("large", 70),
    ("very_large", 10_000),
)

# Family detection: maps a slug prefix to a family name.
_FAMILY_PATTERNS = (
    ("alibaba-qwen", "qwen"),
    ("qwen", "qwen"),
    ("deepseek", "deepseek"),
    ("llama", "llama"),
    ("mistral", "mistral"),
    ("gemma", "gemma"),
    ("glm", "glm"),
    ("kimi", "kimi"),
    ("mimo", "mimo"),
    ("minimax", "minimax"),
    ("nemotron", "nemotron"),
    ("nvidia-nemotron", "nemotron"),
    ("openai-gpt-oss", "gpt-oss"),
    ("arcee", "arcee"),
)

_REASONING_HINTS = ("thinking", "r1", "reasoning", "reason")
_INSTRUCT_HINTS = ("instruct", "-it", "-chat", "maverick", "flash", "omni")


def _is_open_weight_chat(slug: str) -> bool:
    """True if slug is an open-weight chat model (not closed-source, not embedding/image/etc)."""
    # openai-gpt-oss-* are open-weight (gpt-oss-120b, gpt-oss-20b) — allow them.
    if slug.startswith("openai-gpt-oss-"):
        return True
    if slug.startswith(_EXCLUDED_PREFIXES):
        return False
    return True


def _parse_parameter_b(slug: str) -> int:
    """Extract parameter count (in billions) from a slug. Returns 0 if unknown."""
    # Match patterns like "32b", "120b", "14B", "397b-a17b" (MoE: total-active), "550b".
    match = re.search(r"(\d+(?:\.\d+)?)b", slug, re.IGNORECASE)
    if match:
        return int(float(match.group(1)))
    return 0


def _size_class(parameter_b: int) -> str:
    for label, threshold in _SIZE_THRESHOLDS:
        if parameter_b <= threshold:
            return label
    return "very_large"


def _family(slug: str) -> str:
    for prefix, family in _FAMILY_PATTERNS:
        if slug.startswith(prefix):
            return family
    # Fallback: use the first token before a digit/dash.
    return slug.split("-")[0]


def _is_reasoning(slug: str) -> bool:
    lowered = slug.lower()
    return any(hint in lowered for hint in _REASONING_HINTS)


def _is_instruct(slug: str) -> bool:
    lowered = slug.lower()
    return any(hint in lowered for hint in _INSTRUCT_HINTS)


def tag_model(slug: str) -> dict:
    """Return metadata for a slug, preferring the static catalog and inferring the rest.

    The static catalog carries hand-curated family/role/cache tags; anything not
    in the catalog is auto-tagged by parsing the slug so live-only models still
    get stratified correctly.
    """
    catalog = load_catalog()
    for entry in catalog.get("candidates", []):
        if entry.get("slug") == slug:
            return {
                "slug": slug,
                "family": entry.get("family", _family(slug)),
                "parameter_b": entry.get("parameter_b", _parse_parameter_b(slug)),
                "size_class": entry.get("size_class", _size_class(_parse_parameter_b(slug))),
                "reasoning": entry.get("reasoning", _is_reasoning(slug)),
                "instruct": entry.get("instruct", _is_instruct(slug)),
                "open_weight": entry.get("open_weight", True),
                "cache_supported": slug in catalog.get("cache_supported_slugs", []),
                "role": entry.get("role", "Available on DO Serverless Inference"),
            }
    # Auto-tag from the slug.
    parameter_b = _parse_parameter_b(slug)
    return {
        "slug": slug,
        "family": _family(slug),
        "parameter_b": parameter_b,
        "size_class": _size_class(parameter_b),
        "reasoning": _is_reasoning(slug),
        "instruct": _is_instruct(slug),
        "open_weight": True,
        "cache_supported": slug in load_catalog().get("cache_supported_slugs", []),
        "role": "Available on DO Serverless Inference",
    }


def stratified_select(slugs: list[str], k: int = 6) -> list[dict]:
    """Pick up to `k` representative models covering the capability spectrum.

    Groups by (size_class, reasoning) and picks one representative per group,
    preferring instruct variants and (tie-break) the smallest parameter count
    within the group for cost coverage. Returns a list with a `selection_reason`
    field explaining why each model was chosen.
    """
    tagged = [tag_model(s) for s in slugs if _is_open_weight_chat(s)]
    # Group by (size_class, reasoning).
    groups: dict[tuple[str, bool], list[dict]] = {}
    for m in tagged:
        key = (m["size_class"], m["reasoning"])
        groups.setdefault(key, []).append(m)

    # Order groups so the most distinct capability tiers come first: small,
    # very_large, then reasoning, then medium/large.
    order = {
        ("small", False): 0,
        ("very_large", False): 1,
        ("medium", True): 2,
        ("large", True): 3,
        ("very_large", True): 4,
        ("medium", False): 5,
        ("large", False): 6,
    }

    def group_sort_key(key: tuple[str, bool]) -> int:
        return order.get(key, 99)

    selected: list[dict] = []
    for key in sorted(groups.keys(), key=group_sort_key):
        if len(selected) >= k:
            break
        bucket = groups[key]
        # Prefer instruct, then smallest parameter_b (cost coverage), then slug alpha.
        bucket.sort(key=lambda m: (not m["instruct"], m["parameter_b"], m["slug"]))
        chosen = bucket[0]
        size_label, reasoning = key
        reason = f"Covers the {size_label} tier" + (" with reasoning" if reasoning else "")
        chosen = {**chosen, "selection_reason": reason}
        selected.append(chosen)
    return selected[:k]


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_recommendations() -> dict:
    return json.loads(RECOMMENDATIONS_PATH.read_text(encoding="utf-8"))


def list_comparison_models() -> list[dict]:
    catalog = load_catalog()
    return [entry for entry in catalog.get("candidates", []) if entry.get("open_weight", True)]


async def fetch_live_models() -> list[str]:
    settings = get_settings()
    if not settings.do_api:
        return [entry["slug"] for entry in list_comparison_models()]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{settings.si_api_base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {settings.do_api}"},
            )
            response.raise_for_status()
            payload = response.json()
            return [item["id"] for item in payload.get("data", [])]
    except Exception:
        return [entry["slug"] for entry in list_comparison_models()]


async def get_models_for_ui() -> list[dict]:
    catalog = load_catalog()
    cache_slugs = set(catalog.get("cache_supported_slugs", []))
    live_slugs = await fetch_live_models()
    live_set = set(live_slugs)

    models: list[dict] = []
    seen: set[str] = set()

    for entry in list_comparison_models():
        slug = entry["slug"]
        seen.add(slug)
        models.append(
            {
                **entry,
                "available": slug in live_set if live_set else True,
                "cache_supported": slug in cache_slugs or entry.get("cache_supported", False),
            }
        )

    for slug in sorted(live_set):
        if slug in seen:
            continue
        if not _is_open_weight_chat(slug):
            continue
        seen.add(slug)
        models.append(
            {
                "slug": slug,
                "tier": "live",
                "open_weight": True,
                "cache_supported": slug in cache_slugs,
                "parameter_class": "—",
                "role": "Available on DO Serverless Inference",
                "available": True,
            }
        )

    if not models:
        recs = load_recommendations()
        for slug in {recs.get("model_a"), recs.get("model_b")} - {None}:
            models.append(
                {
                    "slug": slug,
                    "tier": "fallback",
                    "open_weight": True,
                    "cache_supported": slug in cache_slugs,
                    "parameter_class": "—",
                    "role": "Configured recommendation",
                    "available": True,
                }
            )

    return models
