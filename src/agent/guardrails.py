from __future__ import annotations

import re
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

MAX_INPUT_LENGTH = 4000
MAX_AUDIT_EVENTS = 1000
LEAK_SHINGLE_WORDS = 6
MAX_HISTORY_RECORDS = 200
MAX_HISTORY_CONTENT_LENGTH = 8000

INJECTION_REFUSAL_MESSAGE = (
    "I cannot act on instructions that try to change how I operate or reveal "
    "my configuration. I can help with your timetable, university policy "
    "questions, or a support ticket."
)

ADMIN_REFUSAL_MESSAGE = (
    "I am not authorized to process changes to academic records, "
    "fee adjustments, or disciplinary decisions. This request "
    "requires human administrative review. Would you like me to "
    "route this to your department administrator?"
)

INVALID_INPUT_MESSAGE = "Please send a non-empty question of reasonable length."

LEAK_REDACTION_NOTICE = "[internal instructions redacted]"
CITATION_REDACTION_NOTICE = "[unverified citation removed]"
OUTPUT_FALLBACK_MESSAGE = (
    "I cannot share that. I can help with your timetable, university policy "
    "questions, or a support ticket."
)

CATEGORY_INVALID_INPUT = "invalid_input"
CATEGORY_PROMPT_INJECTION = "prompt_injection"
CATEGORY_OUT_OF_SCOPE = "out_of_scope_administrative_action"

STUDENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]{2,29}")
CASE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,49}")
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
COURSE_CODE_PATTERN = re.compile(r"[A-Z]{3}[0-9]{4}")
ESCALATION_TARGET_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 '&,.-]{2,99}")

WEEKDAYS = frozenset(
    {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
)
TICKET_CATEGORIES = frozenset({"timetable", "policy", "administrative", "other"})
TICKET_PRIORITIES = frozenset({"low", "medium", "high"})
HISTORY_ROLES = frozenset({"user", "assistant", "system"})

CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "в": "b",
        "е": "e",
        "к": "k",
        "м": "m",
        "н": "h",
        "о": "o",
        "р": "p",
        "с": "c",
        "т": "t",
        "у": "y",
        "х": "x",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "ο": "o",
        "ι": "i",
        "α": "a",
        "ε": "e",
    }
)
LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)

POLICY_SUFFIX = (
    r"(?! (?:policy|policies|procedure|procedures|process|rules?|regulations?|"
    r"requirements?)\b)"
)

INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "system_prompt_reference",
        re.compile(
            r"\b(?:system|developer|hidden|initial|original) "
            r"(?:prompt|message|instructions?)\b"
        ),
    ),
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|discard)(?: \w+){0,3} "
            r"(?:instructions?|rules|guidelines|directives|restrictions|prompts?|"
            r"programming|constraints|safeguards|guardrails)\b"
        ),
    ),
    (
        "rule_disclosure_request",
        re.compile(
            r"\b(?:(?:reveal|show|print|repeat|display|output|leak|expose|recite|"
            r"share|tell)(?: me| us)? (?:your|ur|the above|the system|the hidden|"
            r"the initial|the original|all your)(?: \w+)? (?:rules|instructions|"
            r"guidelines|prompt|configuration|programming|guardrails)|"
            r"what (?:are|is) your (?:rules|instructions|guidelines|system prompt))\b"
        ),
    ),
    (
        "persona_hijack",
        re.compile(
            r"\b(?:you are now|pretend (?:to be|you are|you re)|developer mode|"
            r"jailbreak|jailbroken|do anything now|dan mode|"
            r"act as if you have no (?:rules|restrictions))\b"
        ),
    ),
    (
        "safeguard_disable",
        re.compile(
            r"\b(?:disable|turn off|remove) (?:your |all |the )*"
            r"(?:restrictions|filters|guardrails|safeguards|safety|rules)\b"
        ),
    ),
)

DELIMITER_RULE = (
    "delimiter_injection",
    re.compile(
        r"<\|?\s*(?:im_start|im_end|system|assistant|endoftext)\s*\|?>|"
        r"\[/?(?:inst|system)\]|^\s*#{1,3}\s*system\b",
        re.MULTILINE,
    ),
)

ADMIN_VERBS = (
    r"(?:change|alter|modify|edit|update(?! (?:me|on)\b)|override|overwrite|delete|"
    r"remove|erase|expunge|waive|forgive|refund|overturn|reverse|revoke|cancel|"
    r"backdate|falsify|amend|adjust|fix|correct)"
)
PROTECTED_OBJECTS = (
    r"(?:grades?|marks?|scores?|gpa|results?|transcripts?|fees?|tuition|balance|"
    r"attendance|admission|disciplinary|suspension|expulsion|penalty|penalties|"
    r"sanctions?)"
)

ADMIN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "admin_verb_on_protected_record",
        re.compile(rf"\b{ADMIN_VERBS}\b(?: \w+){{0,3}} {PROTECTED_OBJECTS}\b"),
    ),
    (
        "admin_noun_on_protected_record",
        re.compile(
            r"\b(?:grade|mark|score|result|fee|tuition|attendance|transcript)s? "
            r"(?:change|alteration|override|amendment|adjustment|correction|edit|"
            r"waiver|refund|modification)\b" + POLICY_SUFFIX
        ),
    ),
    (
        "prohibited_admin_phrase",
        re.compile(
            r"\b(?:fee waiver|tuition refund|financial bypass|clear tuition|"
            r"cancel suspension|expulsion overturn|disciplinary appeal|"
            r"exam result edit)\b" + POLICY_SUFFIX
        ),
    ),
)

LEAK_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "rule_header",
        re.compile(r"\b(?:critical rules|system rules|hard rules)\s*:", re.IGNORECASE),
    ),
    (
        "prompt_self_reference",
        re.compile(
            r"\b(?:my|the) (?:system|hidden|internal|initial) "
            r"(?:prompt|instructions|rules|configuration)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_quotation",
        re.compile(
            r"\b(?:i was|i am|i have been) (?:told|instructed|programmed|configured) "
            r"(?:to|not to|never to)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prohibited_intent_list",
        re.compile(r"\bprohibited[_ ]intents?\b", re.IGNORECASE),
    ),
    (
        "chat_delimiter",
        re.compile(r"<\|?\s*(?:im_start|im_end|system)\s*\|?>|\[/?(?:inst|system)\]"),
    ),
)

BRACKETED_SPAN = re.compile(r"\[([^\[\]\n]{3,300})\](?!\()")
CITATION_HINT = re.compile(
    r"^(?:source|citation|ref|reference)\s*:|"
    r"\bs\.\s*\d|\bsection\s+\d|"
    r"\b(?:policy|handbook|regulations?|code of conduct|procedure|prospectus|act)\b",
    re.IGNORECASE,
)
BARE_REFERENCE = re.compile(
    r"\b(?:section|sec\.|clause|article|regulation|paragraph|s\.)\s*(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY = re.compile(r"((?<=[.!?])\s+(?=[A-Z\[\"'(])|\n+)")


def clean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        ch
        for ch in normalized
        if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf"}
    )


def word_form(text: str) -> str:
    folded = clean_text(text).casefold().translate(CONFUSABLES)
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def leet_form(text: str) -> str:
    folded = clean_text(text).casefold().translate(CONFUSABLES)
    tokens = re.findall(r"[a-z0-9@$]+", folded)
    mapped = []
    for token in tokens:
        if re.search(r"[a-z]", token) and re.search(r"[0-9@$]", token):
            token = token.translate(LEET)
        mapped.append(re.sub(r"[^a-z0-9]", "", token))
    return " ".join(mapped)


def match_rules(
    rules: Iterable[tuple[str, re.Pattern[str]]], *forms: str
) -> tuple[str, ...]:
    matched: list[str] = []
    for rule_id, pattern in rules:
        if any(pattern.search(form) for form in forms) and rule_id not in matched:
            matched.append(rule_id)
    return tuple(matched)


@dataclass(frozen=True)
class InputDecision:
    allowed: bool
    category: str | None
    rules: tuple[str, ...]
    message: str | None
    text: str


@dataclass(frozen=True)
class ParamRule:
    kind: str
    required: bool = True
    nullable: bool = False
    pattern: re.Pattern[str] | None = None
    min_length: int = 0
    max_length: int = 0
    minimum: int | None = None
    maximum: int | None = None
    choices: frozenset[str] | None = None
    multiline: bool = False


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    params: Mapping[str, ParamRule]
    requires_human_approval: bool = False
    approval_param: str | None = None


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    tool_name: str
    rule: str | None
    reason: str | None
    params: Mapping[str, Any]
    approval_required: bool = False


@dataclass(frozen=True)
class OutputDecision:
    text: str
    modified: bool
    leaked: bool
    hallucinated_citations: tuple[str, ...]
    rules: tuple[str, ...]


class GuardrailError(Exception):
    pass


class ToolCallBlocked(GuardrailError):
    def __init__(self, decision: ToolDecision) -> None:
        super().__init__(f"{decision.tool_name}: {decision.rule}: {decision.reason}")
        self.decision = decision


class ParamViolation(GuardrailError):
    def __init__(self, rule: str, reason: str) -> None:
        super().__init__(reason)
        self.rule = rule
        self.reason = reason


def _string_rule(
    pattern: re.Pattern[str] | None = None,
    *,
    min_length: int = 1,
    max_length: int,
    required: bool = True,
    nullable: bool = False,
    multiline: bool = False,
) -> ParamRule:
    return ParamRule(
        kind="str",
        required=required,
        nullable=nullable,
        pattern=pattern,
        min_length=min_length,
        max_length=max_length,
        multiline=multiline,
    )


def _enum_rule(choices: frozenset[str], *, required: bool = True) -> ParamRule:
    return ParamRule(kind="enum", required=required, choices=choices)


def _int_rule(minimum: int, maximum: int, *, required: bool = True) -> ParamRule:
    return ParamRule(kind="int", required=required, minimum=minimum, maximum=maximum)


TOOL_ALLOW_LIST: Mapping[str, ToolPolicy] = {
    "get_course_schedule": ToolPolicy(
        name="get_course_schedule",
        params={
            "student_id": _string_rule(STUDENT_ID_PATTERN, min_length=3, max_length=30),
            "course_code": _string_rule(
                COURSE_CODE_PATTERN,
                min_length=7,
                max_length=7,
                required=False,
                nullable=True,
            ),
            "day": ParamRule(
                kind="enum", required=False, nullable=True, choices=WEEKDAYS
            ),
        },
    ),
    "search_academic_policy": ToolPolicy(
        name="search_academic_policy",
        params={
            "query": _string_rule(max_length=500),
            "top_k": _int_rule(1, 5, required=False),
        },
    ),
    "create_support_ticket": ToolPolicy(
        name="create_support_ticket",
        params={
            "student_id": _string_rule(STUDENT_ID_PATTERN, min_length=3, max_length=30),
            "summary": _string_rule(min_length=10, max_length=500),
            "original_message": _string_rule(max_length=2000, multiline=True),
            "category": _enum_rule(TICKET_CATEGORIES),
            "priority": _enum_rule(TICKET_PRIORITIES),
            "student_confirmed": ParamRule(kind="bool", required=False),
            "case_id": _string_rule(
                CASE_ID_PATTERN,
                min_length=3,
                max_length=50,
                required=False,
                nullable=True,
            ),
        },
        requires_human_approval=True,
        approval_param="student_confirmed",
    ),
    "escalate_to_human_admin": ToolPolicy(
        name="escalate_to_human_admin",
        params={
            "session_id": _string_rule(SESSION_ID_PATTERN, max_length=64),
            "student_id": _string_rule(STUDENT_ID_PATTERN, min_length=3, max_length=30),
            "reason": _string_rule(max_length=500),
            "conversation_history": ParamRule(kind="history"),
            "iteration_count": _int_rule(0, 10),
            "max_allowed_iterations": _int_rule(1, 10),
            "escalation_target": _string_rule(
                ESCALATION_TARGET_PATTERN,
                min_length=3,
                max_length=100,
                required=False,
            ),
        },
        requires_human_approval=True,
    ),
}


def _has_forbidden_characters(value: str, multiline: bool) -> bool:
    for ch in value:
        category = unicodedata.category(ch)
        if multiline and ch in "\n\t":
            continue
        if category in {"Cc", "Cf", "Cs", "Co", "Cn"}:
            return True
    return False


def _check_string(name: str, rule: ParamRule, value: Any) -> str:
    if not isinstance(value, str) or isinstance(value, Enum):
        raise ParamViolation("param_type", f"{name} must be a string")
    if not rule.min_length <= len(value) <= rule.max_length:
        raise ParamViolation(
            "param_length",
            f"{name} must be {rule.min_length}-{rule.max_length} characters",
        )
    if _has_forbidden_characters(value, rule.multiline):
        raise ParamViolation("param_characters", f"{name} contains control characters")
    if rule.pattern is not None and rule.pattern.fullmatch(value) is None:
        raise ParamViolation("param_pattern", f"{name} does not match the required format")
    if not value.strip():
        raise ParamViolation("param_length", f"{name} cannot be blank")
    return value


def _check_enum(name: str, rule: ParamRule, value: Any) -> str:
    if not isinstance(value, str):
        raise ParamViolation("param_choice", f"{name} is not an allowed value")
    raw = value.value if isinstance(value, Enum) else value
    if not isinstance(raw, str) or rule.choices is None or raw not in rule.choices:
        raise ParamViolation("param_choice", f"{name} is not an allowed value")
    return raw


def _check_int(name: str, rule: ParamRule, value: Any) -> int:
    if type(value) is not int:
        raise ParamViolation("param_type", f"{name} must be an integer")
    if rule.minimum is not None and value < rule.minimum:
        raise ParamViolation("param_range", f"{name} is below {rule.minimum}")
    if rule.maximum is not None and value > rule.maximum:
        raise ParamViolation("param_range", f"{name} is above {rule.maximum}")
    return value


def _check_bool(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise ParamViolation("param_type", f"{name} must be a boolean")
    return value


def _check_history(name: str, value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ParamViolation("param_type", f"{name} must be a list")
    if len(value) > MAX_HISTORY_RECORDS:
        raise ParamViolation("param_length", f"{name} has too many records")
    records: list[dict[str, str]] = []
    for record in value:
        if not isinstance(record, Mapping) or set(record) != {"role", "content"}:
            raise ParamViolation(
                "param_shape", f"{name} records need exactly role and content"
            )
        role, content = record["role"], record["content"]
        if not isinstance(role, str) or role not in HISTORY_ROLES:
            raise ParamViolation("param_choice", f"{name} has an invalid role")
        if not isinstance(content, str) or len(content) > MAX_HISTORY_CONTENT_LENGTH:
            raise ParamViolation("param_length", f"{name} has invalid content")
        if _has_forbidden_characters(content, True):
            raise ParamViolation(
                "param_characters", f"{name} content contains control characters"
            )
        records.append({"role": role, "content": content})
    return records


def _check_value(name: str, rule: ParamRule, value: Any) -> Any:
    if value is None:
        if rule.nullable:
            return None
        raise ParamViolation("param_null", f"{name} cannot be None")
    if rule.kind == "str":
        return _check_string(name, rule, value)
    if rule.kind == "enum":
        return _check_enum(name, rule, value)
    if rule.kind == "int":
        return _check_int(name, rule, value)
    if rule.kind == "bool":
        return _check_bool(name, value)
    if rule.kind == "history":
        return _check_history(name, value)
    raise ParamViolation("param_type", f"{name} has an unsupported rule")


def _validate_params(
    policy: ToolPolicy, params: Mapping[str, Any]
) -> dict[str, Any]:
    if "human_confirmed" in params:
        raise ParamViolation(
            "approval_self_supplied",
            "human_confirmed cannot be supplied inside tool parameters",
        )
    for key in params:
        if not isinstance(key, str):
            raise ParamViolation("param_unexpected", "parameter names must be strings")
    unexpected = sorted(set(params) - set(policy.params))
    if unexpected:
        raise ParamViolation(
            "param_unexpected", f"unexpected parameter(s) {unexpected}"
        )
    validated: dict[str, Any] = {}
    for name, rule in policy.params.items():
        if name not in params:
            if rule.required:
                raise ParamViolation("param_missing", f"missing required parameter {name!r}")
            continue
        validated[name] = _check_value(name, rule, params[name])
    return validated


def _normalized_words(text: str) -> list[str]:
    return word_form(text).split()


def _shingles(words: list[str], size: int) -> set[tuple[str, ...]]:
    if len(words) < size:
        return set()
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def _normalize_citation(text: str) -> str:
    return word_form(re.sub(r"^\s*(?:source|citation|ref|reference)\s*:", "", text, flags=re.I))


def _reference_numbers(text: str) -> set[str]:
    return {match.group(1) for match in BARE_REFERENCE.finditer(text)}


class GuardrailEngine:
    def __init__(
        self,
        protected_texts: Iterable[str] = (),
        allow_list: Mapping[str, ToolPolicy] | None = None,
        max_input_length: int = MAX_INPUT_LENGTH,
    ) -> None:
        self.allow_list: Mapping[str, ToolPolicy] = dict(
            TOOL_ALLOW_LIST if allow_list is None else allow_list
        )
        self.max_input_length = max_input_length
        self.audit_log: deque[dict[str, Any]] = deque(maxlen=MAX_AUDIT_EVENTS)
        self._protected_shingles: set[tuple[str, ...]] = set()
        for text in protected_texts:
            self.add_protected_text(text)

    def add_protected_text(self, text: str) -> None:
        self._protected_shingles |= _shingles(_normalized_words(text), LEAK_SHINGLE_WORDS)

    def _record(self, stage: str, allowed: bool, **details: Any) -> None:
        self.audit_log.append({"stage": stage, "allowed": allowed, **details})

    def screen_input(self, user_text: Any) -> InputDecision:
        if not isinstance(user_text, str):
            self._record("input", False, category=CATEGORY_INVALID_INPUT, rules=("not_a_string",))
            return InputDecision(
                False, CATEGORY_INVALID_INPUT, ("not_a_string",), INVALID_INPUT_MESSAGE, ""
            )

        cleaned = clean_text(user_text).strip()
        if not cleaned:
            self._record("input", False, category=CATEGORY_INVALID_INPUT, rules=("empty_input",))
            return InputDecision(
                False, CATEGORY_INVALID_INPUT, ("empty_input",), INVALID_INPUT_MESSAGE, ""
            )
        if len(cleaned) > self.max_input_length:
            self._record(
                "input", False, category=CATEGORY_INVALID_INPUT, rules=("input_too_long",)
            )
            return InputDecision(
                False, CATEGORY_INVALID_INPUT, ("input_too_long",), INVALID_INPUT_MESSAGE, ""
            )

        words = word_form(cleaned)
        leet = leet_form(cleaned)
        raw_folded = cleaned.casefold().translate(CONFUSABLES)

        injection = match_rules(INJECTION_RULES, words, leet) + match_rules(
            (DELIMITER_RULE,), raw_folded
        )
        if injection:
            self._record(
                "input",
                False,
                category=CATEGORY_PROMPT_INJECTION,
                rules=injection,
                length=len(cleaned),
            )
            return InputDecision(
                False, CATEGORY_PROMPT_INJECTION, injection, INJECTION_REFUSAL_MESSAGE, cleaned
            )

        admin = match_rules(ADMIN_RULES, words, leet)
        if admin:
            self._record(
                "input",
                False,
                category=CATEGORY_OUT_OF_SCOPE,
                rules=admin,
                length=len(cleaned),
            )
            return InputDecision(False, CATEGORY_OUT_OF_SCOPE, admin, ADMIN_REFUSAL_MESSAGE, cleaned)

        self._record("input", True, length=len(cleaned))
        return InputDecision(True, None, (), None, cleaned)

    def authorize_tool_call(
        self,
        tool_name: Any,
        params: Any,
        *,
        human_confirmed: bool = False,
    ) -> ToolDecision:
        name_label = tool_name if isinstance(tool_name, str) else repr(type(tool_name))

        def blocked(
            rule: str, reason: str, approval_required: bool = False
        ) -> ToolDecision:
            self._record("tool", False, tool=name_label, rule=rule)
            return ToolDecision(
                False, name_label, rule, reason, {}, approval_required=approval_required
            )

        if not isinstance(tool_name, str) or tool_name not in self.allow_list:
            return blocked("tool_not_allowed", f"{name_label!r} is not on the allow-list")
        if not isinstance(params, Mapping):
            return blocked("params_not_mapping", "tool parameters must be a mapping")

        policy = self.allow_list[tool_name]
        try:
            validated = _validate_params(policy, params)
        except ParamViolation as violation:
            return blocked(violation.rule, violation.reason)

        if policy.requires_human_approval:
            if human_confirmed is not True:
                return blocked(
                    "human_approval_required",
                    f"{tool_name} has side effects and needs human_confirmed=True",
                    approval_required=True,
                )
            if policy.approval_param is not None:
                validated[policy.approval_param] = True

        self._record(
            "tool",
            True,
            tool=tool_name,
            approved=bool(policy.requires_human_approval and human_confirmed is True),
        )
        return ToolDecision(
            True,
            tool_name,
            None,
            None,
            validated,
            approval_required=policy.requires_human_approval,
        )

    def guarded_execute(
        self,
        tool_name: Any,
        params: Any,
        executor: Callable[[str, Mapping[str, Any]], Any],
        *,
        human_confirmed: bool = False,
    ) -> Any:
        decision = self.authorize_tool_call(
            tool_name, params, human_confirmed=human_confirmed
        )
        if not decision.allowed:
            raise ToolCallBlocked(decision)
        return executor(decision.tool_name, decision.params)

    def _leaks(self, sentence: str) -> tuple[str, ...]:
        rules = [rule_id for rule_id, pattern in LEAK_MARKERS if pattern.search(sentence)]
        if self._protected_shingles and (
            _shingles(_normalized_words(sentence), LEAK_SHINGLE_WORDS)
            & self._protected_shingles
        ):
            rules.append("protected_text_overlap")
        return tuple(rules)

    def _redact_leaks(self, text: str) -> tuple[str, tuple[str, ...]]:
        parts = SENTENCE_BOUNDARY.split(text)
        output: list[str] = []
        rules: list[str] = []
        for index, part in enumerate(parts):
            if index % 2 == 1:
                output.append(part)
                continue
            found = self._leaks(part)
            if not found:
                output.append(part)
                continue
            rules.extend(rule for rule in found if rule not in rules)
            output.append(LEAK_REDACTION_NOTICE)
        merged = re.sub(
            rf"(?:{re.escape(LEAK_REDACTION_NOTICE)}\s*)+",
            LEAK_REDACTION_NOTICE + " ",
            "".join(output),
        )
        return merged.strip() if rules else "".join(output), tuple(rules)

    def _scrub_citations(
        self, text: str, grounded_citations: Iterable[str], grounded_texts: Iterable[str]
    ) -> tuple[str, tuple[str, ...]]:
        grounded = {_normalize_citation(c) for c in grounded_citations if c}
        grounded.discard("")
        grounded_numbers: set[str] = set()
        for source in (*grounded_citations, *grounded_texts):
            grounded_numbers |= _reference_numbers(str(source))

        protected_spans: list[tuple[int, int]] = []
        for citation in grounded:
            pattern = re.compile(
                r"\s+".join(re.escape(token) for token in citation.split()),
                re.IGNORECASE,
            )
            protected_spans.extend(match.span() for match in pattern.finditer(text))

        def overlaps(span: tuple[int, int], others: list[tuple[int, int]]) -> bool:
            return any(span[0] < end and start < span[1] for start, end in others)

        bad_spans: list[tuple[int, int]] = []
        bracket_spans: list[tuple[int, int]] = []
        for match in BRACKETED_SPAN.finditer(text):
            span = match.span()
            bracket_spans.append(span)
            if overlaps(span, protected_spans) or not CITATION_HINT.search(match.group(1)):
                continue
            if _normalize_citation(match.group(1)) in grounded:
                continue
            bad_spans.append(span)

        for match in BARE_REFERENCE.finditer(text):
            span = match.span()
            if overlaps(span, protected_spans) or overlaps(span, bracket_spans):
                continue
            if match.group(1) in grounded_numbers:
                continue
            bad_spans.append(span)

        hallucinated = tuple(text[start:end].strip() for start, end in sorted(bad_spans))
        scrubbed = text
        for start, end in sorted(bad_spans, reverse=True):
            scrubbed = scrubbed[:start] + CITATION_REDACTION_NOTICE + scrubbed[end:]
        return scrubbed, hallucinated

    def sanitize_output(
        self,
        response: Any,
        *,
        grounded_citations: Iterable[str] = (),
        grounded_texts: Iterable[str] = (),
    ) -> OutputDecision:
        if not isinstance(response, str) or not clean_text(response).strip():
            self._record("output", False, rules=("empty_output",))
            return OutputDecision(OUTPUT_FALLBACK_MESSAGE, True, False, (), ("empty_output",))

        grounded_citations = tuple(grounded_citations)
        grounded_texts = tuple(grounded_texts)
        original = clean_text(response)

        redacted, leak_rules = self._redact_leaks(original)
        if leak_rules and not redacted.replace(LEAK_REDACTION_NOTICE, "").strip():
            self._record("output", False, rules=leak_rules)
            return OutputDecision(OUTPUT_FALLBACK_MESSAGE, True, True, (), leak_rules)

        scrubbed, hallucinated = self._scrub_citations(
            redacted, grounded_citations, grounded_texts
        )

        rules = leak_rules + (("hallucinated_citation",) if hallucinated else ())
        modified = scrubbed != response
        self._record(
            "output",
            not rules,
            rules=rules,
            hallucinated=len(hallucinated),
        )
        return OutputDecision(
            scrubbed, modified, bool(leak_rules), hallucinated, rules
        )
