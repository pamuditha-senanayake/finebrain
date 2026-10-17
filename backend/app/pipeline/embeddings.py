# embeddings.py: Voyage AI embeddings and rerank over plain HTTP, with retry. Used for S5 retrieval.
# Used by: adapters.py (real "voyage" part), scripts/smoke_voyage.py. Uses: retry.py. Reads keys from the environment.
import os

import httpx

from app.pipeline.retry import call_with_retry

# Config
VOYAGE_BASE_URL = os.environ.get("VOYAGE_BASE_URL", "https://api.voyageai.com/v1")
EMBED_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3.5")
RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2.5")
TIMEOUT_SECONDS = 10
ATTEMPTS = 3


class VoyageError(Exception):
    """Voyage answered with a rate limit or a server error. Worth another try."""
    retryable = True


def is_retryable(error: Exception) -> bool:
    return isinstance(error, (VoyageError, httpx.TimeoutException, httpx.TransportError))


def post(path: str, body: dict) -> dict:
    """One Voyage call. 429 and 5xx raise VoyageError so the caller can retry; other errors raise at once."""
    response = httpx.post(
        f"{VOYAGE_BASE_URL}{path}", json=body, timeout=TIMEOUT_SECONDS,
        headers={"Authorization": f"Bearer {os.environ['VOYAGE_API_KEY']}"},
    )
    if response.status_code == 429 or response.status_code >= 500:
        raise VoyageError(f"voyage {path} answered {response.status_code}")
    response.raise_for_status()
    return response.json()


def voyage_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """One vector per text. input_type is "query" for questions, "document" for stored chunks."""
    reply = call_with_retry(lambda: post("/embeddings", {"model": EMBED_MODEL, "input": texts, "input_type": input_type}), is_retryable, attempts=ATTEMPTS)
    return [item["embedding"] for item in sorted(reply["data"], key=lambda item: item["index"])]


def voyage_rerank(query: str, documents: list[str]) -> list[float]:
    """One relevance score per document, in the order given."""
    reply = call_with_retry(lambda: post("/rerank", {"model": RERANK_MODEL, "query": query, "documents": documents}), is_retryable, attempts=ATTEMPTS)
    scores = [0.0] * len(documents)
    for item in reply["data"]:
        scores[item["index"]] = item["relevance_score"]
    return scores
