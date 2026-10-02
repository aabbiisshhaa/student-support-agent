"""Multi-step student-support agent orchestrator."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.agent.memory import ConversationMemory
from src.baseline_model import GeminiModel
from src.rag.retriever import EmbedderInfo, Retriever
from src.telemetry.tracker import TelemetryTracker, TurnTelemetry
from src.tools import registry as tool_registry
from src.tools.ticket_tool import TicketCategory, TicketPriority


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_STUDENT_ID = "2300712345"
MAX_AGENT_ITERATIONS = 3
VALID_RUN_STATUSES = frozenset(
    {"success", "recovered", "escalated"}
)

COURSE_CODE_IN_QUERY = re.compile(r"\b[A-Za-z]{3}\d{4}\b")
TICKET_SUMMARY_MIN_LENGTH = 10
TICKET_SUMMARY_MAX_LENGTH = 80

EventCallback = Callable[[Dict[str, Any]], None]


# Allows joblib to load older stored EmbedderInfo objects.
import __main__

setattr(__main__, "EmbedderInfo", EmbedderInfo)


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
)
logger = logging.getLogger("AgentOrchestrator")


class SupportAgentOrchestrator:
    """Runs the bounded Sense-Plan-Act-Observe-Revise workflow."""

    PROHIBITED_INTENTS = [
        "grade change",
        "change grade",
        "change my grade",
        "update my grade",
        "change mark",
        "alter score",
        "exam result edit",
        "modify academic records",
        "modify student academic records",
        "fee waiver",
        "clear tuition",
        "tuition refund",
        "financial bypass",
        "disciplinary appeal",
        "cancel suspension",
        "expulsion overturn",
    ]

    HARD_REFUSAL_MESSAGE = (
        "I am not authorized to process changes to academic records, "
        "fee adjustments, or disciplinary decisions. This request "
        "requires human administrative review. Would you like me to "
        "route this to your department administrator?"
    )

    SYSTEM_PROMPT = """
You are the official University Student Support Case Agent.

Your duty is to assist students using verified university policy
documents and tool observations.

CRITICAL RULES:

1. Answer only using facts from the provided evidence or tool results.
2. Do not invent policy, timetable or administrative information.
3. When citing university policy, include the exact source citation.
4. Use a professional, clear, objective and supportive tone.
5. If the evidence does not contain the answer, state that the
   information cannot be confirmed and offer escalation.
6. Never alter grades, fee records, admission decisions or disciplinary
   decisions.
""".strip()

    def __init__(
        self,
        memory_manager: Optional[ConversationMemory] = None,
        max_iterations: int = MAX_AGENT_ITERATIONS,
    ) -> None:
        if (
            isinstance(max_iterations, bool)
            or not isinstance(max_iterations, int)
            or not 1 <= max_iterations <= MAX_AGENT_ITERATIONS
        ):
            raise ValueError(
                "max_iterations must be an integer between 1 and "
                f"{MAX_AGENT_ITERATIONS}."
            )

        self.memory = memory_manager or ConversationMemory()
        self.telemetry = TelemetryTracker()
        self.max_iterations = max_iterations
        self._retriever_instance: Optional[Retriever] = None

        try:
            self.model = GeminiModel()
            self.has_live_model = True
        except Exception as error:
            logger.warning(
                "GeminiModel could not be initialized (%s). "
                "Running in deterministic fallback mode.",
                error,
            )
            self.has_live_model = False

    def _get_retriever(self) -> Retriever:
        """Return the shared retriever instance."""

        if self._retriever_instance is None:
            self._retriever_instance = Retriever(top_k=2)

        return self._retriever_instance

    @staticmethod
    def _emit(
        on_event: Optional[EventCallback],
        event: Dict[str, Any],
    ) -> None:
        """Emit an execution event when a callback is available."""

        if on_event is not None:
            on_event(event)

    def _finish_tool_call(
        self,
        on_event: Optional[EventCallback],
        tool_name: str,
        params: Dict[str, Any],
        result: Any,
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        """Build an auditable record for a completed tool call."""

        failed = isinstance(result, dict) and "error" in result

        record = {
            "tool": tool_name,
            "params": params,
            "status": "error" if failed else "ok",
            "result": result,
            "latency_ms": elapsed_seconds * 1000,
        }

        self._emit(
            on_event,
            {
                "event": "tool_end",
                "tool": tool_name,
                "status": record["status"],
                "latency_ms": record["latency_ms"],
            },
        )

        return record

    def run(
        self,
        session_id: str,
        user_query: str,
        student_id: str = DEFAULT_STUDENT_ID,
        on_event: Optional[EventCallback] = None,
    ) -> Dict[str, Any]:
        """Run one bounded agent turn."""

        start_time = time.time()
        tool_time_total = 0.0
        tools_used: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        logger.info(
            "[%s] SENSE: Processing user turn...",
            session_id,
        )

        self.memory.initialize_session(session_id, student_id)

        turn_index = (
            len(self.memory.get_recent_history(session_id)) + 1
        )

        turn_metrics = TurnTelemetry(
            session_id=session_id,
            turn_index=turn_index,
            user_query=user_query,
        )

        query_lower = user_query.lower()

        # Stop prohibited operations before any agent iteration or tool.
        if any(
            intent in query_lower
            for intent in self.PROHIBITED_INTENTS
        ):
            logger.warning(
                "[%s] SAFETY REFUSAL: Prohibited intent detected.",
                session_id,
            )

            self.memory.add_turn(
                session_id,
                "user",
                user_query,
            )
            self.memory.add_turn(
                session_id,
                "assistant",
                self.HARD_REFUSAL_MESSAGE,
            )

            turn_metrics.status = "escalated"
            turn_metrics.total_turn_latency_ms = (
                time.time() - start_time
            ) * 1000
            self.telemetry.record_turn(turn_metrics)

            return {
                "status": "escalated",
                "response": self.HARD_REFUSAL_MESSAGE,
                "escalation_required": True,
                "iterations": 0,
                "tool_calls": tool_calls,
            }

        self.memory.add_turn(
            session_id,
            "user",
            user_query,
        )

        # Includes recent messages and summarized older messages.
        session_history = self.memory.get_context(session_id)

        iteration = 0
        observation = ""
        context_snippets: List[Dict[str, Any]] = []

        while iteration < self.max_iterations:
            iteration += 1

            logger.info(
                "[%s] PLAN: Iteration %s/%s",
                session_id,
                iteration,
                self.max_iterations,
            )

            plan = self._plan_next_step(
                user_query,
                session_history,
                observation,
                student_id,
            )

            action = plan.get("action")

            if action == "RETRIEVE_KNOWLEDGE":
                logger.info(
                    "[%s] ACT: Retrieving RAG knowledge chunks...",
                    session_id,
                )

                self._emit(
                    on_event,
                    {
                        "event": "tool_start",
                        "tool": "retriever",
                    },
                )

                started_at = time.time()
                retrieval_result: Any = []

                try:
                    retriever = self._get_retriever()
                    rag_result = retriever.retrieve(
                        plan["query"],
                        top_k=2,
                    )

                    if rag_result.passages:
                        context_snippets = [
                            {
                                "text": passage.text,
                                "citation": passage.citation,
                                "doc": passage.doc_title,
                            }
                            for passage in rag_result.passages
                        ]

                        retrieval_result = context_snippets
                        observation = (
                            "Policy Evidence: "
                            f"{json.dumps(context_snippets)}"
                        )
                    else:
                        observation = (
                            "No relevant policy documents found "
                            "in the university database."
                        )

                except Exception as error:
                    logger.error(
                        "Error during RAG retrieval: %s",
                        error,
                    )
                    observation = (
                        "Knowledge base lookup failed: "
                        f"{error}"
                    )
                    retrieval_result = {
                        "error": str(error),
                    }

                elapsed = time.time() - started_at
                tool_time_total += elapsed
                tools_used.append("retriever")

                tool_calls.append(
                    self._finish_tool_call(
                        on_event,
                        "retriever",
                        {"query": plan["query"]},
                        retrieval_result,
                        elapsed,
                    )
                )

            elif action == "EXECUTE_TOOL":
                tool_name = plan["tool_name"]
                tool_params = plan["tool_params"]

                logger.info(
                    "[%s] ACT: Executing tool '%s' with %s",
                    session_id,
                    tool_name,
                    tool_params,
                )

                self._emit(
                    on_event,
                    {
                        "event": "tool_start",
                        "tool": tool_name,
                    },
                )

                started_at = time.time()

                tool_result = self._dispatch_tool(
                    tool_name,
                    tool_params,
                )

                elapsed = time.time() - started_at
                tool_time_total += elapsed
                tools_used.append(tool_name)

                tool_calls.append(
                    self._finish_tool_call(
                        on_event,
                        tool_name,
                        tool_params,
                        tool_result,
                        elapsed,
                    )
                )

                observation = (
                    "Tool Result: "
                    f"{json.dumps(tool_result)}"
                )

                logger.info(
                    "[%s] OBSERVE: Tool execution completed.",
                    session_id,
                )

            elif action == "FINAL_SYNTHESIS":
                logger.info(
                    "[%s] REVISE: Synthesizing final response...",
                    session_id,
                )

                model_started_at = time.time()

                final_answer = self._synthesize_response(
                    user_query=user_query,
                    history=session_history,
                    context=context_snippets,
                    observation=observation,
                    session_id=session_id,
                )

                model_latency_ms = (
                    time.time() - model_started_at
                ) * 1000

                self.memory.add_turn(
                    session_id,
                    "assistant",
                    final_answer,
                )

                prompt_estimate = (
                    len(user_query)
                    + len(observation)
                    + len(str(session_history))
                ) // 4

                completion_estimate = len(final_answer) // 4

                ticket_created = any(
                    call["tool"] == "create_support_ticket"
                    and call["status"] == "ok"
                    for call in tool_calls
                )

                tool_failed = any(
                    call["status"] == "error"
                    for call in tool_calls
                )

                if ticket_created:
                    turn_status = "escalated"
                elif tool_failed:
                    turn_status = "recovered"
                else:
                    turn_status = "success"

                turn_metrics.status = turn_status
                turn_metrics.model_latency_ms = model_latency_ms
                turn_metrics.tool_latency_ms = (
                    tool_time_total * 1000
                )
                turn_metrics.total_turn_latency_ms = (
                    time.time() - start_time
                ) * 1000
                turn_metrics.prompt_tokens = prompt_estimate
                turn_metrics.completion_tokens = (
                    completion_estimate
                )
                turn_metrics.total_tokens = (
                    prompt_estimate
                    + completion_estimate
                )
                turn_metrics.tools_invoked = tools_used

                self.telemetry.record_turn(turn_metrics)

                return {
                    "status": turn_status,
                    "response": final_answer,
                    "escalation_required": ticket_created,
                    "iterations": iteration,
                    "tool_calls": tool_calls,
                }

            else:
                logger.error(
                    "[%s] Unknown plan action: %s",
                    session_id,
                    action,
                )

                observation = (
                    "Planning failed because the requested action "
                    "was not recognized."
                )

                tool_calls.append(
                    {
                        "tool": "planner",
                        "params": plan,
                        "status": "error",
                        "result": {
                            "error": (
                                "Unknown planner action: "
                                f"{action}"
                            )
                        },
                        "latency_ms": 0.0,
                    }
                )

        fallback = (
            "I was unable to resolve your inquiry within the "
            "allowed execution cycles. Escalating to staff."
        )

        self.memory.add_turn(
            session_id,
            "assistant",
            fallback,
        )

        turn_metrics.status = "escalated"
        turn_metrics.tool_latency_ms = (
            tool_time_total * 1000
        )
        turn_metrics.total_turn_latency_ms = (
            time.time() - start_time
        ) * 1000
        turn_metrics.tools_invoked = tools_used

        self.telemetry.record_turn(turn_metrics)

        return {
            "status": "escalated",
            "response": fallback,
            "escalation_required": True,
            "iterations": iteration,
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _ticket_summary(query: str) -> str:
        """Create a bounded factual support-ticket summary."""

        text = " ".join(query.split())

        if len(text) < TICKET_SUMMARY_MIN_LENGTH:
            text = f"Student request: {text}"

        return text[:TICKET_SUMMARY_MAX_LENGTH]

    def _plan_next_step(
        self,
        query: str,
        history: List[Dict[str, Any]],
        observation: str,
        student_id: str = DEFAULT_STUDENT_ID,
    ) -> Dict[str, Any]:
        """Choose the next deterministic agent action."""

        query_lower = query.lower()

        # Route 1: Timetable inquiry.
        if (
            (
                "schedule" in query_lower
                or "timetable" in query_lower
                or "lecture" in query_lower
            )
            and "Tool Result" not in observation
        ):
            course_match = COURSE_CODE_IN_QUERY.search(query)

            # Search earlier conversation context when the current
            # question refers to a previously mentioned course.
            if course_match is None:
                for message in reversed(history):
                    if isinstance(message, dict):
                        previous_content = " ".join(
                            str(value)
                            for value in message.values()
                        )
                    else:
                        previous_content = str(message)

                    course_match = COURSE_CODE_IN_QUERY.search(
                        previous_content
                    )

                    if course_match is not None:
                        break

            return {
                "action": "EXECUTE_TOOL",
                "tool_name": "get_course_schedule",
                "tool_params": {
                    "student_id": student_id,
                    "course_code": (
                        course_match.group(0).upper()
                        if course_match
                        else None
                    ),
                },
            }

        # Route 2: Explicit support-ticket request.
        explicit_ticket_request = (
            (
                "ticket" in query_lower
                and any(
                    verb in query_lower
                    for verb in (
                        "create",
                        "open",
                        "submit",
                        "raise",
                    )
                )
            )
            or "escalate" in query_lower
            or "lodge" in query_lower
        )

        if (
            explicit_ticket_request
            and "Tool Result" not in observation
        ):
            return {
                "action": "EXECUTE_TOOL",
                "tool_name": "create_support_ticket",
                "tool_params": {
                    "student_id": student_id,
                    "summary": self._ticket_summary(query),
                    "original_message": query,
                    "category": (
                        TicketCategory.ADMINISTRATIVE.value
                    ),
                    "priority": TicketPriority.MEDIUM.value,
                    "student_confirmed": True,
                },
            }

        # Route 3: Search approved university documents.
        if not observation:
            return {
                "action": "RETRIEVE_KNOWLEDGE",
                "query": query,
            }

        # Route 4: Produce the final grounded answer.
        return {
            "action": "FINAL_SYNTHESIS",
        }

    @staticmethod
    def _lowercase_enum(value: Any) -> str:
        """Normalize an enum member or string to lowercase."""

        return str(
            getattr(value, "value", value)
        ).strip().lower()

    @staticmethod
    def _build_tool_params(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Translate a plan's tool_params into the registry's exact argument shape."""

        if tool_name == "get_course_schedule":
            return {
                "student_id": params.get("student_id", DEFAULT_STUDENT_ID),
                "course_code": params.get("course_code"),
            }

        if tool_name == "create_support_ticket":
            return {
                "student_id": params.get("student_id", DEFAULT_STUDENT_ID),
                "summary": params.get("summary", "Support ticket request"),
                "original_message": params.get(
                    "original_message", "Support ticket request"
                ),
                "category": SupportAgentOrchestrator._lowercase_enum(
                    params.get("category", TicketCategory.ADMINISTRATIVE)
                ),
                "priority": SupportAgentOrchestrator._lowercase_enum(
                    params.get("priority", TicketPriority.MEDIUM)
                ),
                "student_confirmed": params.get("student_confirmed", True),
            }

        return dict(params)

    def _dispatch_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Any:
        """Execute only tools on the registry's execution whitelist."""

        try:
            tool_params = self._build_tool_params(tool_name, params)
            return tool_registry.execute(tool_name, tool_params)

        except tool_registry.UnknownToolError:
            return {
                "error": f"Tool '{tool_name}' not recognized."
            }

        except Exception as error:
            logger.error(
                "Error executing tool %s: %s",
                tool_name,
                error,
            )
            return {
                "error": str(error),
            }

    @staticmethod
    def _format_citation(value: Any) -> str:
        """Ensure a citation has one pair of square brackets."""

        citation = str(value).strip()

        if citation.startswith("[") and citation.endswith("]"):
            return citation

        return f"[{citation}]"

    def _synthesize_response(
        self,
        user_query: str,
        history: List[Dict[str, Any]],
        context: List[Dict[str, Any]],
        observation: str,
        session_id: str,
    ) -> str:
        """Create a live-model or deterministic grounded response."""

        if self.has_live_model:
            user_prompt = f"""
Student Question:
{user_query}

Recent Conversation History:
{json.dumps(history[-3:], indent=2)}

Observed Tool / RAG Facts:
{observation}

Synthesize a direct, grounded answer that follows the system
instructions.
""".strip()

            try:
                response_text = self.model.generate_response(
                    user_message=user_prompt,
                    system_prompt=self.SYSTEM_PROMPT,
                    max_tokens=400,
                    session_id=session_id,
                )

                if response_text and response_text.strip():
                    return response_text.strip()

            except Exception as error:
                logger.error(
                    "Gemini generation call failed (%s). "
                    "Using the grounded deterministic formatter.",
                    error,
                )

        if "Tool Result" in observation:
            raw_tool = observation.replace(
                "Tool Result: ",
                "",
                1,
            )

            try:
                data = json.loads(raw_tool)

                if isinstance(data, list) and data:
                    entries = [
                        (
                            f"- **{item.get('course_code', 'Unknown course')}**: "
                            f"{item.get('course_name', 'Course')} - "
                            f"**{item.get('day', '').capitalize()}** "
                            f"({item.get('start_time')} - "
                            f"{item.get('end_time')}) in "
                            f"**{item.get('room', 'TBD')}** - "
                            f"{item.get('instructor', 'Faculty')}"
                        )
                        for item in data
                    ]

                    return (
                        "Here is your verified lecture timetable:"
                        "\n\n"
                        + "\n".join(entries)
                    )

                if isinstance(data, list):
                    return (
                        "I found no lectures matching your request "
                        "in your timetable."
                    )

                if (
                    isinstance(data, dict)
                    and "error" in data
                ):
                    reason = str(data["error"]).rstrip(".")

                    return (
                        "I could not complete that request: "
                        f"{reason}. Would you like me to submit a "
                        "support ticket so a staff member can "
                        "follow up?"
                    )

                if (
                    isinstance(data, dict)
                    and "ticket_id" in data
                ):
                    return (
                        "Your support ticket "
                        f"**{data['ticket_id']}** has been "
                        "registered with priority "
                        f"**{data.get('priority')}**. Our "
                        "administrative desk will review it "
                        "shortly."
                    )

            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning(
                    "Tool output could not be decoded as JSON."
                )

            return f"Tool Execution Result:\n{raw_tool}"

        if context:
            citations = [
                self._format_citation(
                    item.get(
                        "citation",
                        item.get(
                            "doc",
                            "University Policy",
                        ),
                    )
                )
                for item in context
            ]

            response = (
                f"{context[0].get('text', '').strip()} "
                f"{citations[0]}"
            ).strip()

            if len(citations) > 1:
                response += "\n" + "\n".join(citations[1:])

            return response

        return (
            "I cannot confirm this information from current "
            "official records. Would you like me to submit an "
            "escalation ticket to the relevant department?"
        )