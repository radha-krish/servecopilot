import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384 dims: must match vector(384)
# bge was trained with this prefix on queries only (never on documents).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def load_model():
    device = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    return SentenceTransformer(MODEL_NAME, device=device)


def embed_documents(model, texts, batch_size=64):
    return model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )


def embed_query(model, text):
    return model.encode(QUERY_PREFIX + text, normalize_embeddings=True)
