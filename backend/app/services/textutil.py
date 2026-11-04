import re
import unicodedata

SPANISH_STOPWORDS = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "de",
        "del",
        "al",
        "y",
        "o",
        "u",
        "que",
        "en",
        "con",
        "por",
        "para",
        "su",
        "sus",
        "es",
        "son",
        "se",
        "lo",
        "como",
        "mas",
        "pero",
        "si",
        "no",
        "ya",
        "muy",
        "tambien",
        "este",
        "esta",
        "estos",
        "estas",
        "ese",
        "esa",
        "eso",
        "aqui",
        "alli",
        "sobre",
        "entre",
        "hasta",
        "desde",
        "cuando",
        "donde",
        "cual",
        "quien",
        "quienes",
        "hay",
        "fue",
        "fueron",
        "ser",
        "estar",
        "esta",
        "estan",
        "ha",
        "han",
        "haber",
        "porque",
        "les",
        "nos",
        "te",
        "me",
        "mi",
        "tu",
        "sin",
        "tras",
        "durante",
        "mediante",
        "segun",
        "the",
        "and",
        "dice",
        "dijo",
        "documento",
        "documentos",
    }
)

_TOKEN = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}")


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def content_tokens(text: str) -> list[str]:
    seen: list[str] = []
    known: set[str] = set()
    for token in _TOKEN.findall(text):
        lowered = token.lower()
        folded = fold(lowered)
        if folded in SPANISH_STOPWORDS or folded in known:
            continue
        known.add(folded)
        seen.append(lowered)
    return seen


def overlap_tokens(text: str) -> set[str]:
    return {fold(token) for token in content_tokens(text)}


def lexical_query(question: str, limit: int = 16) -> str | None:
    tokens = content_tokens(question)[:limit]
    if not tokens:
        return None
    safe = [re.sub(r"[|&!:*()<>']", "", token) for token in tokens]
    safe = [token for token in safe if token]
    if not safe:
        return None
    return " | ".join(safe)
