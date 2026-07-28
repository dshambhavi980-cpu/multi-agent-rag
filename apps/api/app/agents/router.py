import re
from dataclasses import dataclass
from typing import Literal

from app.models.rag import CreateMessageRequest

COMPLEX_PATTERNS = (
    re.compile(
        r"\b(compare|contrast|reconcile|trade-?offs?|conflict(?:ing)?|differences?)\b", re.I
    ),
    re.compile(r"\b(across|between)\b.+\b(documents?|policies|sources|reports)\b", re.I),
    re.compile(r"\b(analy[sz]e|evaluate|investigate)\b.+\b(and|then|before)\b", re.I),
)


@dataclass(frozen=True)
class RouteDecision:
    mode: Literal["simple", "agentic"]
    reason: str


def route_request(body: CreateMessageRequest) -> RouteDecision:
    if body.force_mode == "simple":
        return RouteDecision("simple", "User explicitly selected the low-latency RAG path.")
    if body.force_mode == "agentic":
        return RouteDecision("agentic", "User explicitly selected bounded agentic research.")

    question = " ".join(body.content.split())
    matched = sum(bool(pattern.search(question)) for pattern in COMPLEX_PATTERNS)
    multi_question = question.count("?") >= 2
    long_multi_part = len(question) >= 320 and bool(
        re.search(r"\b(and|then|also)\b", question, re.I)
    )
    if matched or multi_question or long_multi_part:
        return RouteDecision(
            "agentic",
            "The request requires multiple searches, comparison, or evidence reconciliation.",
        )
    return RouteDecision("simple", "The request can be answered with one bounded retrieval pass.")
