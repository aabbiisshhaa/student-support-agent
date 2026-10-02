from __future__ import annotations

from typing import Any

from src.rag.retriever import Retriever


def search_academic_policy(query: str, top_k: int = 2) -> list[dict[str, Any]]:
    """Return grounded university policy passages for a query."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
        raise ValueError("top_k must be an integer between 1 and 5")

    result = Retriever(top_k=top_k).retrieve(query, top_k=top_k)
    return [
        {
            "text": passage.text,
            "citation": passage.citation,
            "doc": passage.doc_title,
        }
        for passage in result.passages
    ]
