import json
import re
import time
from dataclasses import dataclass

from app.services.textutil import content_tokens, overlap_tokens

DOC_SPLIT = "<<<DOC>>>"
DOC_END = "<<<END>>>"


class ProviderTimeout(Exception):
    pass


class ProviderRateLimit(Exception):
    pass


class ProviderError(Exception):
    pass


class InvalidModelOutput(Exception):
    pass


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLMClient:
    model: str

    def complete(self, system: str, user: str) -> LLMResult:
        raise NotImplementedError


class FakeLLM(LLMClient):
    """Responde solo con fragmentos del prompt. No obedece instrucciones del documento."""

    def __init__(self, model: str = "fake-answer") -> None:
        self.model = model

    def complete(self, system: str, user: str) -> LLMResult:
        started = time.perf_counter()
        payload = _answer_from_prompt(user)
        text = json.dumps(payload, ensure_ascii=False)
        elapsed = (time.perf_counter() - started) * 1000
        return LLMResult(
            text=text,
            model=self.model,
            input_tokens=max(len(system + user) // 4, 1),
            output_tokens=max(len(text) // 4, 1),
            latency_ms=elapsed,
        )


class LiteLLMClient(LLMClient):
    def __init__(
        self,
        model: str,
        timeout: float,
        api_key: str | None,
        *,
        json_mode: bool = False,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.api_key = api_key
        self.json_mode = json_mode

    def complete(self, system: str, user: str) -> LLMResult:
        import litellm

        litellm.telemetry = False
        started = time.perf_counter()
        kwargs: dict[str, object] = {}
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=self.timeout,
                temperature=0,
                api_key=self.api_key,
                **kwargs,
            )
        except Exception as exc:
            raise map_provider_exception(exc) from exc
        message = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResult(
            text=message,
            model=self.model,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


def build_llm(settings=None) -> LLMClient:
    from app.config import get_settings

    settings = settings or get_settings()
    if settings.llm_provider == "fake":
        return FakeLLM(model=settings.llm_model or "fake-answer")
    if settings.llm_provider == "gemini":
        return LiteLLMClient(
            model=settings.llm_model or "gemini/gemini-2.0-flash",
            timeout=settings.llm_timeout_seconds,
            api_key=settings.gemini_api_key,
        )
    if settings.llm_provider == "openai":
        return LiteLLMClient(
            model=settings.llm_model or "gpt-4o-mini",
            timeout=settings.llm_timeout_seconds,
            api_key=settings.openai_api_key,
        )
    if settings.llm_provider == "groq":
        return LiteLLMClient(
            model=settings.llm_model or "groq/openai/gpt-oss-120b",
            timeout=settings.llm_timeout_seconds,
            api_key=settings.groq_api_key,
            json_mode=True,
        )
    raise ValueError(f"Proveedor LLM desconocido: {settings.llm_provider}")


def map_provider_exception(exc: Exception) -> Exception:
    name = exc.__class__.__name__.lower()
    module = exc.__class__.__module__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return ProviderTimeout(str(exc))
    if "ratelimit" in name or "rate limit" in text or "429" in text:
        return ProviderRateLimit(str(exc))
    if "litellm" in module or "openai" in module or "gemini" in module:
        return ProviderError(str(exc))
    return ProviderError(str(exc))


def _answer_from_prompt(user: str) -> dict:
    question = _question(user)
    documents = _documents(user)
    question_tokens = overlap_tokens(question)
    ranked = []
    for document in documents:
        shared = question_tokens & overlap_tokens(document["text"])
        if shared:
            ranked.append((len(shared), document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen = [document for _, document in ranked[:3]]
    if not chosen:
        return {
            "answer": "No encuentro evidencia suficiente en los documentos de esta comunidad.",
            "citations": [],
            "sufficient_evidence": False,
        }
    prefix = ""
    if len(chosen) >= 2:
        prefix = (
            "Hay más de un fragmento relevante. Si se contradicen, no elijo un ganador jurídico. "
        )
    answer = prefix + " ".join(document["text"][:240] for document in chosen)
    citations = [
        {
            "document_id": document["id"],
            "document_name": document["nombre"],
            "page": int(document["pagina"]),
            "fragment": document["text"][:400],
        }
        for document in chosen
    ]
    return {"answer": answer, "citations": citations, "sufficient_evidence": True}


def _question(user: str) -> str:
    match = re.search(r"Pregunta:\n(.*)\n\nFragmentos:", user, re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _documents(user: str) -> list[dict[str, str]]:
    documents = []
    for part in user.split(DOC_SPLIT)[1:]:
        body = part.split(DOC_END)[0]
        meta: dict[str, str] = {}
        text_lines: list[str] = []
        in_text = False
        for line in body.splitlines():
            if in_text:
                text_lines.append(line)
                continue
            if line == "texto:":
                in_text = True
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        meta["text"] = "\n".join(text_lines).strip()
        if meta.get("id") and meta.get("text"):
            documents.append(meta)
    return documents


def usable_tokens(text: str) -> list[str]:
    return content_tokens(text)
