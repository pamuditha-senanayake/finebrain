# lab_embed.py: embeddings in a lab, as Execution_V1's frozen config has them: each string embedded once (cached in the
# process, and patient when the embedding service rate limits), the pack embedded ahead in calls under its token limit, and
# no reranker. Used by: research/freshness_lab.py, tests/test_research_runner.py. Uses: stages_file.py (how S11 cuts chunks).
import threading
import time

from app.pipeline import stages_file

# Config
EMBED_WAITS = [5, 10, 20, 30, 60, 60, 60, 60, 60, 60, 60, 60]  # seconds between tries when the embedding service says 429
EMBED_BATCH_TOKENS = 8_000  # per call when the lab embeds a pack ahead of time: under Voyage's 10,000 tokens a minute
CHARS_PER_TOKEN = 3  # French and accented text run near 3; at 4 a French batch passed the minute's limit and could never succeed


EMBEDDED: dict[tuple[str, str], list[float]] = {}
EMBEDDED_LOCK = threading.Lock()


def once_each(embed, sleep=time.sleep):
    """The lane's embedder, asked only for strings it has not embedded before, waiting out a rate limit instead of failing."""
    def cached(texts: list[str], input_type: str = "document") -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if (t, input_type) not in EMBEDDED]
        if missing:
            vectors = patiently(lambda: embed(missing, input_type), sleep)
            with EMBEDDED_LOCK:
                EMBEDDED.update({(t, input_type): v for t, v in zip(missing, vectors)})
        return [EMBEDDED[(t, input_type)] for t in texts]
    return cached


def patiently(call, sleep):
    for wait in [*EMBED_WAITS, None]:
        try:
            return call()
        except Exception as error:
            if wait is None or not getattr(error, "retryable", False):
                raise
            sleep(wait)


def batches(texts: list[str]) -> list[list[str]]:
    """Consecutive groups of about EMBED_BATCH_TOKENS each."""
    groups, current, size = [], [], 0
    for text in texts:
        tokens = len(text) // CHARS_PER_TOKEN + 1
        if current and size + tokens > EMBED_BATCH_TOKENS:
            groups.append(current)
            current, size = [], 0
        current.append(text)
        size += tokens
    return groups + ([current] if current else [])


def embed_ahead(lane, pack: dict, beat=lambda: None) -> None:
    """Embed the pack's chunk texts (as S11 will cut them: S2 hands it the text on one line) and its questions in a few large
    calls, as Execution_V1 embedded everything once up front. S11 and S5 then find them in the cache; a chunk that masking
    changed is simply embedded when S11 asks for it."""
    chunks = [f"{doc['meta'].title}: {part}" for doc in pack["documents"].values() for part in stages_file.chunks_of(" ".join(doc["body"].split()))]
    questions = [q.text for q in pack["main"]]
    embed_texts(lane, chunks, beat)
    embed_texts(lane, questions, beat, "query")


def embed_texts(lane, texts: list[str], beat=lambda: None, kind: str = "document") -> None:
    """Texts the lane will ask for one at a time, embedded now in calls under the token limit (the cache keeps them)."""
    for group in batches(texts):
        lane.embed(group, kind)
        beat()


def keep_order(query: str, texts: list[str]) -> list[float]:
    """No reranker: S5 keeps its fused order."""
    return [float(len(texts) - i) for i in range(len(texts))]
