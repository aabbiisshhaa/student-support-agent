# Multi-Step Agent Orchestrator: Sense -> Plan -> Act -> Observe -> Revise

import os
import re
import sys
import time
import json
import logging
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Project modules
from src.baseline_model import GeminiModel, ModelAPIError
from src.rag.retriever import Retriever, EmbedderInfo
from src.tools.timetable_tool import get_course_schedule
from src.tools.ticket_tool import create_support_ticket, TicketCategory, TicketPriority
from src.agent.memory import ConversationMemory
from src.telemetry.tracker import TelemetryTracker, TurnTelemetry

DEFAULT_STUDENT_ID = "2300712345"
COURSE_CODE_IN_QUERY = re.compile(r"\b[A-Za-z]{3}\d{4}\b")
TICKET_SUMMARY_MIN_LENGTH = 10
TICKET_SUMMARY_MAX_LENGTH = 80

EventCallback = Callable[[Dict[str, Any]], None]


# Provide namespace hook for joblib unpickling
import __main__
setattr(__main__, "EmbedderInfo", EmbedderInfo)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger("AgentOrchestrator")
    
# --- Orchestrator Implementation ---
class SupportAgentOrchestrator:
    # Sense-Plan-Act-Observe-Revise Autonomous Orchestrator.
    # Combines hard safety boundaries, deterministic tool dispatch, live RAG retrieval, and Gemini LLM response synthesis.
    
    PROHIBITED_INTENTS = [
        "grade change", "change mark", "alter score", "exam result edit",
        "fee waiver", "clear tuition", "tuition refund", "financial bypass",
        "disciplinary appeal", "cancel suspension", "expulsion overturn"
    ]

    HARD_REFUSAL_MESSAGE = (
        "I am not authorized to process changes to academic records, fee adjustments, "
        "or disciplinary decisions. This request requires human administrative review. "
        "Would you like me to route this to your department administrator?"
    )
    
    SYSTEM_PROMPT = """You are the official University Student Support Case Agent.
Your duty is to assist students using verified university policy documents and tool observations.

CRITICAL RULES:
1. Grounding: Answer ONLY using the facts from the Provided Evidence or Tool Results. Do NOT hallucinate.
2. Citation: If citing university policy, append exact citations in the format: [Source: Document Title, Section / Page].
3. Tone: Professional, clear, objective, and supportive.
4. Unverified Information: If the evidence does not contain the answer, explicitly state that you cannot confirm this from current records and offer an escalation ticket.
"""

    def __init__(self, memory_manager: Optional[ConversationMemory] = None, max_iterations: int = 3):
            self.memory = memory_manager or ConversationMemory()
            self.telemetry = TelemetryTracker()
            self.max_iterations = max_iterations
            self._retriever_instance: Optional[Retriever] = None

            # Live Gemini Model Wrapper
            try:
                self.model = GeminiModel()
                self.has_live_model = True
            except Exception as e:
                logger.warning(f"GeminiModel could not be initialized ({e}). Running in deterministic fallback mode.")
                self.has_live_model = False

    def _get_retriever(self) -> Retriever:
        if self._retriever_instance is None:
            self._retriever_instance = Retriever(top_k=2)
        return self._retriever_instance

    @staticmethod
    def _emit(on_event: Optional[EventCallback], event: Dict[str, Any]) -> None:
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
        failed = isinstance(result, dict) and "error" in result
        record = {
            "tool": tool_name,
            "params": params,
            "status": "error" if failed else "ok",
            "result": result,
            "latency_ms": elapsed_seconds * 1000,
        }
        self._emit(on_event, {
            "event": "tool_end",
            "tool": tool_name,
            "status": record["status"],
            "latency_ms": record["latency_ms"],
        })
        return record

    def run(
        self,
        session_id: str,
        user_query: str,
        student_id: str = DEFAULT_STUDENT_ID,
        on_event: Optional[EventCallback] = None,
    ) -> Dict[str, Any]:
        # Runs the primary Sense -> Plan -> Act -> Observe -> Revise cycle with telemetry instrumentation."""
        start_time = time.time()
        tool_start_total = 0.0
        tools_used = []
        tool_calls: List[Dict[str, Any]] = []

        logger.info(f"[{session_id}] SENSE: Processing user turn...")
        self.memory.initialize_session(session_id, student_id)
        
        turn_idx = len(self.memory.get_recent_history(session_id)) + 1
        turn_metrics = TurnTelemetry(
            session_id=session_id,
            turn_index=turn_idx,
            user_query=user_query,
        )

        # 1. Deterministic Safety Boundary Refusal (Iteration 0)
        query_lower = user_query.lower()
        if any(intent in query_lower for intent in self.PROHIBITED_INTENTS):
            logger.warning(f"[{session_id}] SAFETY REFUSAL: Prohibited intent detected.")
            self.memory.add_turn(session_id, "user", user_query)
            self.memory.add_turn(session_id, "assistant", self.HARD_REFUSAL_MESSAGE)
            
            turn_metrics.status = "refused"
            turn_metrics.total_turn_latency_ms = (time.time() - start_time) * 1000
            self.telemetry.record_turn(turn_metrics)
            
            return {
                "status": "refused",
                "response": self.HARD_REFUSAL_MESSAGE,
                "escalation_required": True,
                "iterations": 0,
                "tool_calls": tool_calls,
            }

        self.memory.add_turn(session_id, "user", user_query)
        session_history = self.memory.get_recent_history(session_id)

        iteration = 0
        observation = ""
        context_snippets = []

        # 2. Multi-Step Execution Loop
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"[{session_id}] PLAN: Iteration {iteration}/{self.max_iterations}")

            plan = self._plan_next_step(user_query, session_history, observation, student_id)

            if plan["action"] == "RETRIEVE_KNOWLEDGE":
                logger.info(f"[{session_id}] ACT: Retrieving RAG knowledge chunks...")
                self._emit(on_event, {"event": "tool_start", "tool": "retriever"})
                t0 = time.time()
                retrieval_result: Any = []
                try:
                    retriever = self._get_retriever()
                    rag_result = retriever.retrieve(plan["query"], top_k=2)
                    if rag_result.passages:
                        context_snippets = [
                            {"text": p.text, "citation": p.citation, "doc": p.doc_title}
                            for p in rag_result.passages
                        ]
                        retrieval_result = context_snippets
                        observation = f"Policy Evidence: {json.dumps(context_snippets)}"
                    else:
                        observation = "No relevant policy documents found in the university database."
                except Exception as e:
                    logger.error(f"Error during RAG retrieval: {e}")
                    observation = f"Knowledge base lookup failed: {str(e)}"
                    retrieval_result = {"error": str(e)}

                elapsed = time.time() - t0
                tool_start_total += elapsed
                tools_used.append("retriever")
                tool_calls.append(self._finish_tool_call(
                    on_event, "retriever", {"query": plan["query"]}, retrieval_result, elapsed
                ))

            elif plan["action"] == "EXECUTE_TOOL":
                tool_name = plan["tool_name"]
                tool_params = plan["tool_params"]
                logger.info(f"[{session_id}] ACT: Executing tool '{tool_name}' with {tool_params}")
                self._emit(on_event, {"event": "tool_start", "tool": tool_name})

                t0 = time.time()
                tool_result = self._dispatch_tool(tool_name, tool_params)
                elapsed = time.time() - t0
                tool_start_total += elapsed
                tools_used.append(tool_name)
                tool_calls.append(self._finish_tool_call(
                    on_event, tool_name, tool_params, tool_result, elapsed
                ))

                observation = f"Tool Result: {json.dumps(tool_result)}"
                logger.info(f"[{session_id}] OBSERVE: Tool execution completed.")

            elif plan["action"] == "FINAL_SYNTHESIS":
                logger.info(f"[{session_id}] REVISE: Synthesizing final response...")
                m_start = time.time()
                final_answer = self._synthesize_response(
                    user_query=user_query,
                    history=session_history,
                    context=context_snippets,
                    observation=observation,
                )
                m_latency = (time.time() - m_start) * 1000
                self.memory.add_turn(session_id, "assistant", final_answer)

                # Collect prompt and response token estimates
                prompt_approx = (len(user_query) + len(observation) + len(str(session_history))) // 4
                comp_approx = len(final_answer) // 4

                ticket_created = any(
                    call["tool"] == "create_support_ticket" and call["status"] == "ok"
                    for call in tool_calls
                )
                tool_failed = any(call["status"] == "error" for call in tool_calls)
                turn_status = "tool_error" if tool_failed else "success"

                turn_metrics.status = turn_status
                turn_metrics.model_latency_ms = m_latency
                turn_metrics.tool_latency_ms = tool_start_total * 1000
                turn_metrics.total_turn_latency_ms = (time.time() - start_time) * 1000
                turn_metrics.prompt_tokens = prompt_approx
                turn_metrics.completion_tokens = comp_approx
                turn_metrics.total_tokens = prompt_approx + comp_approx
                turn_metrics.tools_invoked = tools_used
                self.telemetry.record_turn(turn_metrics)

                return {
                    "status": turn_status,
                    "response": final_answer,
                    "escalation_required": ticket_created,
                    "iterations": iteration,
                    "tool_calls": tool_calls,
                }

        # Safe loop termination fallback
        fallback = "I was unable to resolve your inquiry within the allowed execution cycles. Escalating to staff."
        self.memory.add_turn(session_id, "assistant", fallback)
        return {
            "status": "max_iterations_reached",
            "response": fallback,
            "escalation_required": True,
            "iterations": iteration,
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _ticket_summary(query: str) -> str:
        text = " ".join(query.split())
        if len(text) < TICKET_SUMMARY_MIN_LENGTH:
            text = f"Student request: {text}"
        return text[:TICKET_SUMMARY_MAX_LENGTH]

    def _plan_next_step(
        self,
        query: str,
        history: List[Dict],
        observation: str,
        student_id: str = DEFAULT_STUDENT_ID,
    ) -> Dict[str, Any]:
        query_lower = query.lower()

        # Route 1: Timetable inquiry
        if ("schedule" in query_lower or "timetable" in query_lower or "lecture" in query_lower) and "Tool Result" not in observation:
            course_match = COURSE_CODE_IN_QUERY.search(query)
            return {
                "action": "EXECUTE_TOOL",
                "tool_name": "get_course_schedule",
                "tool_params": {
                    "student_id": student_id,
                    "course_code": course_match.group(0).upper() if course_match else None,
                }
            }

        # Route 2: Support ticket creation (strict 6-argument schema & lowercase enums)
        if ("ticket" in query_lower or "escalate" in query_lower or "lodge" in query_lower or "complaint" in query_lower) and "Tool Result" not in observation:
            return {
                "action": "EXECUTE_TOOL",
                "tool_name": "create_support_ticket",
                "tool_params": {
                    "student_id": student_id,
                    "summary": self._ticket_summary(query),
                    "original_message": query,
                    "category": TicketCategory.ADMINISTRATIVE.value,
                    "priority": TicketPriority.MEDIUM.value,
                    "student_confirmed": True
                }
            }

        # Route 3: RAG Policy Retrieval
        if not observation:
            return {"action": "RETRIEVE_KNOWLEDGE", "query": query}

        # Route 4: Final response synthesis
        return {"action": "FINAL_SYNTHESIS"}

    @staticmethod
    def _lowercase_enum(value: Any) -> str:
        return str(getattr(value, "value", value)).strip().lower()

    def _dispatch_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        try:
            if tool_name == "get_course_schedule":
                return get_course_schedule(
                    student_id=params.get("student_id", DEFAULT_STUDENT_ID),
                    course_code=params.get("course_code")
                )
            elif tool_name == "create_support_ticket":
                return create_support_ticket(
                    student_id=params.get("student_id", DEFAULT_STUDENT_ID),
                    summary=params.get("summary", "Support ticket request"),
                    original_message=params.get("original_message", "Support ticket request"),
                    category=self._lowercase_enum(params.get("category", TicketCategory.ADMINISTRATIVE)),
                    priority=self._lowercase_enum(params.get("priority", TicketPriority.MEDIUM)),
                    student_confirmed=params.get("student_confirmed", True)
                )
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}

        return {"error": f"Tool '{tool_name}' not recognized."}

    def _synthesize_response(
        self,
        user_query: str,
        history: List[Dict[str, Any]],
        context: List[Dict[str, Any]],
        observation: str
    ) -> str:
        # Synthesizes the response using live GeminiModel when available, or formatted fallback."""
        if self.has_live_model:
            user_prompt = f"""
Student Question:
{user_query}

Recent Conversation History:
{json.dumps(history[-3:], indent=2)}

Observed Tool / RAG Facts:
{observation}

Synthesize a direct, grounded answer adhering to the system instructions.
"""
            try:
                response_text = self.model.generate_response(
                    user_message=user_prompt,
                    system_prompt=self.SYSTEM_PROMPT,
                    max_tokens=400
                )
                if response_text and response_text.strip():
                    return response_text.strip()
            except Exception as e:
                logger.error(f"Gemini generation call failed ({e}). Reverting to grounded rule formatter.")

        # Grounded Rule-Based Formatter (Used if LLM API is unreachable or key missing)
        if "Tool Result" in observation:
            raw_tool = observation.replace("Tool Result: ", "")
            try:
                data = json.loads(raw_tool)
                if isinstance(data, list) and data:
                    entries = [
                        f"• **{item.get('day', '').capitalize()}** ({item.get('start_time')} - {item.get('end_time')}) in **{item.get('room', 'TBD')}** — {item.get('instructor', 'Faculty')} ({item.get('course_name')})"
                        for item in data
                    ]
                    return f"Here is your verified lecture timetable:\n\n" + "\n".join(entries)
                if isinstance(data, list):
                    return "I found no lectures matching your request in your timetable."
                if isinstance(data, dict) and "error" in data:
                    reason = str(data["error"]).rstrip(".")
                    return (
                        f"I could not complete that request: {reason}. "
                        "Would you like me to submit a support ticket so a staff member can follow up?"
                    )
                if isinstance(data, dict) and "ticket_id" in data:
                    return f"Your support ticket **{data['ticket_id']}** has been registered with priority **{data.get('priority')}**. Our administrative desk will review it shortly."
            except Exception:
                pass
            return f"Tool Execution Result:\n{raw_tool}"

        if context:
            citations = [f"[{c.get('citation', c.get('doc', 'University Policy'))}]" for c in context]
            return f"{context[0].get('text')}\n\n" + "\n".join(citations)

        return (
            "I cannot confirm this information from current official records. "
            "Would you like me to submit an escalation ticket to the relevant department?"
        )
        
    
# --- Standalone Integration Verification ---
if __name__ == "__main__":
    print("\n=== TESTING LIVE AGENT ORCHESTRATOR & GEMINI INTEGRATION ===")
    memory = ConversationMemory()
    orchestrator = SupportAgentOrchestrator(memory_manager=memory)

    # Test 1: Timetable Tool Call
    print("\n--- Test 1: Timetable Tool Call ---")
    res1 = orchestrator.run("session-live-01", "When is the lecture schedule for BSE4104?")
    print("Response:\n", res1["response"])
    print("Meta:", res1)

    # Test 2: Safety Refusal
    print("\n--- Test 2: Safety Boundary Refusal ---")
    res2 = orchestrator.run("session-live-01", "Can you please do a grade change for my last exam?")
    print("Response:\n", res2["response"])
    print("Meta:", res2)

    # Test 3: Grounded Policy RAG Retrieval
    print("\n--- Test 3: Policy Grounding Retrieval ---")
    res3 = orchestrator.run("session-live-01", "What are the rules regarding the capstone project?")
    print("Response:\n", res3["response"])
    print("Meta:", res3)

    # Test 4: Support Ticket Creation
    print("\n--- Test 4: Support Ticket Tool Call ---")
    res4 = orchestrator.run("session-live-01", "Please create a support ticket for my portal login issue.")
    print("Response:\n", res4["response"])
    print("Meta:", res4)