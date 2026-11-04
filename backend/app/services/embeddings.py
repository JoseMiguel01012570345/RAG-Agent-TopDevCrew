import hashlib
import math
import re
import time
import unicodedata

from opentelemetry import trace

from app.config import EMBEDDING_DIM, Settings, get_settings
from app.services.llm import (
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    map_provider_exception,
)

_TOKEN = re.compile(r"\w+", re.UNICODE)


class Embedder:
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class FakeEmbedder(Embedder):
    """Feature hashing determinista. No llama a la red y no cambia entre procesos."""

    def __init__(self, dim: int = EMBEDDING_DIM, model: str = "fake-hash-384") -> None:
        self.dim = dim
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)


class LiteLLMEmbedder(Embedder):
    def __init__(self, model: str, timeout: float, api_key: str | None) -> None:
        self.model = model
        self.timeout = timeout
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        litellm.telemetry = False
        try:
            response = litellm.embedding(
                model=self.model,
                input=texts,
                timeout=self.timeout,
                api_key=self.api_key,
            )
        except Exception as exc:
            raise map_provider_exception(exc) from exc
        data = response.data if hasattr(response, "data") else response["data"]
        vectors: list[list[float]] = []
        for item in data:
            raw = item["embedding"] if isinstance(item, dict) else item.embedding
            vectors.append(fit_dim(list(raw), EMBEDDING_DIM))
        return vectors


def build_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()
    provider = settings.embedding_provider
    if provider == "fake":
        return FakeEmbedder(model=settings.embedding_model or "fake-hash-384")
    if provider == "gemini":
        return LiteLLMEmbedder(
            model=settings.embedding_model or "gemini/text-embedding-004",
            timeout=settings.llm_timeout_seconds,
            api_key=settings.gemini_api_key,
        )
    raise ValueError(f"Proveedor de embeddings desconocido: {provider}")


def embed_texts(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    tracer = trace.get_tracer("faro")
    with tracer.start_as_current_span("rag.embed") as span:
        started = time.perf_counter()
        try:
            vectors = embedder.embed(texts)
        except (ProviderTimeout, ProviderRateLimit, ProviderError):
            span.set_attribute("gen_ai.request.model", embedder.model)
            span.set_attribute("faro.latency_ms", (time.perf_counter() - started) * 1000)
            raise
        elapsed = (time.perf_counter() - started) * 1000
        span.set_attribute("gen_ai.request.model", embedder.model)
        span.set_attribute("rag.input_count", len(texts))
        span.set_attribute("gen_ai.usage.input_tokens", _estimate_tokens(texts))
        span.set_attribute("faro.latency_ms", elapsed)
        return vectors


def fit_dim(values: list[float], dim: int) -> list[float]:
    if len(values) > dim:
        values = values[:dim]
    elif len(values) < dim:
        values = [*values, *([0.0] * (dim - len(values)))]
    return _normalize(values)


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


def _tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFD", text.lower())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return [token for token in _TOKEN.findall(folded) if len(token) >= 3]


def _estimate_tokens(texts: list[str]) -> int:
    return sum(max(len(text) // 4, 1) for text in texts)


def to_pgvector(values: list[float]) -> str:
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Embedding con valores no finitos")
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
