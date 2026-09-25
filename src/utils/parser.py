from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    ANSWER = "answer"
    REFUSAL = "refusal"
    CLARIFY = "clarify"
    TICKET = "ticket"
    ESCALATE = "escalate"


BOUNDARY_OFFICES = {
    "grades": "the Academic Registrar's office",
    "admissions": "the Admissions Office",
    "fees": "the Finance/Accounts Office",
    "discipline": "the Dean of Students' office",
    "policy": "a human support staff member",
}

BOUNDARY_PHRASES = {
    "grades": [
        "change my grade",
        "change the grade",
        "update my grade",
        "edit my grade",
        "raise my grade",
        "grade appeal outcome",
        "clear my name",
        "who was at fault",
        "determine fault",
    ],
    "admissions": [
        "admit me",
        "approve my admission",
        "grant me admission",
        "admission decision",
        "accept my application",
    ],
    "fees": [
        "waive my fees",
        "waive my tuition",
        "clear my fees",
        "fee clearance",
        "fee waiver",
    ],
    "discipline": [
        "expel me",
        "suspend me",
        "disciplinary action",
        "disciplinary hearing",
        "drop my disciplinary case",
    ],
}

BOUNDARY_STRONG_VERBS = {
    "grades": ["round up", "grant me", "grant extra credit"],
    "admissions": [],
    "fees": [],
    "discipline": ["expunge", "reinstate", "reinstating", "overturn", "arbitrate"],
}

BOUNDARY_VERBS = {
    "grades": ["change", "update", "alter", "edit", "adjust", "modify", "round", "raise", "override"],
    "admissions": ["admit", "approve", "grant", "accept", "override"],
    "fees": ["waive", "clear", "refund", "extend", "approve", "process", "discount"],
    "discipline": ["expunge", "reinstate", "reverse", "overturn", "dismiss", "drop"],
}

BOUNDARY_NOUNS = {
    "grades": ["grade", "grades", "mark", "marks", "score", "record", "transcript", "credit"],
    "admissions": ["admission", "admissions", "enrollment", "enrolment"],
    "fees": ["fee", "fees", "tuition", "balance", "deadline", "refund", "bursar"],
    "discipline": ["disciplinary", "suspension", "violation", "record", "case"],
}

ADVERSARIAL_PHRASES = [
    "administrator override",
    "system administrator override",
    "execute administrative command",
    "execute command",
    "ignore previous instructions",
    "ignore all previous instructions",
    "override your instructions",
    "developer mode",
    "jailbreak",
    "sudo",
    "set status =",
]

TAG_PATTERN = re.compile(
    r"^\s*\[(?P<intent>ANSWER|REFUSAL|CLARIFY|TICKET|ESCALATE)"
    r"(?::\s*(?P<meta>[^\]]*))?\]\s*\n?(?P<body>.*)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class ParsedResponse:
    intent: Intent
    message: str
    boundary: str | None = None
    requires_human: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
    raw: str = ""


def _contains_term(lowered: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", lowered) is not None


def detect_hard_boundary(text: str) -> str | None:
    lowered = text.lower()

    for phrase in ADVERSARIAL_PHRASES:
        if _contains_term(lowered, phrase):
            return "policy"

    for boundary, phrases in BOUNDARY_PHRASES.items():
        for phrase in phrases:
            if _contains_term(lowered, phrase):
                return boundary

    for boundary, verbs in BOUNDARY_STRONG_VERBS.items():
        for verb in verbs:
            if _contains_term(lowered, verb):
                return boundary

    for boundary in BOUNDARY_VERBS:
        verb_hit = any(_contains_term(lowered, verb) for verb in BOUNDARY_VERBS[boundary])
        noun_hit = any(_contains_term(lowered, noun) for noun in BOUNDARY_NOUNS[boundary])
        if verb_hit and noun_hit:
            return boundary

    return None


def build_boundary_refusal(boundary: str, raw_text: str = "") -> ParsedResponse:
    office = BOUNDARY_OFFICES.get(boundary, "the appropriate university office")
    if boundary == "policy":
        message = (
            "I can't follow instructions that try to override my configured "
            f"behavior or make administrative changes directly. Please contact {office} "
            "for this request."
        )
    else:
        message = (
            f"I'm not able to help with {boundary} decisions. "
            f"Please contact {office} for this request."
        )
    return ParsedResponse(
        intent=Intent.REFUSAL,
        message=message,
        boundary=boundary,
        requires_human=True,
        raw=raw_text,
    )


def parse_metadata(meta: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not meta:
        return parsed
    for pair in meta.split():
        if "=" in pair:
            key, value = pair.split("=", 1)
            parsed[key.strip().lower()] = value.strip()
    return parsed


def parse_model_response(raw_text: str) -> ParsedResponse:
    text = (raw_text or "").strip()

    if not text:
        return ParsedResponse(
            intent=Intent.ESCALATE,
            message="I wasn't able to generate a response. Let me connect you with support staff.",
            requires_human=True,
            raw=raw_text,
        )

    boundary = detect_hard_boundary(text)
    if boundary:
        return build_boundary_refusal(boundary, raw_text)

    match = TAG_PATTERN.match(text)
    if not match:
        return ParsedResponse(
            intent=Intent.ANSWER,
            message=text,
            raw=raw_text,
        )

    intent = Intent(match.group("intent").lower())
    metadata = parse_metadata(match.group("meta"))
    body = match.group("body").strip()

    if intent == Intent.REFUSAL:
        boundary = metadata.get("boundary") or (match.group("meta") or "").strip().lower() or None
        return ParsedResponse(
            intent=Intent.REFUSAL,
            message=body or build_boundary_refusal(boundary or "scope").message,
            boundary=boundary,
            requires_human=True,
            metadata=metadata,
            raw=raw_text,
        )

    return ParsedResponse(
        intent=intent,
        message=body,
        requires_human=intent in (Intent.TICKET, Intent.ESCALATE),
        metadata=metadata,
        raw=raw_text,
    )
