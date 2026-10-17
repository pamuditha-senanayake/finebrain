# smoke_voyage.py: one real Voyage embed call and one real rerank call, to prove the key and models work for S5.
# Run from backend/: uv run python -m scripts.smoke_voyage   (costs a fraction of a cent)
# Uses: app/pipeline/embeddings.py, scripts/test_keys.py (load_env_file). Reads backend/.env, never prints keys.
from scripts.test_keys import ENV_PATH, load_env_file

# Config
QUERY = "How many days does a customer have to ask for a refund?"
DOCUMENTS = [
    "Customers may request a refund within 30 days of the purchase date.",
    "Approved refunds are paid to the original payment method within 7 working days.",
    "Our office is closed on public holidays.",
]


def main() -> None:
    load_env_file(ENV_PATH)
    from app.pipeline import embeddings  # imported after .env is loaded, so its config sees the values

    vectors = embeddings.voyage_embed(DOCUMENTS, "document")
    print(f"embed  -> {len(vectors)} vectors of size {len(vectors[0])}")
    scores = embeddings.voyage_rerank(QUERY, DOCUMENTS)
    for document, score in sorted(zip(DOCUMENTS, scores), key=lambda pair: -pair[1]):
        print(f"rerank -> {score:.3f}  {document}")


if __name__ == "__main__":
    main()
