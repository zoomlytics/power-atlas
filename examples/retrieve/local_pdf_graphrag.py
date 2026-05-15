import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

VALID_DOC_TYPES = {"all", "facts", "narrative"}


@dataclass(frozen=True)
class PromptTemplate:
    template: str


QA_PROMPT_TEMPLATE = PromptTemplate(
    template=(
        "Use the provided context to answer the user question.\n"
        "Every bullet MUST end with a citation.\n"
        "Context:\n{context}\n\n"
        "Question:\n{query_text}\n\n"
        "Examples:\n{examples}"
    )
)


def _normalize_doc_type(doc_type: str | None) -> str | None:
    if doc_type is None or doc_type == "":
        return None
    if doc_type not in VALID_DOC_TYPES:
        raise ValueError(f"Unsupported doc_type: {doc_type}")
    return None if doc_type == "all" else doc_type


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _build_query_params(*, corpus: str, doc_type: str, document_path: str) -> dict[str, str | None]:
    return {
        "corpus": _normalize_optional_text(corpus),
        "doc_type": _normalize_doc_type(doc_type),
        "document_path": _normalize_optional_text(document_path),
    }


def _build_retriever_filters(*, corpus: str, doc_type: str, document_path: str) -> dict[str, str]:
    return {
        key: value
        for key, value in _build_query_params(
            corpus=corpus,
            doc_type=doc_type,
            document_path=document_path,
        ).items()
        if value is not None
    }


def _result_formatter(record: dict[str, Any]) -> SimpleNamespace:
    sections = [
        (
            f"[source: {record['source_path']} | hitChunk: {record['hit_chunk']} | "
            f"score: {record['similarity_score']}]"
        )
    ]
    if record.get("prev_text"):
        sections.append(f"[prev chunk: {record['prev_chunk']}]\n{record['prev_text']}")
    sections.append(
        "hit window "
        f"(chunk {record['hit_chunk']} | score: {record['similarity_score']})\n"
        f"{record['hit_text']}"
    )
    if record.get("next_text"):
        sections.append(f"[next chunk: {record['next_chunk']}]\n{record['next_text']}")
    return SimpleNamespace(content="\n\n".join(sections))


def _normalize_context_text(value: str) -> str:
    normalized = (
        value.replace("\\r", "")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\u2192", "→")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )
    return "".join(
        character
        for character in normalized
        if character in "\n\t" or (32 <= ord(character) != 127)
    )


_WRAPPED_RECORD_RE = re.compile(r"^<Record content='(?P<content>.*)'>$")


def _dedupe_retrieved_items(retriever_result: Any) -> tuple[int, list[Any]]:
    deduped: list[Any] = []
    seen: set[str] = set()
    removed = 0
    for item in getattr(retriever_result, "items", []):
        content = getattr(item, "content", "")
        match = _WRAPPED_RECORD_RE.match(content)
        canonical = match.group("content") if match else content
        if canonical in seen:
            removed += 1
            continue
        seen.add(canonical)
        deduped.append(item)
    return removed, deduped


__all__ = [
    "QA_PROMPT_TEMPLATE",
    "_build_query_params",
    "_build_retriever_filters",
    "_dedupe_retrieved_items",
    "_normalize_context_text",
    "_result_formatter",
]