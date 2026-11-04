import math

from app.config import EMBEDDING_DIM
from app.services.embeddings import FakeEmbedder, fit_dim


def test_fake_embeddings_are_deterministic_and_normalized():
    embedder = FakeEmbedder()
    first = embedder.embed(["Reparación del ascensor"])[0]
    second = embedder.embed(["Reparación del ascensor"])[0]
    other = embedder.embed(["horario de piscina climatizada"])[0]
    assert first == second
    assert len(first) == EMBEDDING_DIM
    assert other != first
    norm = math.sqrt(sum(value * value for value in first))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_fit_dim_truncates_and_normalizes():
    fitted = fit_dim([3.0, 0.0, 4.0], 2)
    assert len(fitted) == 2
    norm = math.sqrt(sum(value * value for value in fitted))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)
