"""Local text embeddings for GraphRAG (BAAI/bge-small-en-v1.5, 384-d, cosine)."""

from functools import cache

from redthread.config import EMBEDDING_DIM, EMBEDDING_MODEL

# bge models expect this instruction on queries (not on the passages being searched).
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@cache
def _model():
    from sentence_transformers import SentenceTransformer  # heavy import; only when embedding

    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def embed_passages(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    vectors = _model().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 500)
    assert vectors.shape[1] == EMBEDDING_DIM
    return vectors.round(6).tolist()


def embed_query(text: str) -> list[float]:
    return _model().encode(QUERY_INSTRUCTION + text, normalize_embeddings=True).round(6).tolist()
